#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json


def lame_from_E_nu(E, nu):
    """Lamé parameters for isotropic linear elasticity."""
    mu = E / (2.0 * (1.0 + nu))
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return lam, mu


def surface_complete_strain_and_stress(enn, eee, ene, E, nu):
    """
    Complete the *surface* strain tensor using the traction-free radial
    boundary condition and apply full 3-D isotropic Hooke's law.

    Inputs are tensor strains in a local N/E/U frame, U positive upward.

    Assumptions:
      sigma_UU = sigma_NU = sigma_EU = 0 at the free surface.
      isotropic, homogeneous linear elasticity for the constitutive conversion.

    The radial strain is therefore
        eps_UU = -lambda/(lambda+2mu) * (eps_NN + eps_EE)
               = -nu/(1-nu) * (eps_NN + eps_EE).

    The resulting horizontal stress components are algebraically identical
    to the familiar plane-stress formulas.  We write the calculation this
    way so the physical boundary condition and the missing vertical strain
    are explicit rather than silently calling the subsurface Earth
    "plane stress".
    """
    lam, mu = lame_from_E_nu(E, nu)

    enn = np.asarray(enn, float)
    eee = np.asarray(eee, float)
    ene = np.asarray(ene, float)

    euu = -(lam / (lam + 2.0 * mu)) * (enn + eee)
    trace = enn + eee + euu

    snn = lam * trace + 2.0 * mu * enn
    see = lam * trace + 2.0 * mu * eee
    suu = lam * trace + 2.0 * mu * euu
    sne = 2.0 * mu * ene
    snu = np.zeros_like(snn)
    seu = np.zeros_like(snn)

    return {
        "eps_UU": euu,
        "sigma_NN": snn,
        "sigma_EE": see,
        "sigma_UU": suu,
        "sigma_NE": sne,
        "sigma_NU": snu,
        "sigma_EU": seu,
    }


