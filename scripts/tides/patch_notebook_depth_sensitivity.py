#!/usr/bin/env python
from __future__ import annotations

import nbformat as nbf

from common import ROOT


NOTEBOOK = ROOT / "notebooks" / "SAFOD_tides_model_framework.ipynb"


HIERARCHY_MD = r"""
# 4. Which calculations are actually compared with the AWD sensitivity?

The calculations in this notebook do **not** all have the same scientific role.

## 4.1 Preliminary reference only: the 240-Pa Niu estimate

The preliminary estimate

$$
240\ \mathrm{Pa}\times
2.4\times10^{-7}\ \mathrm{Pa}^{-1}
=5.76\times10^{-5}
$$

does not calculate the June 2026 tide. It does not use PySolid, SPOTL, the experiment dates, or the modeled tidal strain. It is retained only as an order-of-magnitude reference and is excluded from the final detectability table.

## 4.2 External literature context only: Takano

The Takano strain-sensitivity branch is retained only as evidence that much larger tidal strain sensitivities have been reported in a different geologic setting. It is not an expected SAFOD response and is excluded from the final detectability table.

## 4.3 Common calculated forcing chain

The two retained SAFOD response branches begin from the same explicitly calculated forcing:

$$
\boxed{
\text{June 2026 Sun/Moon forcing}
\rightarrow
\boldsymbol{\varepsilon}(t)
\rightarrow
\boldsymbol{\sigma}(t)
\rightarrow
\Delta\sigma_n(t)
}
$$

### Model B — direct empirical transfer

$$
\boxed{
\Delta\sigma_n(t)
\rightarrow
S_{\mathrm{Niu}}
\rightarrow
\left(\frac{\Delta v}{v}\right)_B(t)
}
$$

Model B directly multiplies the calculated compression-positive fault-normal stress by Niu's SAFOD barometric coefficient. The uncertain arrow is the transfer from barometric loading near 1 km depth to tidal fault-normal loading relevant to the AWD experiment.

### Model D — Niu-calibrated crack model

$$
\boxed{
\Delta\sigma_n(t)
\rightarrow
\text{crack-density evolution}
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

Model D does not directly multiply every tidal-stress sample by Niu's coefficient. However, the **current implementation is still calibrated to Niu**: it chooses the crack stress scale $\hat{\sigma}$ so that the local $V_S$ stress sensitivity at the reference state matches $S_{\mathrm{Niu}}$. In the code,

$$
\hat{\sigma}=\frac{\text{crack-model prefactor}}{S_{\mathrm{Niu}}}.
$$

Therefore, agreement between Model B and Model-D $\Delta V_S/V_S$ is **not independent confirmation of the absolute amplitude**; that agreement is partly built into the calibration. Model D adds constitutive structure, possible nonlinearity, and the distinction between $V_P$ and $V_S$, but it shares Niu's sensitivity anchor and its depth limitation.

The AWD observable is a fractional change in an **apparent along-fiber propagation speed**. It is not automatically intrinsic formation $V_P$ or $V_S$. The Model-D rows are therefore order-of-magnitude comparisons, not an assertion that the AWD estimator measures either bulk velocity directly.

## 4.4 Current AWD sensitivity benchmark

The benchmark is the imposed apparent along-fiber speed change required to recover the **correct direction in 90% of synthetic injection-recovery tests**. For the full usable cable:

- Nano: **0.55%** (95% interval 0.40–0.81%)
- Deep outbound: **0.40%** (0.28–0.48%)
- Deep return: **0.68%** (0.54–0.81%)

For the matched 700 m comparison, Nano is **0.55%** (0.41–0.81%), while both Deep branches are **greater than 2%** because neither reached 90% correct-direction recovery within the tested range.

The final table uses the full-cable Deep-outbound 0.40% threshold and contains only Model B and the two Model-D formation-velocity outputs. Model A and Takano are deliberately excluded.

No branch constitutes a tidal detection.
""".strip()


FINAL_TABLE_CODE = r'''
if models is not None:
    benchmark = CONFIG["awd_benchmarks"]["full_cable"]["deep_outbound"]
    deep90 = benchmark["threshold"]
    summary_rows = []
    for forcing in ["pysolid", "spotl"]:
        mapping = {
            "B — direct Niu transfer": (
                f"{forcing}_model_B_dv_over_v",
                "Niu used directly as dv/v per Pa",
                "empirical apparent-velocity response scenario",
            ),
            "D — Niu-calibrated crack model dVs/Vs": (
                f"{forcing}_model_D_dVs_over_Vs",
                "Niu sets the crack stress scale",
                "intrinsic formation Vs scenario",
            ),
            "D — Niu-calibrated crack model dVp/Vp": (
                f"{forcing}_model_D_dVp_over_Vp",
                "Niu sets the crack stress scale",
                "intrinsic formation Vp scenario",
            ),
        }
        for name, (col, niu_role, observable_role) in mapping.items():
            if col not in models.columns:
                continue
            amp = np.nanmax(np.abs(models[col]))
            summary_rows.append({
                "forcing": forcing,
                "prediction": name,
                "Niu role": niu_role,
                "predicted quantity": observable_role,
                "max_abs_fractional_change": amp,
                "max_abs_percent": 100 * amp,
                "Deep outbound 90% threshold / prediction": deep90 / amp,
            })
    summary = pd.DataFrame(summary_rows)
    print(
        "AWD benchmark: full-cable Deep outbound 90%-correct-direction threshold "
        f"= {100*deep90:.2f}% "
        f"(95% interval {100*benchmark['ci95_low']:.2f}–{100*benchmark['ci95_high']:.2f}%)."
    )
    display(summary.style.format({
        "max_abs_fractional_change": "{:.3e}",
        "max_abs_percent": "{:.5f}",
        "Deep outbound 90% threshold / prediction": "{:.1f}x",
    }))
'''.strip()


