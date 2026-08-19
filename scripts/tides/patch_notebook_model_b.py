#!/usr/bin/env python
from __future__ import annotations

import nbformat as nbf

from common import ROOT

NOTEBOOK = ROOT / "notebooks" / "SAFOD_tides_model_framework.ipynb"

MODEL_B_MD = r"""
# 3. Model B: calculated tide → elastic stress → empirical SAFOD velocity response

The tide calculation and the velocity-response calculation are separate pieces of the reasoning chain. Model B uses

$$
\boxed{
\text{Sun/Moon}
\rightarrow
\boldsymbol{\varepsilon}(t)
\rightarrow
\boldsymbol{\sigma}(t)
\rightarrow
\text{vertical-SAF fault-normal stress}
\rightarrow
S_{\mathrm{Niu}}
\rightarrow
\Delta v/v
}
$$

The first arrows are calculated explicitly for the June 16–17, 2026 SAFOD window. PySolid and SPOTL provide the tidal strain forcing. Linear elasticity converts that strain to stress, and the stress is resolved onto a vertical receiver plane at the local SAF strike.

The final arrow is empirical rather than mechanical: we apply the SAFOD stress sensitivity reported by Niu et al. (2008) to the calculated fault-normal stress. Niu measured a velocity response to barometric loading, not to tidal fault-normal stress, so this cross-loading transfer is an explicit assumption.

Thomas et al. (2012) provide a useful check on the strain → stress → vertical-fault-traction part of the chain. They use a vertical plane striking N42°W and plot fault-normal stress (FNS) and right-lateral shear stress (RLSS) in their Figure 3.

## 3.1 Surface strain trace and elastic stress

For an isotropic traction-free surface,

$$
\sigma_{DD}=0,
$$

with

$$
\sigma_{ij}=2\mu\varepsilon_{ij}
+\lambda\,\mathrm{tr}(\boldsymbol{\varepsilon})\delta_{ij}.
$$

The free-surface condition gives

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

The required horizontal stresses are

$$
\sigma_{NN}=2\mu\varepsilon_{NN}+\lambda\theta,
\qquad
\sigma_{EE}=2\mu\varepsilon_{EE}+\lambda\theta,
\qquad
\sigma_{NE}=2\mu\varepsilon_{NE}.
$$

For a vertical fault with horizontal strike and normal vectors $\mathbf{s}$ and $\mathbf{n}$,

$$
\mathrm{FNS}=\mathbf{n}^{T}\boldsymbol{\sigma}_{h}\mathbf{n},
\qquad
\mathrm{RLSS}=\mathbf{s}^{T}\boldsymbol{\sigma}_{h}\mathbf{n}.
$$

The primary SAFOD branch uses a vertical N40°W receiver plane and $E=51.9$ GPa, $\nu=0.24$. The approximately $70^\circ$ SW dip is retained only as geologic context. A dipping-fault traction calculation requires a defensible full 3-D depth-dependent strain tensor and is not attempted here.
""".strip()

FIG3_MD = r"""
## 3.2 Thomas et al. Figure 3 analogue for June 16–17, 2026

Thomas et al. (2012) explicitly use the architecture

$$
\boxed{
\text{SPOTL surface tidal strain}
\rightarrow
\text{linear elasticity}
\rightarrow
\text{stress on a vertical N42°W SAF plane}
\rightarrow
\mathrm{FNS},\mathrm{RLSS}
}
$$

Here we compute the same two stress components for the June 2026 SAFOD experiment window as a **Figure-3-style analogue**. This is not an exact reproduction of their 2001 curve. Their methods do not tabulate all elastic constants used in Figure 3, and the present calculation is body tide only.
""".strip()