def resolve_vertical_strike_slip_fault(snn, see, sne, strike_deg):
    """
    Resolve horizontal stress onto a VERTICAL strike-slip fault.

    strike_deg is clockwise from north.  For a NW-striking San Andreas
    orientation (e.g. N42W = 318 deg), the chosen normal points to the
    southwest side of the fault and +strike points northwest.  With this
    convention:

      FNS  > 0  : fault-normal tension / unclamping
      RLSS > 0  : right-lateral shear

    This mirrors the sign language used by Thomas et al. (2012).

    Because the plane is vertical, FNS and strike-parallel shear depend only
    on the horizontal stress tensor.  We deliberately do NOT use this
    surface stress tensor to resolve traction onto the ~70-deg dipping SAFOD
    plane; that requires a defensible subsurface 3-D stress tensor.
    """
    a = np.deg2rad(float(strike_deg))

    sN, sE = np.cos(a), np.sin(a)
    nN, nE = np.sin(a), -np.cos(a)

    fns = snn * nN**2 + 2.0 * sne * nN * nE + see * nE**2
    rlss = (
        sN * (snn * nN + sne * nE)
        + sE * (sne * nN + see * nE)
    )

    fns = fns - np.nanmean(fns)
    rlss = rlss - np.nanmean(rlss)
    return fns, rlss


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

    # Model A: published Niu 240-Pa amplitude shortcut.
    stress_A = m["niu_tidal_stress_scale_pa"] * shape
    dv_A = m["niu_stress_sensitivity_pa_inv"] * stress_A

    # Model B: Thomas-style stress construction.
    # Thomas et al. (2012) compute tidal strains, convert strain to stress
    # with a linear elastic constitutive equation, and resolve the stress
    # onto a vertical SAF plane striking N42W. Their paper does not state
    # a "plane stress" assumption. Here we make the surface closure
    # explicit: the tide package supplies horizontal surface strain, the
    # free-surface condition supplies eps_UU, then full 3-D Hooke's law is
    # applied. For a vertical fault only the horizontal stresses enter
    # FNS and RLSS.
    #
    # This is a surface/long-wavelength Thomas-style benchmark. It is NOT
    # claimed to be the exact 3-D stress tensor at ~1 km depth.
    surf = surface_complete_strain_and_stress(
        enn, eee, ene,
        m["youngs_modulus_pa"],
        m["poisson_ratio"],
    )

    strike = m.get("model_b_vertical_fault_strike_deg", 318.0)
    fns, rlss = resolve_vertical_strike_slip_fault(
        surf["sigma_NN"],
        surf["sigma_EE"],
        surf["sigma_NE"],
        strike,
    )

    # Niu's coefficient is an empirical barometric stress sensitivity.
    # Applying it to tidal FNS is OUR transfer assumption, not a published
    # statement by Niu et al.
    niu_component = m.get("model_b_niu_component", "FNS").upper()
    if niu_component == "FNS":
        selected_B = fns
    elif niu_component == "RLSS":
        selected_B = rlss
    else:
        raise ValueError("model_b_niu_component must be 'FNS' or 'RLSS'")

    dv_B = m["niu_stress_sensitivity_pa_inv"] * selected_B

    # Model C: direct strain-sensitivity transfers (context only).
    dv_C = -m["takano_strain_sensitivity"] * centered
    dv_C_sheng = -m["sheng_strain_sensitivity"] * centered

    # Model D: mechanistic crack closure. Crack closure responds to
    # compression. Thomas FNS is positive in tension, so -FNS is the
    # compression-positive perturbation here.
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
    compression_positive = -fns
    rc = rho_c0 * np.exp(-compression_positive / sigma_hat)
    vp, vs = vel(rc)
    dvp = (vp - vp0) / vp0
    dvs = (vs - vs0) / vs0

    fns_amp = float(np.max(np.abs(fns)))
    rlss_amp = float(np.max(np.abs(rlss)))
    ratio = np.inf if rlss_amp == 0 else fns_amp / rlss_amp

    out = pd.DataFrame({
        "time_utc": df.time_utc,
        f"{label}_areal_strain": areal,
        f"{label}_model_A_stress_pa": stress_A,
        f"{label}_model_A_dv_over_v": dv_A,
        f"{label}_eps_UU_surface_closure": surf["eps_UU"],
        f"{label}_sigma_NN_pa": surf["sigma_NN"],
        f"{label}_sigma_EE_pa": surf["sigma_EE"],
        f"{label}_sigma_UU_pa": surf["sigma_UU"],
        f"{label}_sigma_NE_pa": surf["sigma_NE"],
        f"{label}_FNS_tension_pa": fns,
        f"{label}_RLSS_right_lateral_pa": rlss,
        # Back-compatible aliases, now using Thomas sign conventions.
        f"{label}_fault_normal_pa": fns,
        f"{label}_fault_shear_pa": rlss,
        f"{label}_model_B_stress_pa": selected_B,
        f"{label}_model_B_dv_over_v": dv_B,
        f"{label}_model_C_takano_dv_over_v": dv_C,
        f"{label}_model_C_sheng_dv_over_v": dv_C_sheng,
        f"{label}_model_D_compression_positive_pa": compression_positive,
        f"{label}_model_D_crack_density": rc,
        f"{label}_model_D_Vp_m_s": vp,
        f"{label}_model_D_Vs_m_s": vs,
        f"{label}_model_D_dVp_over_Vp": dvp,
        f"{label}_model_D_dVs_over_Vs": dvs,
    })

    summary = {
        "forcing": label,
        "model_B_method": (
            "Thomas-style vertical-SAF stress benchmark: horizontal surface "
            "strain + explicit free-surface completion + 3-D isotropic Hooke "
            "law + resolution onto vertical strike-slip plane"
        ),
        "model_B_vertical_fault_strike_deg": float(strike),
        "model_B_FNS_sign": "positive=tension/unclamping",
        "model_B_RLSS_sign": "positive=right-lateral",
        "model_B_niu_transfer_component": niu_component,
        "max_abs_model_A": float(np.max(np.abs(dv_A))),
        "max_abs_model_B": float(np.max(np.abs(dv_B))),
        "max_abs_model_C_takano": float(np.max(np.abs(dv_C))),
        "max_abs_model_D_Vs": float(np.max(np.abs(dvs))),
        "max_abs_model_D_Vp": float(np.max(np.abs(dvp))),
        "max_abs_FNS_pa": fns_amp,
        "max_abs_RLSS_pa": rlss_amp,
        "FNS_to_RLSS_amplitude_ratio": float(ratio),
        "max_abs_sigma_UU_surface_check_pa": float(np.max(np.abs(surf["sigma_UU"]))),
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
        combined = pd.merge(
            combined, spout, on="time_utc", how="outer"
        ).sort_values("time_utc")
        summaries.append(spsum)
    elif not a.allow_missing_spotl:
        raise FileNotFoundError(
            f"{spotl_path} not found. Run run_spotl_ertid.py first "
            "or use --allow-missing-spotl only for local testing."
        )

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(a.output, index=False)
    write_json(a.summary, {
        "models": summaries,
        "primary_forcing": cfg["primary_forcing"],
    })
    write_json(a.provenance, provenance_base(__file__, {
        "output": str(Path(a.output).resolve()),
        "forcings": [s["forcing"] for s in summaries],
        "model_parameters": cfg["model_parameters"],
        "important_model_B_limitation": (
            "The Thomas-style benchmark is a surface/long-wavelength vertical-"
            "fault stress construction. It is not the full 3-D tidal stress "
            "tensor at the ~1 km SAFOD DAS depth and is not projected onto the "
            "70-deg dipping plane."
        ),
    }))

    print(f"wrote model products to {a.output}")
    for s in summaries:
        print(s)


if __name__ == "__main__":
    main()
