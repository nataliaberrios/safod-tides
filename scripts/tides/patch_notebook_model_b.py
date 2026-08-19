#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path
import nbformat as nbf

from common import ROOT

NOTEBOOK = ROOT / "notebooks" / "SAFOD_tides_model_framework.ipynb"

MODEL_B_MD = r"""
# 3. Model B: strain → elastic stress → vertical-fault traction

Thomas et al. (2012) explicitly document the architecture

$$
\text{SPOTL strain}
\rightarrow
\text{linear elastic constitutive equation}
\rightarrow
\text{stress resolved onto a vertical SAF plane}.
$$

They use a **vertical plane striking N42°W** and plot fault-normal stress (FNS) and right-lateral shear stress (RLSS) in their Figure 3. Their methods paragraph does **not** state a plane-strain closure, a plane-stress closure, or the numerical elastic constants used in Figure 3.

The previous version of our Model B imposed plane strain and then projected the resulting tensor onto the approximately $70^\circ$-dipping SAF. That step is removed: the present tide products are surface horizontal strains, so a dipping receiver plane would require a defensible full 3-D stress tensor at depth.

## 3.1 Surface strain trace

For an isotropic traction-free surface,

$$
\sigma_{DD}=0,
$$

with the full isotropic constitutive law

$$
\sigma_{ij}=2\mu\varepsilon_{ij}
+\lambda\,\mathrm{tr}(\boldsymbol{\varepsilon})\delta_{ij}.
$$

The free-surface condition implies

$$
\varepsilon_{DD}
=-\frac{\nu}{1-\nu}
\left(\varepsilon_{NN}+\varepsilon_{EE}\right),
$$

and therefore

$$
\theta\equiv\mathrm{tr}(\boldsymbol{\varepsilon})
=\frac{1-2\nu}{1-\nu}
\left(\varepsilon_{NN}+\varepsilon_{EE}\right).
$$

This use of the traction-free boundary condition is only how we recover the **surface strain trace**. It is not a plane-strain assumption at depth.

The horizontal stresses required by a vertical receiver fault are then

$$
\sigma_{NN}=2\mu\varepsilon_{NN}+\lambda\theta,
$$

$$
\sigma_{EE}=2\mu\varepsilon_{EE}+\lambda\theta,
$$

$$
\sigma_{NE}=2\mu\varepsilon_{NE}.
$$

For a vertical fault with horizontal strike and normal vectors $\mathbf{s}$ and $\mathbf{n}$,

$$
\mathrm{FNS}=\mathbf{n}^{T}\boldsymbol{\sigma}_{h}\mathbf{n},
\qquad
\mathrm{RLSS}=\mathbf{s}^{T}\boldsymbol{\sigma}_{h}\mathbf{n}.
$$

The primary SAFOD branch uses a vertical N40°W receiver plane and the site-informed elastic scenario $E=51.9$ GPa, $\nu=0.24$. The approximately $70^\circ$ SW dip is retained as geologic context but is **not used in current Model B**. A true dipping-fault calculation is deferred until a full 3-D depth-dependent strain tensor is available.
""".strip()

FIG3_MD = r"""
## 3.2 Thomas et al. Figure 3 analogue for June 16–17, 2026

Thomas et al. Figure 3 shows FNS (blue) and RLSS (red) resolved onto a vertical N42°W San Andreas plane. Here we compute the same two stress components for our SAFOD experiment window.

This is a **Figure-3-style analogue**, not a claim of exact numerical reproduction of their 2001 curve. Thomas et al. state that the elastic parameters used for Figure 3 were equivalent to the top layer of the Harkrider continental-shield model but do not tabulate them in paragraph 13. The benchmark therefore uses explicit $\mu=30$ GPa and $\nu=0.25$ values and labels them as a benchmark; Thomas et al. use those values elsewhere in the same paper, but that does not prove they are the exact Figure-3 constants.

Our present curve is body tide only. Thomas et al. included ocean loading but report that the body-tide contribution dominates inland and that FNS is roughly an order of magnitude larger than RLSS.
""".strip()

