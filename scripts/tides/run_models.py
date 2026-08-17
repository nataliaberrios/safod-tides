#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json

def plane_stress(enn, eee, ene, E, nu):
    p=E/(1-nu**2)
    snn=p*(enn+nu*eee)
    see=p*(eee+nu*enn)
    sne=E/(1+nu)*ene
    return snn,see,sne

def fault_vectors(strike_deg,dip_deg,dipdir_deg):
    strike=np.deg2rad(strike_deg)
    dip=np.deg2rad(dip_deg)
    dipdir=np.deg2rad(dipdir_deg)
    s=np.array([np.cos(strike),np.sin(strike),0.0])
    d=np.array([np.cos(dip)*np.cos(dipdir),np.cos(dip)*np.sin(dipdir),np.sin(dip)])
    n=np.cross(s,d); n=n/np.linalg.norm(n)
    return s,d,n

def stress_proxies(snn,see,sne,cfg):
    m=cfg["model_parameters"]
    s,_,n=fault_vectors(m["fault_strike_deg"],m["fault_dip_deg"],m["fault_dip_direction_deg"])
    normal_tension=snn*n[0]**2+2*sne*n[0]*n[1]+see*n[1]**2
    normal_comp=-(normal_tension-np.mean(normal_tension))
    shear=(
        s[0]*(snn*n[0]+sne*n[1])
        +s[1]*(sne*n[0]+see*n[1])
    )
    shear-=np.mean(shear)
    mean_h=-0.5*(snn+see); mean_h-=np.mean(mean_h)
    return normal_comp,shear,mean_h

def host_moduli(E,nu):
    return E/(3*(1-2*nu)), E/(2*(1+nu))

def model_one_forcing(df,cfg,label):
    m=cfg["model_parameters"]
    enn=df.eps_NN.to_numpy()
    eee=df.eps_EE.to_numpy()
    ene=df.eps_NE.to_numpy()
    areal=enn+eee
    centered=areal-np.mean(areal)
    shape=centered/np.max(np.abs(centered))

    # A
    stress_A=m["niu_tidal_stress_scale_pa"]*shape
    dv_A=m["niu_stress_sensitivity_pa_inv"]*stress_A

    # B
    snn,see,sne=plane_stress(enn,eee,ene,m["youngs_modulus_pa"],m["poisson_ratio"])
    fn,fs,mh=stress_proxies(snn,see,sne,cfg)
    lookup={"fault_normal":fn,"fault_parallel_shear":fs,"mean_horizontal":mh}
    selected=lookup[m["model_b_stress_proxy"]]
    dv_B=m["niu_stress_sensitivity_pa_inv"]*selected

    # C
    dv_C=-m["takano_strain_sensitivity"]*centered
    dv_C_sheng=-m["sheng_strain_sensitivity"]*centered

    # D
    Kh,muh=host_moduli(m["model_d_host_E_pa"],m["model_d_host_nu"])
    nuh=(3*Kh-2*muh)/(6*Kh+2*muh)
    Ak=16*(1-nuh**2)/(9*(1-2*nuh))
    Amu=32*(1-nuh)*(5-nuh)/(45*(2-nuh))
    rho=m["model_d_density_kg_m3"]
    mu_target=rho*m["model_d_target_Vs_m_s"]**2
    rho_c0=(muh/mu_target-1)/Amu
    pref=0.5*(Amu*rho_c0)/(1+Amu*rho_c0)
    sigma_hat=pref/m["niu_stress_sensitivity_pa_inv"]

    def vel(rc):
        K=Kh/(1+Ak*rc)
        mu=muh/(1+Amu*rc)
        vp=np.sqrt((K+4*mu/3)/rho)
        vs=np.sqrt(mu/rho)
        return vp,vs
    vp0,vs0=vel(rho_c0)
    rc=rho_c0*np.exp(-selected/sigma_hat)
    vp,vs=vel(rc)
    dvp=(vp-vp0)/vp0
    dvs=(vs-vs0)/vs0

    out=pd.DataFrame({
        "time_utc":df.time_utc,
        f"{label}_areal_strain":areal,
        f"{label}_model_A_stress_pa":stress_A,
        f"{label}_model_A_dv_over_v":dv_A,
        f"{label}_sigma_NN_pa":snn,
        f"{label}_sigma_EE_pa":see,
        f"{label}_sigma_NE_pa":sne,
        f"{label}_fault_normal_pa":fn,
        f"{label}_fault_shear_pa":fs,
        f"{label}_mean_horizontal_pa":mh,
        f"{label}_model_B_dv_over_v":dv_B,
        f"{label}_model_C_takano_dv_over_v":dv_C,
        f"{label}_model_C_sheng_dv_over_v":dv_C_sheng,
        f"{label}_model_D_crack_density":rc,
        f"{label}_model_D_Vp_m_s":vp,
        f"{label}_model_D_Vs_m_s":vs,
        f"{label}_model_D_dVp_over_Vp":dvp,
        f"{label}_model_D_dVs_over_Vs":dvs,
    })
    summary={
        "forcing":label,
        "max_abs_model_A":float(np.max(np.abs(dv_A))),
        "max_abs_model_B":float(np.max(np.abs(dv_B))),
        "max_abs_model_C_takano":float(np.max(np.abs(dv_C))),
        "max_abs_model_D_Vs":float(np.max(np.abs(dvs))),
        "max_abs_model_D_Vp":float(np.max(np.abs(dvp))),
        "max_abs_selected_stress_pa":float(np.max(np.abs(selected))),
        "model_D_rho_c0":float(rho_c0),
        "model_D_sigma_hat_pa":float(sigma_hat),
        "model_D_baseline_Vp_m_s":float(vp0),
        "model_D_baseline_Vs_m_s":float(vs0),
    }
    return out,summary

