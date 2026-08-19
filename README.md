# SAFOD solid-Earth tides — Sherlock reproducible framework

This repository calculates the June 16–17, 2026 solid-Earth tide at SAFOD, propagates the forcing through explicitly labeled response scenarios, compares those amplitudes with AWD injection–recovery sensitivity, and renders the results in a reproducible notebook.

The repository separates **scientific execution** from **scientific presentation**:

```text
scripts/tides/                              calculations and notebook patchers
outputs/tides/                              generated products and provenance
notebooks/SAFOD_tides_model_framework.ipynb presentation notebook
config.json                                 site, model, AWD, and depth-scenario settings
RUN_ON_SHERLOCK.sh                          complete scientific pipeline
MAKE_NOTEBOOK_HTML.sh                       executed notebook + static HTML
```

The notebook does not install packages or compile Fortran.

## Scientific hierarchy

### Tidal forcing

The pipeline calculates body-tide strain three ways:

1. **PySolid 0.3.4** — displacement on a spatial stencil, differentiated to obtain horizontal strain;
2. **SPOTL `ertid`** — extensional strain at 0°, 45°, and 90°, reconstructed as `eps_NN`, `eps_EE`, and `eps_NE`;
3. **transparent degree-2 calculation** — independent Sun/Moon and Love-number check.

The PySolid/SPOTL comparison constrains uncertainty in the forcing calculation.

### Stress construction

The current mechanical benchmark is

```text
surface horizontal tidal strain
    -> traction-free surface strain trace
    -> 3-D isotropic Hooke law
    -> horizontal stress
    -> FNS and RLSS on a vertical SAF receiver plane
```

It does **not** impose plane strain and does not project a surface-derived tensor onto the approximately 70°-dipping fault. A dipping-fault calculation requires a full 3-D depth-dependent strain tensor.

The notebook also contains a Thomas et al. (2012) Figure-3-style analogue on a vertical N42W plane. It is a transparent benchmark, not an exact reproduction of their undocumented parameter choices.

### Response calculations do not all have the same role

- **240-Pa Niu calculation:** preliminary order-of-magnitude reference only. It does not calculate the June 2026 tide and is excluded from the final detectability table.
- **Model B:** calculated fault-normal tidal stress multiplied directly by Niu's SAFOD barometric stress-sensitivity coefficient.
- **Takano/Model C:** external literature context from a different geologic setting. It is excluded from the final SAFOD detectability table.
- **Model D:** stress-dependent crack model yielding formation-scale `dVp/Vp` and `dVs/Vs`.

Model D is **not independent of Niu in absolute amplitude**. The current implementation uses Niu's coefficient to calibrate its crack stress scale, so agreement between Model B and Model-D `dVs/Vs` is partly built into the calibration. Model D adds constitutive structure and separates `Vp` from `Vs`; it does not provide an independent amplitude validation.

The AWD observable is an apparent along-fiber propagation speed, not automatically intrinsic formation `Vp` or `Vs`.

## First-time Sherlock setup

The installation workflow was validated on Sherlock with Python 3.11.4 and GCC 14.2.0. Run this from a Sherlock terminal on a login node because the SPOTL archive is approximately 200 MB:

```bash
git clone git@github.com:nataliaberrios/safod-tides.git
cd safod-tides

module load gcc/14.2.0
bash scripts/tides/setup_sherlock.sh
```

For an existing clone:

```bash
cd /path/to/safod-tides
git pull
module load gcc/14.2.0
bash scripts/tides/setup_sherlock.sh
```

The setup script creates a project-local `.venv`; it does not create a conda environment. It installs the pinned scientific stack, a Sherlock-compatible `pyzmq` wheel, `nbformat`, `nbconvert`, the `SAFOD tides (.venv)` kernel, PySolid built against the pinned NumPy ABI, and SPOTL.

The SPOTL installer applies the required legacy GNU-Fortran flags and patches the old `ispand.c` implicit-`int` declarations for modern GCC.

A successful setup ends with messages like:

```text
Python environment check: PASS
Installed kernelspec safod-tides ...
SPOTL installed successfully: .../external/spotl/bin/ertid
Setup complete.
```

Do **not** run `conda activate safod-tides`.

## Run the full calculation

No environment activation is needed:

```bash
bash RUN_ON_SHERLOCK.sh
```

The pipeline runs the tide packages, forcing comparison, Models A–D, the depth-dependent sensitivity scenarios, and both notebook synchronization steps.

A successful run ends with:

```text
Pipeline complete.
Products are in outputs/tides/.
Notebook mechanics, model hierarchy, AWD benchmark, and depth-sensitivity sections are synchronized.
```

A SLURM wrapper is also available:

```bash
sbatch scripts/tides/run_tides.sbatch
```

## Main outputs