FIG3_CODE = r'''
if models is None:
    print("No model results yet. Run: bash RUN_ON_SHERLOCK.sh")
else:
    available = []
    for forcing in ["pysolid", "spotl"]:
        fns_col = f"{forcing}_thomas_FNS_pa"
        rlss_col = f"{forcing}_thomas_RLSS_pa"
        if fns_col in models.columns and rlss_col in models.columns:
            available.append(forcing)
            good = models[["time_utc", fns_col, rlss_col]].dropna()
            plt.figure(figsize=(11,5))
            plt.plot(good.time_utc, good[fns_col]/1000.0,
                     color="navy", linewidth=1.7, label="FNS")
            plt.plot(good.time_utc, good[rlss_col]/1000.0,
                     color="red", linewidth=1.5, label="RLSS")
            plt.axhline(0, color="black", linewidth=.8)
            plt.ylabel("Tidally induced stress (kPa)")
            plt.xlabel("UTC")
            plt.title(f"Thomas et al. (2012) Figure-3-style analogue — {forcing}")
            plt.grid(alpha=.25); plt.legend()
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=3))
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout(); plt.show()

    if not available:
        print("Thomas-analogue columns are absent. Pull latest code and rerun run_models.py.")
    else:
        rows=[]
        for forcing in available:
            fns=np.nanmax(np.abs(models[f"{forcing}_thomas_FNS_pa"]))
            rlss=np.nanmax(np.abs(models[f"{forcing}_thomas_RLSS_pa"]))
            rows.append({
                "forcing": forcing,
                "max |FNS| (kPa)": fns/1000.0,
                "max |RLSS| (kPa)": rlss/1000.0,
                "FNS/RLSS amplitude ratio": fns/rlss,
            })
        display(pd.DataFrame(rows).style.format({
            "max |FNS| (kPa)":"{:.3f}",
            "max |RLSS| (kPa)":"{:.3f}",
            "FNS/RLSS amplitude ratio":"{:.1f}",
        }))
'''.strip()

PRIMARY_MD = r"""
## 3.3 Primary SAFOD Model B and the Niu transfer

The Thomas analogue is a literature benchmark. The primary SAFOD calculation uses the site-informed elastic scenario and a vertical N40°W receiver plane.

FNS is stored positive in **tension/unclamping** to preserve the Thomas convention. For the pressure-like Niu transfer we define

$$
\Delta\sigma_B=-\mathrm{FNS},
$$

so positive $\Delta\sigma_B$ means fault-normal compression, and calculate

$$
\left(\frac{\Delta v}{v}\right)_B
=S_{\mathrm{Niu}}\Delta\sigma_B,
\qquad
S_{\mathrm{Niu}}=2.4\times10^{-7}\ \mathrm{Pa}^{-1}.
$$

That last multiplication is **our transfer assumption**. Niu et al. measured a local SAFOD barometric-pressure sensitivity; they did not publish a universal tidal FNS sensitivity. The code therefore also saves the alternative RLSS $\rightarrow$ Niu result as a sensitivity branch.
""".strip()

PRIMARY_CODE = r'''
if models is not None:
    for forcing in ["pysolid", "spotl"]:
        fns = f"{forcing}_FNS_tension_pa"
        rlss = f"{forcing}_RLSS_pa"
        if fns in models.columns and rlss in models.columns:
            good=models[["time_utc", fns, rlss]].dropna()
            plt.figure(figsize=(11,5))
            plt.plot(good.time_utc, good[fns]/1000.0, label="FNS (tension +)")
            plt.plot(good.time_utc, good[rlss]/1000.0, label="RLSS")
            plt.axhline(0, linewidth=.8)
            plt.ylabel("Stress perturbation (kPa)")
            plt.xlabel("UTC")
            plt.title(f"Revised Model B — vertical SAFOD receiver plane ({forcing})")
            plt.grid(alpha=.25); plt.legend()
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=3))
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            plt.xticks(rotation=30,ha="right"); plt.tight_layout(); plt.show()
'''.strip()

CAVEAT_MD = r"""
## 3.4 Mechanical scope of Model B

The revised Model B is intentionally narrower than the old calculation:

$$
\boxed{
\text{surface body-tide strain}
\rightarrow
\text{surface-derived horizontal elastic stress}
\rightarrow
\text{vertical SAF traction}
}
$$

It is sufficient for the Thomas-Figure-3-style FNS/RLSS diagnostic and avoids pretending that we know the full stress tensor on a $70^\circ$-dipping plane at approximately 1 km depth.

A rigorous dipping-fault calculation should instead start from a **full 3-D depth-dependent strain tensor** and then apply isotropic or anisotropic elasticity at depth. That is the next mechanical refinement, not another arbitrary plane-stress/plane-strain closure.
""".strip()