FIG3_CODE = r'''
if models is None:
    print("No model results yet. Run: bash RUN_ON_SHERLOCK.sh")
else:
    available=[]
    for forcing in ["pysolid", "spotl"]:
        fns_col=f"{forcing}_thomas_FNS_pa"
        rlss_col=f"{forcing}_thomas_RLSS_pa"
        if fns_col in models.columns and rlss_col in models.columns:
            available.append(forcing)
            good=models[["time_utc",fns_col,rlss_col]].dropna()
            plt.figure(figsize=(11,5))
            plt.plot(good.time_utc,good[fns_col]/1000.0,color="navy",linewidth=1.7,label="FNS")
            plt.plot(good.time_utc,good[rlss_col]/1000.0,color="red",linewidth=1.5,label="RLSS")
            plt.axhline(0,color="black",linewidth=.8)
            plt.ylabel("Tidally induced stress (kPa)")
            plt.xlabel("UTC")
            plt.title(f"Thomas et al. (2012) Figure-3-style analogue — {forcing}")
            plt.grid(alpha=.25); plt.legend()
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=3))
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            plt.xticks(rotation=30,ha="right"); plt.tight_layout(); plt.show()
    if available:
        rows=[]
        for forcing in available:
            fns=np.nanmax(np.abs(models[f"{forcing}_thomas_FNS_pa"]))
            rlss=np.nanmax(np.abs(models[f"{forcing}_thomas_RLSS_pa"]))
            rows.append({"forcing":forcing,"max |FNS| (kPa)":fns/1000.0,
                         "max |RLSS| (kPa)":rlss/1000.0,
                         "FNS/RLSS amplitude ratio":fns/rlss})
        display(pd.DataFrame(rows).style.format({
            "max |FNS| (kPa)":"{:.3f}","max |RLSS| (kPa)":"{:.3f}",
            "FNS/RLSS amplitude ratio":"{:.1f}"}))
'''.strip()

PRIMARY_MD = r"""
## 3.3 Model B: empirical SAFOD transfer

After the tide and elastic stress have been calculated, Model B takes the branch

$$
\boxed{
\Delta\sigma_{n}(t)
\rightarrow
S_{\mathrm{Niu}}
\rightarrow
\left(\frac{\Delta v}{v}\right)_B
}
$$

with

$$
S_{\mathrm{Niu}}=2.4\times10^{-7}\ \mathrm{Pa}^{-1},
\qquad
\left(\frac{\Delta v}{v}\right)_B
=S_{\mathrm{Niu}}\Delta\sigma_n.
$$

FNS is stored positive in tension/unclamping, so the pressure-like compression used for the primary transfer is $\Delta\sigma_n=-\mathrm{FNS}$.

**Interpretation:** Model B asks, “Given the explicitly calculated June 2026 tidal stress, what velocity change would result if Niu's measured SAFOD stress sensitivity also applies to this tidal fault-normal stress?”

The strength of Model B is that the velocity sensitivity was measured at SAFOD. Its central uncertainty is the assumption that a barometric-loading sensitivity transfers to tidal fault-normal stress.
""".strip()

PRIMARY_CODE = r'''
if models is not None:
    for forcing in ["pysolid", "spotl"]:
        fns=f"{forcing}_FNS_tension_pa"
        rlss=f"{forcing}_RLSS_pa"
        if fns in models.columns and rlss in models.columns:
            good=models[["time_utc",fns,rlss]].dropna()
            plt.figure(figsize=(11,5))
            plt.plot(good.time_utc,good[fns]/1000.0,label="FNS (tension +)")
            plt.plot(good.time_utc,good[rlss]/1000.0,label="RLSS")
            plt.axhline(0,linewidth=.8)
            plt.ylabel("Stress perturbation (kPa)")
            plt.xlabel("UTC")
            plt.title(f"Model B stress input — vertical SAFOD receiver plane ({forcing})")
            plt.grid(alpha=.25); plt.legend()
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=3))
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
            plt.xticks(rotation=30,ha="right"); plt.tight_layout(); plt.show()
'''.strip()

CAVEAT_MD = r"""
## 3.4 Mechanical scope of the stress calculation

The stress calculation intentionally stops at a vertical receiver fault:

$$
\boxed{
\text{surface body-tide strain}
\rightarrow
\text{surface-derived horizontal elastic stress}
\rightarrow
\text{vertical SAF traction}
}
$$

It does not claim to recover the exact 3-D tidal stress tensor along the approximately 1 km-deep DAS interval. A rigorous dipping-fault calculation should begin from a full 3-D depth-dependent strain tensor.
""".strip()

