#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json

# Coordinates are North, East, Down (NED).
#
# Thomas et al. (2012) specify the architecture
#     SPOTL strain -> linear elasticity -> fault traction,
# but do not print the constitutive equation or numerical elastic constants in
# their Figure-3 methods paragraph. A later Parkfield implementation by van der
# Elst et al. (2016), using SPOTL for the same deep-SAF tidal-stress problem,
# explicitly states plane strain, nu=0.25, and shear modulus G=30 GPa. Model B
# adopts that explicit Parkfield closure and keeps the Thomas geometry as a
# separate reference calculation from the SAFOD application geometry.


def isotropic_plane_strain_stress(enn, eee, ene, shear_modulus_pa, nu):
    """3-D isotropic Hooke law under plane strain.

    NED coordinates. We impose eps_DD = eps_ND = eps_ED = 0. Stress is
    positive in tension; ``ene`` is tensor shear strain, not engineering shear.
    """
    mu = float(shear_modulus_pa)
    nu = float(nu)
    if not (-1.0 < nu < 0.5):
        raise ValueError("Poisson ratio must lie between -1 and 0.5.")
    lam = 2.0 * mu * nu / (1.0 - 2.0 * nu)

    enn = np.asarray(enn, float)
    eee = np.asarray(eee, float)
    ene = np.asarray(ene, float)
    trace = enn + eee

    snn = 2.0 * mu * enn + lam * trace
    see = 2.0 * mu * eee + lam * trace
    sdd = lam * trace
    sne = 2.0 * mu * ene
    return snn, see, sdd, sne


def fault_basis(strike_deg, dip_deg, dip_direction_deg):
    """Return strike, down-dip, and normal unit vectors in NED coordinates."""
    strike = np.deg2rad(float(strike_deg))
    dip = np.deg2rad(float(dip_deg))
    dipdir = np.deg2rad(float(dip_direction_deg))

    s = np.array([np.cos(strike), np.sin(strike), 0.0])
    d = np.array([
        np.cos(dip) * np.cos(dipdir),
        np.cos(dip) * np.sin(dipdir),
        np.sin(dip),
    ])
    s /= np.linalg.norm(s)
    d /= np.linalg.norm(d)
    n = np.cross(s, d)
    n /= np.linalg.norm(n)
    return s, d, n


def resolve_geometry(snn, see, sdd, sne, strike_deg, dip_deg, dip_direction_deg):
    """Resolve the plane-strain stress tensor onto one fault geometry.

    Returns FNS (positive=tension/unclamping), along-strike shear, down-dip
    shear, and mean normal stress. All time series are mean removed.
    """
    s, d, n = fault_basis(strike_deg, dip_deg, dip_direction_deg)

    nt = len(np.asarray(snn))
    sigma = np.zeros((nt, 3, 3), dtype=float)
    sigma[:, 0, 0] = snn
    sigma[:, 1, 1] = see
    sigma[:, 2, 2] = sdd
    sigma[:, 0, 1] = sigma[:, 1, 0] = sne

    traction = np.einsum("tij,j->ti", sigma, n)
    fns = np.einsum("ti,i->t", traction, n)
    shear_strike = np.einsum("ti,i->t", traction, s)
    shear_dip = np.einsum("ti,i->t", traction, d)
    mean_normal = (np.asarray(snn) + np.asarray(see) + np.asarray(sdd)) / 3.0

    fns -= np.mean(fns)
    shear_strike -= np.mean(shear_strike)
    shear_dip -= np.mean(shear_dip)
    mean_normal -= np.mean(mean_normal)
    return fns, shear_strike, shear_dip, mean_normal


def resolve_safod_geometry(snn, see, sdd, sne, cfg):
    m = cfg["model_parameters"]
    return resolve_geometry(
        snn, see, sdd, sne,
        m["fault_strike_deg"],
        m["fault_dip_deg"],
        m["fault_dip_direction_deg"],
    )


def resolve_thomas_reference_geometry(snn, see, sdd, sne, cfg):
    """Resolve onto Thomas et al. (2012) vertical N42W reference plane.

    N42W = azimuth 318 deg. For a vertical plane, either horizontal normal
    direction represents the same plane; 228 deg is used here for dip direction.
    The along-strike sign is reported with the +strike direction toward N42W.
    """
    m = cfg["model_parameters"]
    strike = float(m.get("thomas_2012_reference_fault_strike_deg", 318.0))
    dip = float(m.get("thomas_2012_reference_fault_dip_deg", 90.0))
    dipdir = (strike - 90.0) % 360.0
    return resolve_geometry(snn, see, sdd, sne, strike, dip, dipdir)


def host_moduli(E, nu):
    return E / (3.0 * (1.0 - 2.0 * nu)), E / (2.0 * (1.0 + nu))


