# SAFOD solid-Earth tides — Sherlock reproducible framework

This repository separates **scientific execution** from **scientific presentation**.

- `scripts/tides/` contains the actual package calls and Models A–D.
- `outputs/tides/` contains generated numerical products and run provenance.
- `notebooks/SAFOD_tides_model_framework.ipynb` reads those products and explains them.
- `config.json` contains every editable site/time/model parameter.

The notebook **does not install packages or compile Fortran**.

## What gets run

The pipeline runs:

1. **PySolid 0.3.4**
   - solid-Earth tide ENU displacement at SAFOD
   - a spatial stencil around SAFOD
   - horizontal strain tensor from the displacement gradients

2. **SPOTL 3.3.0.2 / `ertid`**
   - official Scripps code
   - extensional strain at 0°, 45°, and 90°
   - reconstruction of `eps_NN`, `eps_EE`, and `eps_NE`

3. **Transparent degree-2 calculation**
   - independent Sun/Moon + PREM Love-number calculation

4. **Package comparison**
   - correlations, amplitudes, RMS residuals

5. **Models A–D**
   - Model A: Niu 240 Pa shortcut
   - Model B: strain -> elastic stress -> fault stress -> Niu
   - Model C: direct published strain sensitivity
   - Model D: crack closure -> effective moduli -> Vp/Vs

Every script writes a JSON provenance record containing the host, time, Python version, script hash, and (when available) git commit.

## First-time Sherlock setup

Do this on a **login node**, because the SPOTL download is about 200 MB.

```bash
cd safod-tides
git pull
bash scripts/tides/setup_sherlock.sh
```

The setup script intentionally uses a lightweight project-local Python virtual environment (`.venv`) rather than solving a new conda environment on a Sherlock login node. PySolid 0.3.4 supports Python 3.11.

If the setup script reports that `gfortran`, `gcc`, or `make` is missing, load a GNU compiler toolchain first:

```bash
module spider gcc
# load an appropriate GCC module for your environment
bash scripts/tides/install_spotl.sh
```

The official SPOTL distribution states that it is intended to compile on systems supporting GNU Fortran and C compilers.

The SPOTL installer accepts both `install.compile` (the name used in the 2013 manual) and `install.comp` (found in distributed copies of the package), preserves the downloaded archive, and saves compiler stdout/stderr for inspection.

## Run the complete calculation

No environment activation is required after setup. The runner automatically uses `.venv/bin/python` when it exists:

```bash
bash RUN_ON_SHERLOCK.sh
```

or submit through SLURM:

```bash
sbatch scripts/tides/run_tides.sbatch
```

The SLURM file intentionally does **not** hard-code an account or partition.

## Outputs

A successful run creates:

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

The saved `ertid.stdin`, stdout, stderr, and raw strain files make the SPOTL run inspectable rather than opaque.

## Open the notebook

After the scripts finish:

```bash
.venv/bin/jupyter lab notebooks/SAFOD_tides_model_framework.ipynb
```

The notebook reads the CSV/JSON products. It does not silently rerun external packages.

## Reproducibility rule

A package curve is shown as a package result only if its output file exists and has a corresponding provenance record.

The transparent degree-2 calculation is kept as an independent check, not relabeled as package output.

## SPOTL sources

Official distribution and documentation:

- Duncan C. Agnew, SPOTL 3.3.0.2, Scripps Institution of Oceanography.
- `ertid(1)`: computes elastic-Earth body tides directly from Sun/Moon positions; supports up to three strain tides.
- Strain output is nanostrain, positive for extension.

Relevant California precedent includes Thomas et al. (2012), Johnson et al. (2017), Shelly et al. (2016), and Lu et al. (2018).

## Important model caveats

- PySolid and SPOTL solve the **body-tide forcing** problem; they do not determine the local stress-to-AWD-velocity constitutive law.
- Model B currently uses a surface plane-stress elastic closure; this is a scenario, not a rigorous 1-km stress tensor.
- Niu's coefficient is an empirical SAFOD barometric sensitivity measured near 1 km, not a universal tidal sensitivity.
- Model D predicts formation-scale elastic `Vp`/`Vs`; the AWD observable is a coherent borehole-mode apparent velocity.
- No tidal detection is claimed.