AWD_MD = r"""
# 4. Which calculations are actually compared with the AWD sensitivity?

The calculations in this notebook do **not** all have the same scientific role.

## 4.1 Preliminary reference only: the old 240-Pa Niu estimate

Before explicitly calculating the June 2026 tidal forcing, a simple order-of-magnitude estimate was

$$
240\ \mathrm{Pa}\times
2.4\times10^{-7}\ \mathrm{Pa}^{-1}
=5.76\times10^{-5}.
$$

This quantity does **not** use PySolid, SPOTL, the June 2026 Sun/Moon geometry, or the calculated tidal strain. It is therefore retained only as a **preliminary reference calculation** and is excluded from the final AWD detectability table.

## 4.2 External literature context only: Takano

The Takano strain-sensitivity branch is retained only to show that substantially larger tidal strain sensitivities have been reported at other sites. It comes from a different geologic setting and should **not** be interpreted as an expected SAFOD response. It is excluded from the final AWD detectability table.

## 4.3 Two SAFOD-relevant decision chains

Once the June 2026 tide has been calculated, the common upstream chain is

$$
\boxed{
\text{June 2026 tide}
\rightarrow
\boldsymbol{\varepsilon}(t)
\rightarrow
\boldsymbol{\sigma}(t)
}
$$

From that point the notebook follows two conceptually different response branches.

### Model B — empirical SAFOD branch

$$
\boxed{
\boldsymbol{\sigma}(t)
\rightarrow
\Delta\sigma_n(t)
\rightarrow
S_{\mathrm{Niu}}
\rightarrow
\Delta v/v
}
$$

This uses the observed SAFOD stress sensitivity from Niu et al. Its key assumption is the transfer from barometric loading to tidal fault-normal stress.

### Model D — mechanistic rock-physics branch

$$
\boxed{
\boldsymbol{\sigma}(t)
\rightarrow
\text{stress-dependent crack/contact compliance}
\rightarrow
K_{\mathrm{eff}}(t),\mu_{\mathrm{eff}}(t)
\rightarrow
V_P(t),V_S(t)
}
$$

with

$$
V_S=\sqrt{\frac{\mu}{\rho}},
\qquad
V_P=\sqrt{\frac{K+\frac{4}{3}\mu}{\rho}}.
$$

Model D does **not** use Niu's empirical $dv/v$-per-Pa coefficient. It asks instead what a physical stress-sensitive crack model predicts for intrinsic formation-scale $V_P$ and $V_S$.

The agreement or disagreement between B and D is therefore informative because they reach velocity changes through different assumptions. However, the AWD observable is an **apparent along-fiber propagation speed**, not a direct measurement of intrinsic formation $V_P$ or $V_S$. The D($V_P$) and D($V_S$) comparisons below are therefore order-of-magnitude detectability comparisons, not statements that the AWD observable equals either velocity.

## 4.4 Current AWD sensitivity benchmark

The benchmark is the imposed apparent along-fiber speed change required to recover the **correct direction in 90% of synthetic injection–recovery tests**. For the full usable cable:

- Nano: **0.55%** (95% interval 0.40–0.81%)
- Deep outbound: **0.40%** (0.28–0.48%)
- Deep return: **0.68%** (0.54–0.81%)

For the matched 700 m comparison, Nano is **0.55%** (0.41–0.81%), while both Deep branches are **greater than 2%** because neither reached 90% correct-direction recovery within the tested range.

The final table uses the **full-cable Deep outbound 0.40% threshold** as the observational benchmark. It contains only Model B and Model D.

No branch constitutes a tidal detection.
""".strip()

AWD_CODE = r'''
if models is not None:
    benchmark=CONFIG["awd_benchmarks"]["full_cable"]["deep_outbound"]
    deep90=benchmark["threshold"]
    summary_rows=[]
    for forcing in ["pysolid","spotl"]:
        mapping={
            "B — empirical SAFOD Niu transfer":f"{forcing}_model_B_dv_over_v",
            "D — formation dVs/Vs":f"{forcing}_model_D_dVs_over_Vs",
            "D — formation dVp/Vp":f"{forcing}_model_D_dVp_over_Vp",
        }
        for name,col in mapping.items():
            if col not in models.columns:
                continue
            amp=np.nanmax(np.abs(models[col]))
            summary_rows.append({
                "forcing":forcing,
                "prediction":name,
                "max_abs_dv/v":amp,
                "max_abs_percent":100*amp,
                "Deep outbound 90% threshold / prediction":deep90/amp,
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
        "Deep outbound 90% threshold / prediction":"{:.1f}x",
    }))
'''.strip()