AWD_MD = r"""
# 4. Models A–D and AWD sensitivity context

Model A is the Niu 240-Pa amplitude shortcut. Model B is the explicit elastic-stress calculation above followed by the Niu transfer. Model C applies direct strain sensitivities from other sites as context. Model D uses a stress-dependent crack-compliance model.

The AWD comparison uses the **current synthetic injection–recovery benchmark**, defined as the imposed change in apparent along-fiber speed required for the method to recover the **correct direction in 90% of tests**. These thresholds are sensitivity limits measured by injecting synthetic changes into real field variability; they are **not measured natural velocity changes**.

For the **full usable cable**:

- Nano: **0.55%** (95% interval: 0.40–0.81%)
- Deep outbound: **0.40%** (0.28–0.48%)
- Deep return: **0.68%** (0.54–0.81%)

For the matched **700 m cable-length comparison**, Nano is **0.55%** (0.41–0.81%), while both Deep branches are **greater than 2%** because neither reached 90% correct-direction recovery within the tested range ending at 2%. “Greater than 2%” is a lower bound, not a threshold equal to 2%.

Deep outbound has the lowest full-cable point estimate, but Nano and Deep outbound cannot be confidently ranked because their uncertainty overlaps in the formal paired comparison. Deep outbound is more sensitive than Deep return.

The table below uses the **full-cable Deep outbound 90%-correct-recovery threshold of 0.40%** as the single observational benchmark against which the model amplitudes are compared.

No branch constitutes a tidal detection.
""".strip()

AWD_CODE = r'''
if models is not None:
    benchmark = CONFIG["awd_benchmarks"]["full_cable"]["deep_outbound"]
    deep90 = benchmark["threshold"]
    summary_rows=[]
    for forcing in ["pysolid","spotl"]:
        mapping={
            "A":f"{forcing}_model_A_dv_over_v",
            "B":f"{forcing}_model_B_dv_over_v",
            "C (Takano)":f"{forcing}_model_C_takano_dv_over_v",
            "D (Vs)":f"{forcing}_model_D_dVs_over_Vs",
            "D (Vp)":f"{forcing}_model_D_dVp_over_Vp",
        }
        if all(col in models.columns for col in mapping.values()):
            for name,col in mapping.items():
                amp=np.nanmax(np.abs(models[col]))
                summary_rows.append({
                    "forcing":forcing,
                    "model":name,
                    "max_abs_dv/v":amp,
                    "max_abs_percent":100*amp,
                    "Deep outbound 90% threshold / model":deep90/amp,
                })
    summary=pd.DataFrame(summary_rows)
    print(
        "AWD benchmark: full-cable Deep outbound 90%-correct-direction threshold "
        f"= {100*deep90:.2f}% "
        f"(95% interval {100*benchmark['ci95_low']:.2f}–{100*benchmark['ci95_high']:.2f}%)."
    )
    display(summary.style.format({
        "max_abs_dv/v":"{:.3e}",
        "max_abs_percent":"{:.5f}",
        "Deep outbound 90% threshold / model":"{:.1f}x",
    }))
'''.strip()


def main():
    if not NOTEBOOK.exists():
        raise FileNotFoundError(NOTEBOOK)

    nb = nbf.read(NOTEBOOK, as_version=4)
    fig3_code_done = False
    primary_code_done = False
    awd_code_done = False

    for cell in nb.cells:
        src = cell.get("source", "")
        if cell.cell_type == "markdown" and src.lstrip().startswith("# 3. Model B:"):
            cell.source = MODEL_B_MD
        elif cell.cell_type == "markdown" and "Thomas et al. Figure 3 analogue" in src:
            cell.source = FIG3_MD
        elif cell.cell_type == "code" and "thomas_FNS_pa" in src and "thomas_RLSS_pa" in src:
            if not fig3_code_done:
                cell.source = FIG3_CODE
                fig3_code_done = True
        elif cell.cell_type == "markdown" and "## 3.2 Primary SAFOD Model B geometry" in src:
            cell.source = PRIMARY_MD
        elif cell.cell_type == "code" and ("spotl_FNS_pa" in src or "along_strike_shear_pa" in src):
            if not primary_code_done:
                cell.source = PRIMARY_CODE
                primary_code_done = True
        elif cell.cell_type == "markdown" and src.lstrip().startswith("# 4. Models A–D and AWD"):
            cell.source = AWD_MD
        elif cell.cell_type == "code" and ("Deep reliable / model" in src or "deep_outbound_reliable" in src):
            if not awd_code_done:
                cell.source = AWD_CODE
                awd_code_done = True

    if not any(c.cell_type == "markdown" and "## 3.4 Mechanical scope of Model B" in c.source for c in nb.cells):
        insert_at = None
        for i, cell in enumerate(nb.cells):
            if cell.cell_type == "code" and "Revised Model B" in cell.source:
                insert_at = i + 1
                break
        if insert_at is not None:
            nb.cells.insert(insert_at, nbf.v4.new_markdown_cell(CAVEAT_MD))

    nbf.write(nb, NOTEBOOK)
    print(f"Updated Model B / Thomas Figure 3 / AWD sensitivity sections in {NOTEBOOK}")


if __name__ == "__main__":
    main()
