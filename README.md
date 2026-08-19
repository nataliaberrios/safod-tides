# SAFOD solid-Earth tides — Sherlock reproducible framework

This repository separates **scientific execution** from **scientific presentation**.

- `scripts/tides/` contains the package calls and Models A–D.
- `outputs/tides/` contains generated numerical products and run provenance.
- `notebooks/SAFOD_tides_model_framework.ipynb` reads those products and explains them.
- `config.json` contains the editable site/time/model parameters.

The notebook **does not install packages or compile Fortran**.

## What gets run

The pipeline runs:

1. **PySolid 0.3.4**
   - solid-Earth-tide ENU displacement at SAFOD
   - a spatial stencil around SAFOD
   - horizontal strain tensor from displacement gradients

2. **SPOTL 3.3.0.2 / `ertid`**, when the executable is available
   - official Scripps code
   - extensional strain at 0°, 45°, and 90°
   - reconstruction of `eps_NN`, `eps_EE`, and `eps_NE`

3. **Transparent degree-2 calculation**
   - independent Sun/Moon + PREM Love-number calculation

4. **Forcing comparison**, when both package results exist
   - correlations, amplitudes, RMS residuals

5. **Models A–D**
   - Model A: Niu 240 Pa shortcut
   - Model B: tidal strain -> linear elasticity -> vertical-SAF FNS/RLSS -> Niu transfer
   - Model C: direct published strain sensitivity
   - Model D: crack closure -> effective moduli -> Vp/Vs

Every scientific script writes a JSON provenance record containing the host, time, Python version, script hash, and, when available, git commit.

## Model B and the Thomas et al. Figure 3 analogue

Model B was revised to remove an unjustified step in the earlier formulation. It **no longer imposes plane strain and no longer projects a surface-derived tensor onto the approximately 70°-dipping SAF**.

Thomas et al. (2012) document the workflow

```text
SPOTL surface tidal strain
    -> linear elastic constitutive equation
    -> stress resolved onto a vertical N42W San Andreas plane
    -> FNS and RLSS
```

For the body tide they argue that the very long wavelength makes surface strain representative of strain at their 25 km source depth. Their paragraph 13 does not specify a plane-strain or plane-stress closure and does not tabulate the exact elastic constants used in Figure 3.

The revised Model B therefore does the following:

1. Uses the free-surface condition only to recover the missing **surface volumetric strain / strain trace** from the horizontal strain tensor.
2. Evaluates the full isotropic Hooke law for the horizontal stress components.
3. Resolves FNS and RLSS onto a **vertical** receiver plane at the local SAF strike.
4. Uses compression-positive FNS for the primary Niu stress-to-dv/v transfer; the RLSS transfer is also saved as a sensitivity branch.

The approximately 70° SW dip is retained as geologic context but is not used until a defensible full 3-D depth-dependent strain tensor is available.

The notebook contains a **Thomas et al. Figure-3-style analogue for the June 16–17, 2026 SAFOD window**. It plots FNS and RLSS in kPa on a vertical N42W plane. It is not labeled as an exact reproduction because Thomas et al. do not tabulate all Figure-3 elastic parameters and because the present calculation is body tide only.

## First-time Sherlock setup

The workflow below was validated on Sherlock with Python 3.11.4 and GCC 14.2.0.

Do this from a Sherlock terminal on a login node because the SPOTL archive is about 200 MB:

```bash
git clone git@github.com:nataliaberrios/safod-tides.git
cd safod-tides

module load gcc/14.2.0
bash scripts/tides/setup_sherlock.sh
```

If the repository is already cloned, use:

```bash
cd safod-tides
git pull
module load gcc/14.2.0
bash scripts/tides/setup_sherlock.sh
```

The setup script uses a project-local Python virtual environment (`.venv`), not a conda environment. It installs the pinned scientific Python stack, a Sherlock-compatible `pyzmq` wheel, `nbformat`, a Jupyter kernel named `SAFOD tides (.venv)`, and PySolid 0.3.4 built locally against the pinned NumPy ABI.

For SPOTL, the validated Sherlock compiler is GCC 14.2.0. The installer also applies the legacy GNU-Fortran compatibility flags and patches SPOTL's old `ispand.c` implicit-`int` declarations required by modern GCC.

A successful setup should end with messages indicating:

```text
Python environment check: PASS
Installed kernelspec safod-tides ...
SPOTL installed successfully: .../external/spotl/bin/ertid
Setup complete.
```

Do **not** run `conda activate safod-tides`; there is no conda environment for this repository.

## Run the calculation

No environment activation is required after setup. The runner automatically uses `.venv/bin/python` when it exists:

```bash
bash RUN_ON_SHERLOCK.sh
```

A successful complete run should end with:

```text
Updated Model B / Thomas Figure 3 sections in .../notebooks/SAFOD_tides_model_framework.ipynb
Pipeline complete.
Products are in outputs/tides/
Notebook Model B / Thomas Figure 3 sections are synchronized.
```

The complete validated run includes PySolid, the transparent degree-2 forcing, SPOTL `ertid`, package comparison, Models A–D, and notebook synchronization.

The SLURM wrapper is also available:

```bash
sbatch scripts/tides/run_tides.sbatch
```

## Outputs

A complete run can create:

```text
outputs/tides/
    pysolid_tides.csv
    pysolid_provenance.json

    spotl_ertid_tides.csv
    spotl_provenance.json
    spotl_work/
        ertid.stdin
        ertid.stdout
        ertid.stderr
        strain_az000.txt
        strain_az045.txt
        strain_az090.txt

    analytic_degree2_tides.csv
    analytic_degree2_provenance.json

    forcing_comparison.csv
    forcing_comparison_provenance.json

    model_results.csv
    model_summary.json
    model_provenance.json
```

The model output includes the primary vertical-SAF FNS/RLSS series and separate Thomas-N42W Figure-3-analogue FNS/RLSS series for each available forcing package.

## Open the notebook in Sherlock OnDemand JupyterLab

The supported interactive workflow is Sherlock Open OnDemand JupyterLab.

1. Run the first-time setup above from a Sherlock terminal.
2. If JupyterLab was already running during setup, stop that OnDemand JupyterLab job and launch a new one so the new kernelspec is discovered.
3. Open `notebooks/SAFOD_tides_model_framework.ipynb`.
4. Choose **Kernel -> Change Kernel -> `SAFOD tides (.venv)`**.
5. Run All.

To verify that JupyterLab is using the correct environment, run:

```python
import sys
print(sys.executable)
```

It should print a path ending in:

```text
/safod-tides/.venv/bin/python
```

The notebook reads the CSV/JSON products and does not silently rerun external packages. `RUN_ON_SHERLOCK.sh` also synchronizes the notebook's Model-B and Thomas-Figure-3 explanation with the current implementation before you open it.

## Re-running later

After the first successful setup, you normally only need:

```bash
cd safod-tides
git pull
module load gcc/14.2.0
bash RUN_ON_SHERLOCK.sh
```

You do not need to recreate `.venv` or reinstall PySolid/SPOTL unless the environment or compiled SPOTL installation has been deleted.

## Reproducibility rule

A package curve is shown as a package result only if its numerical output exists. The notebook's provenance table separately reports whether the corresponding provenance record exists.

The transparent degree-2 calculation is an independent check, not a relabeled package result.

## Key sources

- Thomas, A. M., et al. (2012), *Tidal triggering of low frequency earthquakes near Parkfield, California*, JGR Solid Earth, DOI `10.1029/2011JB009036`.
- Agnew, D. C. (2012), *SPOTL: Some Programs for Ocean-Tide Loading*.
- Johnson, C. W., Fu, Y., & Bürgmann, R. (2017), JGR Solid Earth, DOI `10.1002/2017JB014778`.
- Niu, F., et al. (2008), Nature, DOI `10.1038/nature07111`.
- Boness, N. L., & Zoback, M. D. (2004), GRL, DOI `10.1029/2003GL019020`.

## Important model caveats

- PySolid and SPOTL constrain the body-tide forcing; they do not determine the local stress-to-AWD-velocity constitutive law.
- The revised Model B is a **vertical-fault surface-strain stress benchmark**, not the exact tidal stress tensor along the approximately 1 km-deep DAS interval.
- A true approximately 70° dipping-fault calculation requires a full 3-D depth-dependent strain tensor.
- Niu's coefficient is an empirical SAFOD barometric sensitivity measured near 1 km, not a universal tidal sensitivity.
- Model D predicts formation-scale elastic `Vp`/`Vs`; the AWD observable is a coherent borehole-mode apparent velocity.
- No tidal detection is claimed.