def model_one_forcing(df, cfg, label):
    m = cfg["model_parameters"]
    enn = df.eps_NN.to_numpy()
    eee = df.eps_EE.to_numpy()
    ene = df.eps_NE.to_numpy()
    areal = enn + eee
    centered = areal - np.mean(areal)
    shape = centered / np.max(np.abs(centered))

    # Model A -- Niu amplitude shortcut.
    stress_A = m["niu_tidal_stress_scale_pa"] * shape
    dv_A = m["niu_stress_sensitivity_pa_inv"] * stress_A

    # Model B -- explicit Parkfield-style elastic closure.
    snn, see, sdd, sne = isotropic_plane_strain_stress(
        enn,
        eee,
        ene,
        m["model_b_shear_modulus_pa"],
        m["model_b_poisson_ratio"],
    )

    # Primary SAFOD application geometry.
    fns, shear_strike, shear_dip, mean_normal = resolve_safod_geometry(
        snn, see, sdd, sne, cfg
    )

    # Separate Thomas et al. Figure-3 reference geometry: vertical N42W.
    th_fns, th_rlss, th_dip_shear, _ = resolve_thomas_reference_geometry(
        snn, see, sdd, sne, cfg
    )

    lookup = {
        "fault_normal": fns,
        "fault_parallel_shear": shear_strike,
        "fault_dip_shear": shear_dip,
        "mean_normal": mean_normal,
    }
    selected = lookup[m["model_b_stress_proxy"]]

    # Niu barometric sensitivity -> tidal stress is OUR transfer assumption.
    dv_B = m["niu_stress_sensitivity_pa_inv"] * selected

    # Model C -- direct strain-sensitivity transfers from other sites.
    dv_C = -m["takano_strain_sensitivity"] * centered
    dv_C_sheng = -m["sheng_strain_sensitivity"] * centered

    # Model D -- mechanistic crack closure, driven by the same selected stress.
    Kh, muh = host_moduli(m["model_d_host_E_pa"], m["model_d_host_nu"])
    nuh = (3.0 * Kh - 2.0 * muh) / (6.0 * Kh + 2.0 * muh)
    Ak = 16.0 * (1.0 - nuh**2) / (9.0 * (1.0 - 2.0 * nuh))
    Amu = 32.0 * (1.0 - nuh) * (5.0 - nuh) / (45.0 * (2.0 - nuh))
    rho = m["model_d_density_kg_m3"]
    mu_target = rho * m["model_d_target_Vs_m_s"]**2
    rho_c0 = (muh / mu_target - 1.0) / Amu
    pref = 0.5 * (Amu * rho_c0) / (1.0 + Amu * rho_c0)
    sigma_hat = pref / m["niu_stress_sensitivity_pa_inv"]

    def vel(rc):
        K = Kh / (1.0 + Ak * rc)
        mu = muh / (1.0 + Amu * rc)
        vp = np.sqrt((K + 4.0 * mu / 3.0) / rho)
        vs = np.sqrt(mu / rho)
        return vp, vs

    vp0, vs0 = vel(rho_c0)
    rc = rho_c0 * np.exp(-selected / sigma_hat)
    vp, vs = vel(rc)
    dvp = (vp - vp0) / vp0
    dvs = (vs - vs0) / vs0

    out = pd.DataFrame({
        "time_utc": df.time_utc,
        f"{label}_areal_strain": areal,
        f"{label}_model_A_stress_pa": stress_A,
        f"{label}_model_A_dv_over_v": dv_A,
        f"{label}_sigma_NN_pa": snn,
        f"{label}_sigma_EE_pa": see,
        f"{label}_sigma_DD_pa": sdd,
        f"{label}_sigma_NE_pa": sne,
        # Primary SAFOD geometry.
        f"{label}_FNS_pa": fns,
        f"{label}_along_strike_shear_pa": shear_strike,
        f"{label}_dip_shear_pa": shear_dip,
        f"{label}_mean_normal_stress_pa": mean_normal,
        # Thomas et al. (2012) Figure-3 reference geometry.
        f"{label}_thomas_FNS_pa": th_fns,
        f"{label}_thomas_RLSS_pa": th_rlss,
        f"{label}_thomas_dip_shear_pa": th_dip_shear,
        # Backward-compatible aliases for SAFOD application geometry.
        f"{label}_fault_normal_pa": fns,
        f"{label}_fault_shear_pa": shear_strike,
        f"{label}_model_B_dv_over_v": dv_B,
        f"{label}_model_C_takano_dv_over_v": dv_C,
        f"{label}_model_C_sheng_dv_over_v": dv_C_sheng,
        f"{label}_model_D_crack_density": rc,
        f"{label}_model_D_Vp_m_s": vp,
        f"{label}_model_D_Vs_m_s": vs,
        f"{label}_model_D_dVp_over_Vp": dvp,
        f"{label}_model_D_dVs_over_Vs": dvs,
    })

    max_fns = float(np.max(np.abs(fns)))
    max_shear = float(np.max(np.abs(shear_strike)))
    max_th_fns = float(np.max(np.abs(th_fns)))
    max_th_rlss = float(np.max(np.abs(th_rlss)))

    summary = {
        "forcing": label,
        "model_B_closure": "isotropic_plane_strain",
        "model_B_shear_modulus_pa": float(m["model_b_shear_modulus_pa"]),
        "model_B_poisson_ratio": float(m["model_b_poisson_ratio"]),
        "model_B_fault_geometry": {
            "strike_deg": float(m["fault_strike_deg"]),
            "dip_deg": float(m["fault_dip_deg"]),
            "dip_direction_deg": float(m["fault_dip_direction_deg"]),
        },
        "thomas_reference_geometry": {
            "strike_deg": float(m.get("thomas_2012_reference_fault_strike_deg", 318.0)),
            "dip_deg": float(m.get("thomas_2012_reference_fault_dip_deg", 90.0)),
        },
        "max_abs_model_A": float(np.max(np.abs(dv_A))),
        "max_abs_model_B": float(np.max(np.abs(dv_B))),
        "max_abs_model_C_takano": float(np.max(np.abs(dv_C))),
        "max_abs_model_D_Vs": float(np.max(np.abs(dvs))),
        "max_abs_model_D_Vp": float(np.max(np.abs(dvp))),
        "max_abs_SAFOD_FNS_pa": max_fns,
        "max_abs_SAFOD_along_strike_shear_pa": max_shear,
        "SAFOD_FNS_to_shear_amplitude_ratio": float(max_fns / max_shear) if max_shear else np.inf,
        "max_abs_Thomas_FNS_pa": max_th_fns,
        "max_abs_Thomas_RLSS_pa": max_th_rlss,
        "Thomas_FNS_to_RLSS_amplitude_ratio": float(max_th_fns / max_th_rlss) if max_th_rlss else np.inf,
        "max_abs_selected_stress_pa": float(np.max(np.abs(selected))),
        "model_D_rho_c0": float(rho_c0),
        "model_D_sigma_hat_pa": float(sigma_hat),
        "model_D_baseline_Vp_m_s": float(vp0),
        "model_D_baseline_Vs_m_s": float(vs0),
    }
    return out, summary


