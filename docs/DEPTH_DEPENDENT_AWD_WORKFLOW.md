# Depth-dependent SAFOD tide-response and AWD recoverability workflow

This extension separates three quantities that the original scalar comparison combined:

\[
\boxed{\Delta \sigma_n(z,t)}
\quad\rightarrow\quad
\boxed{\Delta v/v(z,t)}
\quad\rightarrow\quad
\boxed{\text{AWD recovery}}.
\]

The current repository can evaluate the middle arrow as a transparent sensitivity scenario. A true depth-localized AWD threshold requires a separate synthetic injection-recovery run on the field waveforms.

## 1. What is calculated now

The tide pipeline supplies the Model-B time history

\[
\left(\frac{\Delta v}{v}\right)_B(t)
=S_{\mathrm{Niu}}\,\Delta\sigma_n(t).
\]

The depth extension replaces the single sensitivity with

\[
S_\sigma(z)=S_{\mathrm{Niu}}
\left[1+(M_0-1)g(z;H)\right],
\]

where

- \(M_0\) is the shallow/surface sensitivity relative to Niu;
- \(H\) is the decay scale;
- \(g(0)=1\);
- \(g(1\ \mathrm{km})=0\), so Niu's calibration is recovered exactly at the reference depth.

The current first-order scenario holds the Model-B tidal-stress history fixed with depth and varies only the stress-to-velocity sensitivity:

\[
\frac{\Delta v}{v}(z,t)
=\left[1+(M_0-1)g(z;H)\right]
\left(\frac{\Delta v}{v}\right)_B(t).
\]

This is **not** a 3-D tidal-stress solution. It answers the narrower question:

> How much larger than the Niu calibration would shallow stress sensitivity have to be for a specified depth interval to approach the AWD recovery benchmark?

Until empirical depth-localized AWD thresholds are supplied, the script averages uniformly within each configured depth window and uses the global full-cable Deep-outbound 90%-correct-direction threshold as a clearly labeled placeholder.

## 2. Run the scenario calculation

After the normal tide pipeline:

```bash
bash RUN_ON_SHERLOCK.sh
```

The following products are written to `outputs/tides/`:

```text
depth_sensitivity_profiles.csv
depth_sensitivity_scenarios.csv
depth_sensitivity_required_shallow_multiplier.csv
depth_sensitivity_required_shallow_multiplier.png
depth_sensitivity_provenance.json
```

The most directly interpretable product is

```text
depth_sensitivity_required_shallow_multiplier.csv
```

which reports the shallow multiplier \(M_0\) required to reach the selected AWD threshold for every forcing, response window, and decay scale.

## 3. What the empirical AWD experiment still has to measure

The existing full-cable injection-recovery result estimates a change in an apparent along-fiber speed. It does not by itself locate that change in depth. A depth-localized experiment must impose a change only over a specified coordinate interval and recover the local perturbation with an estimator designed for that interval.

For a linear baseline trajectory

\[
T(z)=t_0+s z,
\]

a fractional velocity increase \(\epsilon\) confined to \([z_1,z_2]\) produces the first-order travel-time perturbation

\[
\delta T(z)
=-\epsilon s\,\operatorname{clip}(z-z_1,0,z_2-z_1).
\]

This is a **hinge-shaped delay**, not a global linear slope. Channels above the interval are unshifted, channels inside the interval accumulate delay change, and channels below it retain a constant accumulated offset.

For a non-linear frozen trajectory, use the corresponding baseline travel-time curve:

\[
\delta T(z)
=-\epsilon
\left[
T\!\left(\operatorname{clip}(z,z_1,z_2)\right)-T(z_1)
\right].
\]

### Required implementation rules

1. Preserve the existing blind stages: freeze, inject, recover, summarize.
2. Keep the previously selected mode, band, and trajectory frozen.
3. Apply the perturbation only inside a time gate around the selected mode. Shifting an entire channel trace makes wrong-observable controls non-diagnostic.
4. Recover \(\epsilon\) with the hinge predictor, while retaining a common intercept term for source timing.
5. Insert positive and negative changes into real field variability.
6. Report the probability of recovering the correct direction as a function of the **local imposed change**.
7. Estimate the 90%-correct-direction threshold separately for every interval.
8. Bootstrap over bursts, not individual aperture measurements, when burst identifiers are available.
9. Keep Nano and Deep coordinate claims separate. Nano has a substantially firmer channel-to-depth mapping; Deep should be labeled in along-fiber coordinates until its registration is independently established.

## 4. Trial-level interface

The raw-data injection code should export one row per recovered trial using the schema in

```text
inputs/awd_depth_localized_trials_template.csv
```

Required columns:

```text
observable
window_label
depth_top_m
depth_bottom_m
burst_id
injected_dvv
recovered_dvv
```

Then summarize it with:

```bash
.venv/bin/python scripts/tides/summarize_awd_depth_trials.py \
  path/to/awd_depth_localized_trials.csv \
  --output-dir outputs/tides
```

This creates:

```text
outputs/tides/awd_depth_localized_recovery_curves.csv
outputs/tides/awd_depth_localized_thresholds.csv
outputs/tides/awd_depth_localized_thresholds_provenance.json
```

The summarizer uses a weighted isotonic correct-direction curve and interpolates its crossing of 90%. Its metric is **correct direction only**. It is intentionally distinct from the older “reliable detection” definition that additionally required exceeding an empirical zero-injection threshold.

## 5. Feed empirical thresholds back into the tide scenarios

After reviewing the trial-level results, copy the accepted threshold table into the input location used by the tide pipeline:

```bash
cp outputs/tides/awd_depth_localized_thresholds.csv \
   inputs/awd_depth_localized_thresholds.csv
```

Then rerun:

```bash
bash RUN_ON_SHERLOCK.sh
bash MAKE_NOTEBOOK_HTML.sh
```

The depth-sensitivity calculation will use window-specific thresholds where available and will retain the global full-cable benchmark only for windows without an empirical result.

## 6. Interpretation ceiling

This workflow can establish:

- the AWD recovery threshold for a perturbation confined to a chosen interval;
- the shallow sensitivity amplification required to make the Model-B tidal response approach that threshold;
- whether a shallow-only response is diluted by the measurement aperture.

It cannot by itself establish:

- the true depth dependence of SAFOD stress sensitivity;
- the exact 3-D tidal stress tensor;
- whether the AWD apparent mode responds as intrinsic \(V_P\), intrinsic \(V_S\), or another guided-mode combination;
- a tidal detection.

Constraining the actual \(S_\sigma(z)\) requires an independent long-duration depth-resolved velocity-change analysis against pressure and temperature loading.
