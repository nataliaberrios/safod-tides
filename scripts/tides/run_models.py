#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from common import ROOT, load_config, provenance_base, write_json


def elastic_moduli_from_E_nu(E_pa, nu):
    E = float(E_pa)
    nu = float(nu)
    if E <= 0:
        raise ValueError("Young modulus must be positive.")
    if not (-1.0 < nu < 0.5):
        raise ValueError("Poisson ratio must lie between -1 and 0.5.")
    mu = E / (2.0 * (1.0 + nu))
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return lam, mu


def elastic_moduli_from_mu_nu(mu_pa, nu):
    mu = float(mu_pa)
    nu = float(nu)
    if mu <= 0:
        raise ValueError("Shear modulus must be positive.")
    if not (-1.0 < nu < 0.5):
        raise ValueError("Poisson ratio must lie between -1 and 0.5.")
    E = 2.0 * mu * (1.0 + nu)
    lam = 2.0 * mu * nu / (1.0 - 2.0 * nu)
    return E, lam, mu


def surface_volume_strain_from_horizontal(enn, eee, nu):
    """Infer tr(eps) for an isotropic traction-free surface.

    At the free surface sigma_DD = 0. Isotropic Hooke law then gives

        eps_DD = -nu/(1-nu) * (eps_NN + eps_EE)

    and therefore

        tr(eps) = (1-2nu)/(1-nu) * (eps_NN + eps_EE).

    This is a surface relation. It is not a plane-strain assumption and it is
    not claimed to be the exact 3-D strain tensor at ~1 km depth.
    """
    nu = float(nu)
    enn = np.asarray(enn, dtype=float)
    eee = np.asarray(eee, dtype=float)
    return ((1.0 - 2.0 * nu) / (1.0 - nu)) * (enn + eee)


def horizontal_stress_from_surface_strain(enn, eee, ene, E_pa, nu):
    """Horizontal stress from surface strain using 3-D isotropic Hooke law.

    Only the surface strain trace is inferred from the traction-free boundary
    condition. The constitutive law itself is the full isotropic relation

        sigma_ij = 2 mu eps_ij + lambda tr(eps) delta_ij.

    For a vertical receiver fault, fault-normal and strike-parallel tractions
    require only sigma_NN, sigma_EE, and sigma_NE. We therefore do not invent
    an underground vertical stress tensor in order to project onto a dipping
    fault.

    Stress sign convention: positive=tension. ``ene`` is tensor shear strain.
    """
    lam, mu = elastic_moduli_from_E_nu(E_pa, nu)
    enn = np.asarray(enn, dtype=float)
    eee = np.asarray(eee, dtype=float)
    ene = np.asarray(ene, dtype=float)

    theta = surface_volume_strain_from_horizontal(enn, eee, nu)
    edd = theta - enn - eee

    snn = 2.0 * mu * enn + lam * theta
    see = 2.0 * mu * eee + lam * theta
    sne = 2.0 * mu * ene
    sdd = 2.0 * mu * edd + lam * theta
    return snn, see, sne, sdd, theta, edd