LIMITATIONS_MD = """
## 5. Interpretation and limitations

The PySolid/SPOTL comparison addresses uncertainty in the calculated tidal forcing. The Thomas-style Figure 3 analogue checks the stress construction. The final stress-to-apparent-velocity step remains the least constrained part.

Important limitations:

- The current Model B does **not** impose plane strain. It uses a free-surface condition to recover the surface strain trace, applies isotropic Hooke law to the horizontal stresses, and resolves traction on a vertical SAF plane.
- This surface-derived calculation is a stress benchmark, not the exact 3-D tidal stress tensor along the approximately 1 km-deep DAS interval. A dipping-fault calculation requires a full 3-D depth-dependent strain tensor.
- Niu's coefficient is an empirical barometric sensitivity, not a universal tidal coefficient.
- Model D predicts formation-scale Vp/Vs, not the AWD guided apparent velocity.
- No tidal response is claimed to have been detected in the AWD experiment.

## References

- Thomas et al. (2012), JGR Solid Earth, DOI `10.1029/2011JB009036`.
- van der Elst et al. (2016), PNAS, DOI `10.1073/pnas.1524316113`.
- Agnew (2012), SPOTL.
- Niu et al. (2008), Nature, DOI `10.1038/nature07111`.
""".strip()

def main():
    if not NOTEBOOK.exists():
        raise FileNotFoundError(NOTEBOOK)

    nb=nbf.read(NOTEBOOK,as_version=4)
    fig3_code_done=False
    primary_code_done=False
    awd_code_done=False

    for cell in nb.cells:
        src=cell.get("source","")
        if cell.cell_type=="markdown" and src.lstrip().startswith("# 3. Model B:"):
            cell.source=MODEL_B_MD
        elif cell.cell_type=="markdown" and "Thomas et al. Figure 3 analogue" in src:
            cell.source=FIG3_MD
        elif cell.cell_type=="code" and "thomas_FNS_pa" in src and "thomas_RLSS_pa" in src:
            if not fig3_code_done:
                cell.source=FIG3_CODE
                fig3_code_done=True
        elif cell.cell_type=="markdown" and (
            "Primary SAFOD Model B" in src or "Model B: empirical SAFOD transfer" in src
        ):
            cell.source=PRIMARY_MD
        elif cell.cell_type=="code" and (
            "spotl_FNS_pa" in src or "along_strike_shear_pa" in src or "Revised Model B" in src
        ):
            if not primary_code_done:
                cell.source=PRIMARY_CODE
                primary_code_done=True
        elif cell.cell_type=="markdown" and (
            src.lstrip().startswith("# 4. Models A–D and AWD")
            or src.lstrip().startswith("# 4. SAFOD model amplitudes and AWD sensitivity")
            or src.lstrip().startswith("# 4. Which calculations are actually compared")
        ):
            cell.source=AWD_MD
        elif cell.cell_type=="code" and (
            "Deep reliable / model" in src
            or "deep_outbound_reliable" in src
            or "Deep outbound 90% threshold / model" in src
            or "Deep outbound 90% threshold / prediction" in src
        ):
            if not awd_code_done:
                cell.source=AWD_CODE
                awd_code_done=True

        elif cell.cell_type=="markdown" and src.lstrip().startswith("## 5. Interpretation and limitations"):
            cell.source=LIMITATIONS_MD

    if not any(c.cell_type=="markdown" and "## 3.4 Mechanical scope" in c.source for c in nb.cells):
        insert_at=None
        for i,cell in enumerate(nb.cells):
            if cell.cell_type=="code" and "Model B stress input" in cell.source:
                insert_at=i+1
                break
        if insert_at is not None:
            nb.cells.insert(insert_at,nbf.v4.new_markdown_cell(CAVEAT_MD))

    nbf.write(nb,NOTEBOOK)
    print(f"Updated Model B / Thomas Figure 3 / model hierarchy / AWD sections in {NOTEBOOK}")


if __name__=="__main__":
    main()