```text
outputs/tides/
    pysolid_tides.csv
    pysolid_provenance.json
    spotl_ertid_tides.csv
    spotl_provenance.json
    analytic_degree2_tides.csv
    analytic_degree2_provenance.json
    forcing_comparison.csv
    forcing_comparison_provenance.json
    model_results.csv
    model_summary.json
    model_provenance.json

    depth_sensitivity_profiles.csv
    depth_sensitivity_scenarios.csv
    depth_sensitivity_required_shallow_multiplier.csv
    depth_sensitivity_required_shallow_multiplier.png
    depth_sensitivity_provenance.json
```

SPOTL intermediate input/output files are stored in `outputs/tides/spotl_work/`.

## Depth-dependent sensitivity scenarios

The scenario calculation makes the decision chain explicit:

```text
tidal fault-normal stress
    -> depth-dependent stress sensitivity S_sigma(z)
    -> local dv/v(z,t)
    -> assumed AWD interval weighting
    -> comparison with recovery threshold
```

It parameterizes a shallow enhancement relative to Niu's approximately 1-km calibration and reports how large the shallow multiplier would have to be for each configured interval to reach the AWD benchmark.

The current scenario:

- holds the Model-B tidal-stress history fixed with depth;
- varies only the stress-to-velocity sensitivity;
- assumes uniform weighting within each interval;
- uses the global full-cable Deep-outbound 0.40% threshold as a labeled placeholder until interval-specific thresholds exist.

This is not a 3-D tide simulation and not yet an empirical depth-localized AWD result.

The full workflow, hinge-shaped localized delay operator, trial schema, and interpretation limits are documented in:

```text
docs/DEPTH_DEPENDENT_AWD_WORKFLOW.md
```

### Summarize future depth-localized AWD trials

The raw AWD injection code should export the schema in:

```text
inputs/awd_depth_localized_trials_template.csv
```

Then run:

```bash
.venv/bin/python scripts/tides/summarize_awd_depth_trials.py \
  path/to/awd_depth_localized_trials.csv \
  --output-dir outputs/tides
```

After scientific review, place the accepted thresholds where the tide pipeline expects them:

```bash
cp outputs/tides/awd_depth_localized_thresholds.csv \
   inputs/awd_depth_localized_thresholds.csv

bash RUN_ON_SHERLOCK.sh
```

Window-specific thresholds will then replace the global placeholder where available.

## Generate a viewable notebook without OnDemand

After the pipeline completes:

```bash
bash MAKE_NOTEBOOK_HTML.sh
```

This writes:

```text
notebooks/SAFOD_tides_model_framework.executed.ipynb
notebooks/SAFOD_tides_model_framework.executed.html
```

The HTML contains rendered equations, tables, and figures. To copy it to a Mac, run this from a **local Mac terminal**, not from Sherlock:

```bash
scp nberrios@login.sherlock.stanford.edu:/home/groups/ettore88/nberrios/safod-tides/notebooks/SAFOD_tides_model_framework.executed.html ~/Downloads/
```

Other users should substitute their username and clone path.

## Open interactively in Sherlock OnDemand

1. Stop and restart an existing OnDemand JupyterLab job after first-time setup so the kernel is rediscovered.
2. Open `notebooks/SAFOD_tides_model_framework.ipynb`.
3. Choose **Kernel -> Change Kernel -> SAFOD tides (.venv)**.
4. Run All.

Verify the environment with:

```python
import sys
print(sys.executable)
```

The path should end in `/safod-tides/.venv/bin/python`.

## Normal later use

```bash
cd /path/to/safod-tides
git pull
module load gcc/14.2.0
bash RUN_ON_SHERLOCK.sh
bash MAKE_NOTEBOOK_HTML.sh
```

You do not need to recreate `.venv` or reinstall SPOTL unless those installations were deleted.

## Interpretation ceiling

- PySolid and SPOTL constrain body-tide forcing; they do not determine the local constitutive response.
- Model B transfers a barometric coefficient measured near 1 km to tidal fault-normal loading.
- Model D shares that Niu calibration and predicts intrinsic formation velocities, not the AWD apparent mode directly.
- The depth scenarios are parameter studies until localized injections provide empirical interval-specific measurement sensitivity.
- Deep coordinate-to-depth registration remains provisional; Deep interval results should be labeled in along-fiber coordinates until independently established.
- No tidal detection is claimed.

## Key sources

- Thomas, A. M., et al. (2012), *JGR Solid Earth*, DOI `10.1029/2011JB009036`.
- Agnew, D. C. (2012), *SPOTL: Some Programs for Ocean-Tide Loading*.
- Niu, F., et al. (2008), *Nature*, DOI `10.1038/nature07111`.
- Boness, N. L., & Zoback, M. D. (2004), *GRL*, DOI `10.1029/2003GL019020`.