def vertical_fault_tractions(snn, see, sne, strike_deg):
    """Resolve horizontal stress onto a vertical strike-slip receiver fault.

    Coordinates are North/East. Strike is clockwise from north. The horizontal
    normal is chosen 90 degrees clockwise from +strike. FNS is positive in
    tension/unclamping. Along-strike shear is positive in the +strike direction
    on the +normal face. With Thomas et al.'s N42W convention this is the
    right-lateral shear-stress (RLSS) sign convention used here.
    """
    a = np.deg2rad(float(strike_deg))
    s = np.array([np.cos(a), np.sin(a)])
    n = np.array([-np.sin(a), np.cos(a)])

    snn = np.asarray(snn, dtype=float)
    see = np.asarray(see, dtype=float)
    sne = np.asarray(sne, dtype=float)

    sigma = np.zeros((len(snn), 2, 2), dtype=float)
    sigma[:, 0, 0] = snn
    sigma[:, 1, 1] = see
    sigma[:, 0, 1] = sigma[:, 1, 0] = sne

    traction = np.einsum("tij,j->ti", sigma, n)
    fns = np.einsum("ti,i->t", traction, n)
    shear = np.einsum("ti,i->t", traction, s)

    fns -= np.mean(fns)
    shear -= np.mean(shear)
    return fns, shear


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

    # Model B -- Thomas-style architecture:
    # surface body-tide strain -> linear isotropic elasticity -> VERTICAL fault traction.
    #
    # The previous 70-degree dipping-fault / plane-strain calculation is removed.
    # A dipping receiver plane requires a defensible full 3-D stress tensor at depth;
    # the present tide products are surface horizontal strains.
    snn, see, sne, sdd, theta, edd = horizontal_stress_from_surface_strain(
        enn,
        eee,
        ene,
        m["model_b_youngs_modulus_pa"],
        m["model_b_poisson_ratio"],
    )
    fns, rlss = vertical_fault_tractions(
        snn,
        see,
        sne,
        m["model_b_vertical_strike_deg"],
    )
    fns_compression = -fns

    # Thomas et al. (2012) Figure-3-style reference calculation for our times.
    # Their paragraph 13 specifies linear elasticity + a vertical N42W plane but
    # does not tabulate the exact Figure-3 elastic constants. The benchmark below
    # therefore uses explicit, labeled values rather than pretending to reproduce
    # an undocumented parameter choice.
    th = cfg["thomas_figure3_analogue"]
    th_E, _, _ = elastic_moduli_from_mu_nu(
        th["shear_modulus_pa"],
        th["poisson_ratio"],
    )
    th_snn, th_see, th_sne, th_sdd, th_theta, _ = horizontal_stress_from_surface_strain(
        enn,
        eee,
        ene,
        th_E,
        th["poisson_ratio"],
    )
    th_fns, th_rlss = vertical_fault_tractions(
        th_snn,
        th_see,
        th_sne,
        th["vertical_strike_deg"],
    )

    # Niu barometric stress sensitivity -> tidal stress is OUR transfer assumption.
    # The primary branch uses compression-positive FNS because Niu's measured
    # coefficient is a pressure-like loading sensitivity. The RLSS transfer is
    # retained as a sensitivity calculation rather than silently discarded.
    S_niu = m["niu_stress_sensitivity_pa_inv"]
    dv_B = S_niu * fns_compression
    dv_B_rlss = S_niu * rlss

    # Model C -- direct foreign-site strain-sensitivity transfers.
    dv_C = -m["takano_strain_sensitivity"] * centered
    dv_C_sheng = -m["sheng_strain_sensitivity"] * centered

    # Model D -- mechanistic crack closure, driven by the same compression-positive
    # stress used by the primary Model B branch.
    Kh, muh = host_moduli(m["model_d_host_E_pa"], m["model_d_host_nu"])
    nuh = (3.0 * Kh - 2.0 * muh) / (6.0 * Kh + 2.0 * muh)
    Ak = 16.0 * (1.0 - nuh**2) / (9.0 * (1.0 - 2.0 * nuh))
    Amu = 32.0 * (1.0 - nuh) * (5.0 - nuh) / (45.0 * (2.0 - nuh))
    rho = m["model_d_density_kg_m3"]
    mu_target = rho * m["model_d_target_Vs_m_s"]**2
    rho_c0 = (muh / mu_target - 1.0) / Amu
    pref = 0.5 * (Amu * rho_c0) / (1.0 + Amu * rho_c0)
    sigma_hat = pref / S_niu

    def vel(rc):
        K = Kh / (1.0 + Ak * rc)
        mu = muh / (1.0 + Amu * rc)
        vp = np.sqrt((K + 4.0 * mu / 3.0) / rho)
        vs = np.sqrt(mu / rho)
        return vp, vs

    vp0, vs0 = vel(rho_c0)
    rc = rho_c0 * np.exp(-fns_compression / sigma_hat)
    vp, vs = vel(rc)
    dvp = (vp - vp0) / vp0
    dvs = (vs - vs0) / vs0

    out = pd.DataFrame({
        "time_utc": df.time_utc,
        f"{label}_areal_strain": areal,
        f"{label}_model_A_stress_pa": stress_A,
        f"{label}_model_A_dv_over_v": dv_A,
        # Surface-derived trace and stress used by Model B.
        f"{label}_surface_volume_strain_used": theta,
        f"{label}_surface_eps_DD_inferred": edd,
        f"{label}_sigma_NN_pa": snn,
        f"{label}_sigma_EE_pa": see,
        f"{label}_sigma_NE_pa": sne,
        f"{label}_sigma_DD_check_pa": sdd,
        # Primary vertical-fault Model B stresses.
        f"{label}_FNS_tension_pa": fns,
        f"{label}_FNS_compression_pa": fns_compression,
        f"{label}_RLSS_pa": rlss,
        f"{label}_model_B_dv_over_v": dv_B,
        f"{label}_model_B_dv_over_v_RLSS_sensitivity": dv_B_rlss,
        # Thomas et al. Figure-3-style analogue for the same forcing times.
        f"{label}_thomas_FNS_pa": th_fns,
        f"{label}_thomas_RLSS_pa": th_rlss,
        f"{label}_thomas_surface_volume_strain_used": th_theta,
        f"{label}_thomas_sigma_DD_check_pa": th_sdd,
        # Backward-compatible aliases.
        f"{label}_fault_normal_pa": fns_compression,
        f"{label}_fault_shear_pa": rlss,
        # Models C/D.
        f"{label}_model_C_takano_dv_over_v": dv_C,
        f"{label}_model_C_sheng_dv_over_v": dv_C_sheng,
        f"{label}_model_D_crack_density": rc,
        f"{label}_model_D_Vp_m_s": vp,
        f"{label}_model_D_Vs_m_s": vs,
        f"{label}_model_D_dVp_over_Vp": dvp,
        f"{label}_model_D_dVs_over_Vs": dvs,
    })

    max_fns = float(np.max(np.abs(fns)))
    max_rlss = float(np.max(np.abs(rlss)))
    max_th_fns = float(np.max(np.abs(th_fns)))
    max_th_rlss = float(np.max(np.abs(th_rlss)))

    summary = {
        "forcing": label,
        "model_B_closure": "surface strain trace + 3-D isotropic Hooke law + vertical receiver fault",
        "model_B_youngs_modulus_pa": float(m["model_b_youngs_modulus_pa"]),
        "model_B_poisson_ratio": float(m["model_b_poisson_ratio"]),
        "model_B_vertical_strike_deg": float(m["model_b_vertical_strike_deg"]),
        "model_B_dipping_fault_not_used": True,
        "max_abs_model_A": float(np.max(np.abs(dv_A))),
        "max_abs_model_B": float(np.max(np.abs(dv_B))),
        "max_abs_model_B_RLSS_sensitivity": float(np.max(np.abs(dv_B_rlss))),
        "max_abs_model_C_takano": float(np.max(np.abs(dv_C))),
        "max_abs_model_D_Vs": float(np.max(np.abs(dvs))),
        "max_abs_model_D_Vp": float(np.max(np.abs(dvp))),
        "max_abs_FNS_pa": max_fns,
        "max_abs_RLSS_pa": max_rlss,
        "FNS_to_RLSS_amplitude_ratio": float(max_fns / max_rlss) if max_rlss else np.inf,
        "max_abs_Thomas_analogue_FNS_pa": max_th_fns,
        "max_abs_Thomas_analogue_RLSS_pa": max_th_rlss,
        "Thomas_analogue_FNS_to_RLSS_ratio": float(max_th_fns / max_th_rlss) if max_th_rlss else np.inf,
        "max_abs_sigma_DD_surface_check_pa": float(np.max(np.abs(sdd))),
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
            "or use --allow-missing-spotl only for local testing."
        )

    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(a.output, index=False)
    write_json(a.summary, {
        "models": summaries,
        "primary_forcing": cfg["primary_forcing"],
        "model_B_note": (
            "Model B no longer uses plane strain or projects a surface-derived tensor onto the 70-degree dipping fault. "
            "It follows the part of Thomas et al. (2012) that is documented: surface body-tide strain is treated as "
            "representative at depth, converted with linear isotropic elasticity, and resolved onto a vertical SAF plane. "
            "The free-surface condition is used only to recover the surface volumetric strain/trace needed by Hooke law. "
            "The Niu barometric stress-sensitivity -> tidal FNS-compression multiplication remains a separate transfer "
            "assumption. A true 70-degree depth projection is deferred until a full 3-D depth-dependent strain tensor is available."
        ),
        "thomas_figure3_note": cfg["thomas_figure3_analogue"]["note"],
    })
    write_json(a.provenance, provenance_base(__file__, {
        "output": str(Path(a.output).resolve()),
        "forcings": [s["forcing"] for s in summaries],
        "model_parameters": cfg["model_parameters"],
        "thomas_figure3_analogue": cfg["thomas_figure3_analogue"],
    }))

    print(f"wrote model products to {a.output}")
    for s in summaries:
        print(s)


if __name__ == "__main__":
    main()