def read_forcing(path):
    df=pd.read_csv(path,parse_dates=["time_utc"])
    needed={"eps_NN","eps_EE","eps_NE"}
    missing=needed-set(df.columns)
    if missing: raise ValueError(f"{path} missing {sorted(missing)}")
    return df

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default=str(ROOT/"config.json"))
    p.add_argument("--pysolid",default=str(ROOT/"outputs/tides/pysolid_tides.csv"))
    p.add_argument("--spotl",default=str(ROOT/"outputs/tides/spotl_ertid_tides.csv"))
    p.add_argument("--output",default=str(ROOT/"outputs/tides/model_results.csv"))
    p.add_argument("--summary",default=str(ROOT/"outputs/tides/model_summary.json"))
    p.add_argument("--provenance",default=str(ROOT/"outputs/tides/model_provenance.json"))
    p.add_argument("--allow-missing-spotl",action="store_true")
    a=p.parse_args()
    cfg=load_config(a.config)

    py=read_forcing(a.pysolid)
    pyout,pysum=model_one_forcing(py,cfg,"pysolid")
    combined=pyout
    summaries=[pysum]

    spotl_path=Path(a.spotl)
    if spotl_path.exists():
        sp=read_forcing(spotl_path)
        # Align by timestamp, because ERTID endpoint convention may differ.
        spout,spsum=model_one_forcing(sp,cfg,"spotl")
        combined=pd.merge(combined,spout,on="time_utc",how="outer").sort_values("time_utc")
        summaries.append(spsum)
    elif not a.allow_missing_spotl:
        raise FileNotFoundError(
            f"{spotl_path} not found. Run run_spotl_ertid.py first "
            "or use --allow-missing-spotl only for local cached testing."
        )

    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    combined.to_csv(a.output,index=False)
    write_json(a.summary,{"models":summaries,"primary_forcing":cfg["primary_forcing"]})
    write_json(a.provenance,provenance_base(__file__,{
        "output":str(Path(a.output).resolve()),
        "forcings":[s["forcing"] for s in summaries],
        "model_parameters":cfg["model_parameters"],
    }))
    print(f"wrote model products to {a.output}")
    for s in summaries:
        print(s)

if __name__=="__main__":
    main()
