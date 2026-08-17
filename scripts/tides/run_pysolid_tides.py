#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime
from importlib.metadata import version as package_version
from pathlib import Path

import numpy as np
import pandas as pd
import pysolid

from common import ROOT, ensure_output_dir, load_config, provenance_base, write_json

def run(cfg):
    site = cfg["site"]
    win = cfg["window"]
    settings = cfg["package_settings"]

    lat = float(site["latitude_deg"])
    lon = float(site["longitude_deg"])
    dt0 = datetime.fromisoformat(win["start_utc"]).replace(tzinfo=None)
    dt1 = datetime.fromisoformat(win["end_utc"]).replace(tzinfo=None)
    step_sec = int(win["sample_seconds"])
    hdeg = float(settings["pysolid_spatial_step_deg"])

    def one_point(la, lo):
        return pysolid.calc_solid_earth_tides_point(
            la, lo, dt0, dt1,
            step_sec=step_sec,
            display=False,
            verbose=False,
        )

    t, e0, n0, u0 = one_point(lat, lon)
    _, e_np, n_np, _ = one_point(lat + hdeg, lon)
    _, e_nm, n_nm, _ = one_point(lat - hdeg, lon)
    _, e_ep, n_ep, _ = one_point(lat, lon + hdeg)
    _, e_em, n_em, _ = one_point(lat, lon - hdeg)

    h = np.deg2rad(hdeg)
    phi = np.deg2rad(lat)
    c = np.cos(phi)
    tan_phi = np.tan(phi)
    R = 6378137.0

    dn_dphi = (n_np - n_nm) / (2.0 * h)
    de_dphi = (e_np - e_nm) / (2.0 * h)
    dn_dlam = (n_ep - n_em) / (2.0 * h)
    de_dlam = (e_ep - e_em) / (2.0 * h)

    eps_nn = (dn_dphi + u0) / R
    eps_ee = (de_dlam / c + u0 - n0 * tan_phi) / R
    eps_ne = 0.5 * (de_dphi + e0 * tan_phi + dn_dlam / c) / R

    df = pd.DataFrame({
        "time_utc": pd.to_datetime(t, utc=True),
        "u_E_m": np.asarray(e0),
        "u_N_m": np.asarray(n0),
        "u_U_m": np.asarray(u0),
        "eps_NN": eps_nn,
        "eps_EE": eps_ee,
        "eps_NE": eps_ne,
    })
    df["areal_strain"] = df["eps_NN"] + df["eps_EE"]
    return df

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "config.json"))
    p.add_argument("--output", default=str(ROOT / "outputs/tides/pysolid_tides.csv"))
    p.add_argument("--provenance", default=str(ROOT / "outputs/tides/pysolid_provenance.json"))
    args = p.parse_args()

    cfg = load_config(args.config)
    required = cfg["package_settings"]["pysolid_version"]
    actual = package_version("pysolid")
    if actual != required:
        raise RuntimeError(f"PySolid version mismatch: required {required}, found {actual}")

    df = run(cfg)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)

    prov = provenance_base(__file__, {
        "software": "PySolid",
        "software_version": actual,
        "output": str(Path(args.output).resolve()),
        "rows": len(df),
        "site": cfg["site"],
        "window": cfg["window"],
        "spatial_step_deg": cfg["package_settings"]["pysolid_spatial_step_deg"],
    })
    write_json(args.provenance, prov)

    print(f"PySolid {actual}: wrote {len(df)} samples to {args.output}")
    print(f"peak-to-peak areal strain = {np.ptp(df['areal_strain']):.6e}")

if __name__ == "__main__":
    main()
