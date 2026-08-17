#!/usr/bin/env python
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from common import ROOT, provenance_base, write_json

def centered(x):
    x=np.asarray(x,float)
    return x-np.nanmean(x)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pysolid",default=str(ROOT/"outputs/tides/pysolid_tides.csv"))
    p.add_argument("--spotl",default=str(ROOT/"outputs/tides/spotl_ertid_tides.csv"))
    p.add_argument("--analytic",default=str(ROOT/"outputs/tides/analytic_degree2_tides.csv"))
    p.add_argument("--output",default=str(ROOT/"outputs/tides/forcing_comparison.csv"))
    p.add_argument("--provenance",default=str(ROOT/"outputs/tides/forcing_comparison_provenance.json"))
    a=p.parse_args()

    py=pd.read_csv(a.pysolid,parse_dates=["time_utc"]).set_index("time_utc")
    sp=pd.read_csv(a.spotl,parse_dates=["time_utc"]).set_index("time_utc")
    an=pd.read_csv(a.analytic,parse_dates=["time_utc"]).set_index("time_utc")

    rows=[]
    for name,other in [("spotl",sp),("analytic",an)]:
        z=py[["eps_NN","eps_EE","eps_NE","areal_strain"]].join(
            other[["eps_NN","eps_EE","eps_NE","areal_strain"]],
            how="inner",lsuffix="_pysolid",rsuffix=f"_{name}"
        )
        for comp in ["eps_NN","eps_EE","eps_NE","areal_strain"]:
            x=centered(z[f"{comp}_pysolid"])
            y=centered(z[f"{comp}_{name}"])
            rows.append({
                "comparison":f"pysolid_vs_{name}",
                "component":comp,
                "n_samples":len(z),
                "correlation":np.corrcoef(x,y)[0,1],
                "pysolid_peak_to_peak":np.ptp(z[f"{comp}_pysolid"]),
                "other_peak_to_peak":np.ptp(z[f"{comp}_{name}"]),
                "pysolid_over_other_amplitude":np.ptp(z[f"{comp}_pysolid"])/np.ptp(z[f"{comp}_{name}"]),
                "rms_centered_difference":np.sqrt(np.mean((x-y)**2)),
            })
    out=pd.DataFrame(rows)
    out.to_csv(a.output,index=False)
    write_json(a.provenance,provenance_base(__file__,{"output":str(Path(a.output).resolve())}))
    print(out.to_string(index=False))

if __name__=="__main__":
    main()