def read_forcing(path):
    df = pd.read_csv(path, parse_dates=["time_utc"])
    needed = {"eps_NN", "eps_EE", "eps_NE"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing {sorted(missing)}")
    return df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "config.json"))
    p.add_argument("--pysolid", default=str(ROOT / "outputs/tides/pysolid_tides.csv"))
    p.add_argument("--spotl", default=str(ROOT / "outputs/tides/spotl_ertid_tides.csv"))
    p.add_argument("--output", default=str(ROOT / "outputs/tides/model_results.csv"))
    p.add_argument("--summary", default=str(ROOT / "outputs/tides/model_summary.json"))
    p.add_argument("--provenance", default=str(ROOT / "outputs/tides/model_provenance.json"))
    p.add_argument("--allow-missing-spotl", action="store_true")
    a = p.parse_args()

    cfg = load_config(a.config)

    py = read_forcing(a.pysolid)
    pyout, pysum = model_one_forcing(py, cfg, "pysolid")
    combined = pyout
    summaries = [pysum]

    spotl_path = Path(a.spotl)
    if spotl_path.exists():
        sp = read_forcing(spotl_path)
        spout, spsum = model_one_forcing(sp, cfg, "spotl")
        combined = pd.merge(combined, spout, on="time_utc", how="outer").sort_values("time_utc")
        summaries.append(spsum)
    elif not a.allow_missing_spotl:
        raise FileNotFoundError(
            f"{spotl_path} not found. Run run_spotl_ertid.py first "
            "or use --allow-missing-spotl only for local cached testing."
        )

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(a.output, index=False)
    write_json(a.summary, {
        "models": summaries,
        "primary_forcing": cfg["primary_forcing"],
        "model_B_note": (
            "Thomas et al. (2012) specify SPOTL strain -> linear elasticity -> vertical N42W fault resolution, "
            "but do not print the constitutive equation/numerical elastic constants in the Figure-3 methods paragraph. "
            "The explicit closure here follows the later Parkfield implementation of van der Elst et al. (2016): "
            "plane strain, nu=0.25, G=30 GPa by default. Thomas-reference and SAFOD-geometry tractions are both saved. "
            "The subsequent Niu stress -> dv/v multiplication remains a separate transfer assumption."
        ),
    })
    write_json(a.provenance, provenance_base(__file__, {
        "output": str(Path(a.output).resolve()),
        "forcings": [s["forcing"] for s in summaries],
        "model_parameters": cfg["model_parameters"],
    }))

    print(f"wrote model products to {a.output}")
    for s in summaries:
        print(s)


if __name__ == "__main__":
    main()
