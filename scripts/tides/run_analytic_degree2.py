#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json

G = 6.674e-11
R = 6.371e6
g = 9.81
M_MOON = 7.342e22
M_SUN = 1.989e30
AU = 1.495978707e11
H2 = 0.603741
L2 = 0.084010

def datetime_range(start, end, step_sec):
    n = int((end - start).total_seconds() // step_sec)
    return [start + timedelta(seconds=step_sec * i) for i in range(n + 1)]

def julian_date(times):
    sec = np.array([t.timestamp() for t in times])
    return sec / 86400.0 + 2440587.5

def sun_position(jd):
    d = jd - 2451545.0
    L = np.deg2rad((280.460 + 0.9856474 * d) % 360.0)
    M = np.deg2rad((357.528 + 0.9856003 * d) % 360.0)
    lam = L + np.deg2rad(1.915) * np.sin(M) + np.deg2rad(0.020) * np.sin(2*M)
    dist = (1.00014 - 0.01671*np.cos(M) - 0.00014*np.cos(2*M)) * AU
    ob = np.deg2rad(23.4393 - 3.563e-7 * d)
    ra = np.arctan2(np.cos(ob) * np.sin(lam), np.cos(lam))
    dec = np.arcsin(np.sin(ob) * np.sin(lam))
    return ra, dec, dist

def moon_position(jd):
    d = jd - 2451543.5
    N = np.deg2rad((125.1228 - 0.0529538083*d) % 360)
    inc = np.deg2rad(5.1454)
    w = np.deg2rad((318.0634 + 0.1643573223*d) % 360)
    a = 60.2666
    e = 0.054900
    M = np.deg2rad((115.3654 + 13.0649929509*d) % 360)

    E = M.copy()
    for _ in range(3):
        E -= (E - e*np.sin(E) - M) / (1 - e*np.cos(E))

    xo = a*(np.cos(E)-e)
    yo = a*np.sqrt(1-e**2)*np.sin(E)
    rr = np.hypot(xo, yo)
    v = np.arctan2(yo, xo)
    arg = v + w

    xe = rr*(np.cos(N)*np.cos(arg)-np.sin(N)*np.sin(arg)*np.cos(inc))
    ye = rr*(np.sin(N)*np.cos(arg)+np.cos(N)*np.sin(arg)*np.cos(inc))
    ze = rr*np.sin(arg)*np.sin(inc)

    ob = np.deg2rad(23.4393 - 3.563e-7*(jd-2451545.0))
    x = xe
    y = ye*np.cos(ob)-ze*np.sin(ob)
    z = ye*np.sin(ob)+ze*np.cos(ob)
    ra = np.arctan2(y, x)
    dec = np.arctan2(z, np.hypot(x, y))
    return ra, dec, rr*R

def degree2_potential_at(jd, ra, dec, distance, mass, lat_rad, lon_rad):
    d = jd - 2451545.0
    gmst = np.deg2rad((280.46061837 + 360.98564736629*d) % 360)
    H = gmst + lon_rad - ra
    cosz = np.sin(lat_rad)*np.sin(dec) + np.cos(lat_rad)*np.cos(dec)*np.cos(H)
    P2 = 0.5*(3*cosz**2-1)
    return G*mass/distance**3*R**2*P2

def run(cfg):
    lat = np.deg2rad(cfg["site"]["latitude_deg"])
    lon = np.deg2rad(cfg["site"]["longitude_deg"])
    start = datetime.fromisoformat(cfg["window"]["start_utc"])
    end = datetime.fromisoformat(cfg["window"]["end_utc"])
    step = int(cfg["window"]["sample_seconds"])
    times = datetime_range(start, end, step)
    jd = julian_date(times)

    sra, sdec, sd = sun_position(jd)
    mra, mdec, md = moon_position(jd)

    def W(la, lo):
        return (
            degree2_potential_at(jd, sra, sdec, sd, M_SUN, la, lo)
            + degree2_potential_at(jd, mra, mdec, md, M_MOON, la, lo)
        )

    h = 1e-4
    w0 = W(lat, lon)
    wnp, wnm = W(lat+h,lon), W(lat-h,lon)
    wep, wem = W(lat,lon+h), W(lat,lon-h)
    wpp, wpm = W(lat+h,lon+h), W(lat+h,lon-h)
    wmp, wmm = W(lat-h,lon+h), W(lat-h,lon-h)

    w_lat = (wnp-wnm)/(2*h)
    w_lon = (wep-wem)/(2*h)
    w_latlat = (wnp-2*w0+wnm)/h**2
    w_lonlon = (wep-2*w0+wem)/h**2
    w_latlon = (wpp-wpm-wmp+wmm)/(4*h**2)

    c = np.cos(lat); tan = np.tan(lat)
    ur = H2/g*w0
    un = L2/g*w_lat
    ue = L2/(g*c)*w_lon
    dun_dlat = L2/g*w_latlat
    dun_dlon = L2/g*w_latlon
    due_dlat = L2/g*(tan/c*w_lon + w_latlon/c)
    due_dlon = L2/(g*c)*w_lonlon

    enn = (dun_dlat+ur)/R
    eee = (due_dlon/c+ur-un*tan)/R
    ene = 0.5*(due_dlat+ue*tan+dun_dlon/c)/R

    out = pd.DataFrame({
        "time_utc": pd.to_datetime(times, utc=True),
        "potential_m2_s2": w0,
        "eps_NN": enn,
        "eps_EE": eee,
        "eps_NE": ene,
    })
    out["areal_strain"] = out.eps_NN + out.eps_EE
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT/"config.json"))
    p.add_argument("--output", default=str(ROOT/"outputs/tides/analytic_degree2_tides.csv"))
    p.add_argument("--provenance", default=str(ROOT/"outputs/tides/analytic_degree2_provenance.json"))
    a=p.parse_args()
    cfg=load_config(a.config)
    df=run(cfg)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(a.output,index=False)
    write_json(a.provenance, provenance_base(__file__,{
        "method":"compact degree-2 Sun+Moon ephemeris with PREM Love numbers",
        "h2":H2,"l2":L2,"output":str(Path(a.output).resolve()),"rows":len(df)
    }))
    print(f"analytic degree-2: wrote {len(df)} samples to {a.output}")
    print(f"peak-to-peak areal strain = {np.ptp(df.areal_strain):.6e}")

if __name__=="__main__":
    main()