DEPTH_MD = r"""
# 5. Depth-dependent stress-sensitivity scenarios

Ettore's depth caveat concerns the constitutive response, not only the tide calculation. The quantity needed for a depth-resolved prediction is

$$
\boxed{
\Delta\sigma_n(z,t)
\rightarrow
S_\sigma(z)
\rightarrow
\frac{\Delta v}{v}(z,t)
\rightarrow
\mathcal{M}_{\mathrm{AWD}}
\rightarrow
\text{recovery probability}
}
$$

where $\mathcal{M}_{\mathrm{AWD}}$ denotes the wavefield and estimator sensitivity to changes distributed along the cable.

The current scenario study asks a deliberately narrower question: **how much larger than Niu's approximately 1-km calibration would shallow stress sensitivity have to be for a specified interval to approach the AWD recovery threshold?**

We parameterize

$$
S_\sigma(z)=S_{\mathrm{Niu}}
\left[1+(M_0-1)g(z;H)\right],
$$

where $M_0$ is the surface sensitivity multiplier and $H$ is the decay scale. The profile is normalized so that

$$
g(0)=1,
\qquad g(1\ \mathrm{km})=0,
$$

and therefore $S_\sigma(1\ \mathrm{km})=S_{\mathrm{Niu}}$.

For this first-order calculation,

1. the current Model-B tidal-stress time history is held fixed with depth;
2. only $S_\sigma(z)$ is varied;
3. the response is averaged uniformly within each listed interval.

Those are explicit scenario assumptions. They are **not** a 3-D tidal-stress calculation and are **not** a measured AWD depth kernel.

Until a depth-localized injection-recovery table is supplied, every interval is compared with the global full-cable Deep-outbound 0.40% benchmark. The output labels that use as a placeholder rather than presenting it as an interval-specific empirical threshold.
""".strip()


DEPTH_CODE = r'''
required_path = OUT / "depth_sensitivity_required_shallow_multiplier.csv"
scenario_path = OUT / "depth_sensitivity_scenarios.csv"
provenance_path = OUT / "depth_sensitivity_provenance.json"

if not required_path.exists():
    print("No depth-sensitivity products yet. Run: bash RUN_ON_SHERLOCK.sh")
else:
    required = pd.read_csv(required_path)
    primary = CONFIG.get("primary_forcing", "pysolid")
    view = required[required["forcing"] == primary].copy()
    if view.empty:
        primary = required["forcing"].iloc[0]
        view = required[required["forcing"] == primary].copy()

    display_columns = [
        "window_label",
        "decay_scale_m",
        "base_model_B_max_abs_dv_over_v",
        "threshold_90",
        "threshold_source",
        "required_effective_sensitivity_multiplier",
        "required_surface_sensitivity_multiplier",
    ]
    print(f"Primary forcing shown: {primary}")
    display(
        view[display_columns]
        .sort_values(["window_label", "decay_scale_m"])
        .style.format({
            "decay_scale_m": "{:.0f}",
            "base_model_B_max_abs_dv_over_v": "{:.3e}",
            "threshold_90": "{:.3e}",
            "required_effective_sensitivity_multiplier": "{:.1f}x",
            "required_surface_sensitivity_multiplier": "{:.1f}x",
        })
    )

    window_order = [w["label"] for w in CONFIG["depth_sensitivity_scenarios"]["response_windows_m"]]
    order = {label: i for i, label in enumerate(window_order)}
    plt.figure(figsize=(11, 6))
    for decay, group in view.groupby("decay_scale_m", sort=True):
        group = group.copy()
        group["_order"] = group["window_label"].map(order)
        group = group.sort_values("_order")
        plt.plot(
            group["window_label"],
            group["required_surface_sensitivity_multiplier"],
            marker="o",
            label=f"H = {decay:g} m",
        )
    plt.axhline(1.0, linewidth=.8)
    plt.yscale("log")
    plt.ylabel("Required shallow sensitivity / Niu sensitivity")
    plt.xlabel("Assumed response interval")
    plt.title(
        "Shallow stress-sensitivity enhancement needed to reach the AWD benchmark\n"
        f"Model B, {primary}; uniform interval weighting"
    )
    plt.xticks(rotation=25, ha="right")
    plt.grid(alpha=.25)
    plt.legend(title="Decay scale")
    plt.tight_layout(); plt.show()

    sources = view["threshold_source"].dropna().unique()
    print("Threshold source(s):")
    for source in sources:
        print(" -", source)
    if all("placeholder" in str(source) for source in sources):
        print(
            "No empirical depth-localized threshold has been supplied yet; "
            "these are physical-sensitivity scenarios against the global full-cable benchmark."
        )
'''.strip()


