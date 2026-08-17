#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, sha256_file, write_json

def doy(dt):
    return int(dt.strftime("%j"))

def decimal_hour(dt):
    return dt.hour + dt.minute/60 + dt.second/3600 + dt.microsecond/3.6e9

def read_series(path):
    text=Path(path).read_text()
    a=np.fromstring(text, sep=" ")
    if a.size==0:
        raise RuntimeError(f"No numeric values parsed from {path}")
    return a

def run(cfg, ertid, work):
    site=cfg["site"]; win=cfg["window"]
    lat=float(site["latitude_deg"]); lon=float(site["longitude_deg"])
    start=datetime.fromisoformat(win["start_utc"])
    end=datetime.fromisoformat(win["end_utc"])
    step=int(win["sample_seconds"])
    sample_hours=step/3600

    work=Path(work); work.mkdir(parents=True,exist_ok=True)
    f0=work/"strain_az000.txt"
    f45=work/"strain_az045.txt"
    f90=work/"strain_az090.txt"

    # ERTID is interactive. The official man page documents this ordering:
    # start, end, sample interval, theoretical-vs-MC choice, station,
    # requested gravity/tilt/strain tides, azimuths, filenames.
    lines=[
        f"{start.year} {doy(start)} {decimal_hour(start):.12f}",
        f"{end.year} {doy(end)} {decimal_hour(end):.12f}",
        f"{sample_hours:.14f}",
        "t",
        f"{lat:.10f}",
        f"{lon:.10f}",
        "0",  # gravity tides
        "0",  # tilt tides
        "3",  # strain tides
        "0",
        "45",
        "90",
        str(f0),
        str(f45),
        str(f90),
    ]
    stdin="\n".join(lines)+"\n"

    proc=subprocess.run(
        [str(Path(ertid).resolve())],
        cwd=work,
        input=stdin,
        text=True,
        capture_output=True,
    )
    (work/"ertid.stdout").write_text(proc.stdout)
    (work/"ertid.stderr").write_text(proc.stderr)
    (work/"ertid.stdin").write_text(stdin)

    if proc.returncode!=0:
        raise RuntimeError(
            f"ertid failed with return code {proc.returncode}; "
            f"see {work/'ertid.stdout'} and {work/'ertid.stderr'}"
        )

    e0=read_series(f0)
    e45=read_series(f45)
    e90=read_series(f90)
    if not (len(e0)==len(e45)==len(e90)):
        raise RuntimeError("ERTID output lengths differ.")

    # nanostrain -> strain
    enn=e0*1e-9
    eee=e90*1e-9
    ene=(e45-0.5*(e0+e90))*1e-9

    times=[start+timedelta(seconds=i*step) for i in range(len(e0))]
    df=pd.DataFrame({
        "time_utc":pd.to_datetime(times,utc=True),
        "eps_NN":enn,
        "eps_EE":eee,
        "eps_NE":ene,
    })
    df["areal_strain"]=df.eps_NN+df.eps_EE
    return df, proc, stdin

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT/"config.json"))
    p.add_argument("--ertid", default=str(ROOT/"external/spotl/bin/ertid"))
    p.add_argument("--work-dir", default=str(ROOT/"outputs/tides/spotl_work"))
    p.add_argument("--output", default=str(ROOT/"outputs/tides/spotl_ertid_tides.csv"))
    p.add_argument("--provenance", default=str(ROOT/"outputs/tides/spotl_provenance.json"))
    a=p.parse_args()

    cfg=load_config(a.config)
    ertid=Path(a.ertid)
    if not ertid.exists():
        raise FileNotFoundError(
            f"{ertid} not found. Run scripts/tides/install_spotl.sh first."
        )

    df, proc, stdin=run(cfg,ertid,a.work_dir)
    df.to_csv(a.output,index=False)
    write_json(a.provenance, provenance_base(__file__,{
        "software":"SPOTL ertid",
        "software_version":cfg["package_settings"]["spotl_version"],
        "executable":str(ertid.resolve()),
        "executable_sha256":sha256_file(ertid),
        "output":str(Path(a.output).resolve()),
        "rows":len(df),
        "site":cfg["site"],
        "window":cfg["window"],
        "requested_strain_azimuths_deg":[0,45,90],
    }))
    print(f"SPOTL ertid: wrote {len(df)} samples to {a.output}")
    print(f"peak-to-peak areal strain = {np.ptp(df.areal_strain):.6e}")

if __name__=="__main__":
    main()