LIMITATIONS_MD = r"""
# 6. Interpretation and limitations

The PySolid/SPOTL comparison addresses forcing uncertainty. The Thomas-style calculation checks the surface-strain-to-vertical-fault-stress construction. The largest uncertainties remain to the right of that calculation:

$$
\Delta\sigma_n(z,t)
\rightarrow
S_\sigma(z)
\rightarrow
\Delta v/v(z,t)
\rightarrow
\text{AWD apparent-velocity recovery}.
$$

Important limitations:

- The current stress calculation is a surface-derived vertical-fault benchmark, not the exact 3-D tidal stress tensor along the borehole.
- Model B uses Niu's barometric coefficient directly. Its variation with depth and its transfer to tidal fault-normal loading are unknown.
- Model D is **not independent of Niu in amplitude**. Niu's coefficient calibrates the crack stress scale $\hat{\sigma}$ in the present implementation.
- Model D predicts intrinsic formation $V_P$ and $V_S$; AWD measures an apparent along-fiber mode velocity.
- The depth-sensitivity profiles hold tidal stress fixed with depth and assume uniform weighting inside each interval. They are scenarios, not a 3-D simulation or a measured sensitivity kernel.
- A true empirical depth-localized result requires synthetic changes confined to selected intervals and recovery with a localized/hinge travel-time predictor.
- Nano has the firmer channel-to-depth mapping. Deep interval results should remain in along-fiber coordinates until its depth registration is independently established.
- No tidal response is claimed to have been detected.

## References

- Thomas et al. (2012), *JGR Solid Earth*, DOI `10.1029/2011JB009036`.
- Agnew (2012), *SPOTL: Some Programs for Ocean-Tide Loading*.
- Niu et al. (2008), *Nature*, DOI `10.1038/nature07111`.
""".strip()


def _is_hierarchy_markdown(source: str) -> bool:
    stripped = source.lstrip()
    return (
        stripped.startswith("# 4. Models A–D and AWD")
        or stripped.startswith("# 4. SAFOD model amplitudes and AWD sensitivity")
        or stripped.startswith("# 4. Which calculations are actually compared")
    )


def _is_final_table_code(source: str) -> bool:
    return any(
        marker in source
        for marker in [
            "Deep reliable / model",
            "deep_outbound_reliable",
            "Deep outbound 90% threshold / model",
            "Deep outbound 90% threshold / prediction",
            "max_abs_fractional_change",
        ]
    )


def main() -> None:
    if not NOTEBOOK.exists():
        raise FileNotFoundError(NOTEBOOK)

    nb = nbf.read(NOTEBOOK, as_version=4)
    hierarchy_done = False
    table_done = False
    depth_markdown_index = None
    depth_code_index = None
    limitations_index = None

    for i, cell in enumerate(nb.cells):
        source = cell.get("source", "")
        if cell.cell_type == "markdown" and _is_hierarchy_markdown(source):
            if not hierarchy_done:
                cell.source = HIERARCHY_MD
                hierarchy_done = True
        elif cell.cell_type == "code" and _is_final_table_code(source):
            if not table_done:
                cell.source = FINAL_TABLE_CODE
                table_done = True
        elif cell.cell_type == "markdown" and source.lstrip().startswith(
            "# 5. Depth-dependent stress-sensitivity scenarios"
        ):
            if depth_markdown_index is None:
                cell.source = DEPTH_MD
                depth_markdown_index = i
        elif cell.cell_type == "code" and "depth_sensitivity_required_shallow_multiplier" in source:
            if depth_code_index is None:
                cell.source = DEPTH_CODE
                depth_code_index = i
        elif cell.cell_type == "markdown" and "Interpretation and limitations" in source:
            cell.source = LIMITATIONS_MD
            limitations_index = i

    if not hierarchy_done:
        raise RuntimeError("Could not locate the notebook model-hierarchy section.")
    if not table_done:
        raise RuntimeError("Could not locate the notebook AWD comparison table cell.")

    if limitations_index is None:
        limitations_index = len(nb.cells)
        nb.cells.append(nbf.v4.new_markdown_cell(LIMITATIONS_MD))

    if depth_markdown_index is None:
        nb.cells.insert(limitations_index, nbf.v4.new_markdown_cell(DEPTH_MD))
        depth_markdown_index = limitations_index
    if depth_code_index is None:
        nb.cells.insert(depth_markdown_index + 1, nbf.v4.new_code_cell(DEPTH_CODE))

    nbf.write(nb, NOTEBOOK)
    print(f"Updated model calibration and depth-sensitivity sections in {NOTEBOOK}")


if __name__ == "__main__":
    main()
