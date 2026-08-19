#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BASE_PYTHON="${BASE_PYTHON:-python}"
VENV="$ROOT/.venv"

echo "SAFOD tides Sherlock setup"
echo "root: $ROOT"
echo "base python: $($BASE_PYTHON --version)"
echo

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating lightweight virtual environment at $VENV ..."
  "$BASE_PYTHON" -m venv "$VENV"
else
  echo "Using existing virtual environment at $VENV"
fi

PY="$VENV/bin/python"

echo "Updating pip/build tooling ..."
"$PY" -m pip install --upgrade pip setuptools wheel

echo
echo "Installing binary scientific wheels compatible with older Sherlock glibc ..."
"$PY" -m pip install --only-binary=:all: \
  "numpy==1.26.4" \
  "scipy==1.13.1" \
  "pandas==2.2.2" \
  "pillow==10.4.0" \
  "matplotlib==3.8.4"

echo
echo "Installing Sherlock-compatible pyzmq wheel ..."
# pyzmq 27.x CPython 3.11 x86_64 wheels require newer glibc than Sherlock.
# 25.1.2 publishes a manylinux2014 / glibc >=2.17 CPython 3.11 wheel.
# Force a binary wheel here so pip never falls back to compiling pyzmq
# with Sherlock's older system compiler/C language defaults.
"$PY" -m pip install --only-binary=:all: "pyzmq==25.1.2"

echo
echo "Installing notebook support ..."
"$PY" -m pip install "ipykernel>=6.29,<7" nbformat nbconvert

echo
echo "Installing PySolid build tooling ..."
"$PY" -m pip install cmake scikit-build-core "setuptools_scm[toml]>=6.2"

echo
echo "Installing PySolid 0.3.4 from source against the pinned NumPy ABI ..."
"$PY" -m pip install --no-deps --no-build-isolation --no-binary=pysolid "pysolid==0.3.4"

echo
"$PY" - <<'PY'
import sys
import numpy, pandas, matplotlib, scipy
import PIL
import pysolid
import nbformat
import nbconvert
import zmq
from importlib.metadata import version
print("Python environment check: PASS")
print("  python    :", sys.version.split()[0])
print("  numpy     :", numpy.__version__)
print("  scipy     :", scipy.__version__)
print("  pandas    :", pandas.__version__)
print("  pillow    :", PIL.__version__)
print("  matplotlib:", matplotlib.__version__)
print("  pysolid   :", version("pysolid"))
print("  pyzmq     :", zmq.__version__)
print("  nbformat  :", nbformat.__version__)
print("  nbconvert :", nbconvert.__version__)
PY

echo
echo "Registering Jupyter kernel..."
"$PY" -m ipykernel install --user \
  --name safod-tides \
  --display-name "SAFOD tides (.venv)"

echo
echo "Preparing GNU compiler toolchain for SPOTL ..."
# The SPOTL build has been validated on Sherlock with gcc/14.2.0.
# Do not silently fall back to Sherlock's older /usr/bin gcc/gfortran.
if [[ "${SAFOD_SKIP_GCC_MODULE_LOAD:-0}" != "1" ]]; then
  if ! command -v module >/dev/null 2>&1; then
    for init in /etc/profile.d/modules.sh /etc/profile.d/lmod.sh; do
      if [[ -r "$init" ]]; then
        # shellcheck disable=SC1090
        source "$init"
        break
      fi
    done
  fi

  if command -v module >/dev/null 2>&1; then
    echo "Loading validated Sherlock module: gcc/14.2.0"
    module load gcc/14.2.0
  else
    echo "WARNING: could not initialize the Sherlock module command."
    echo "Load gcc/14.2.0 in your shell before rerunning this setup."
  fi
fi

echo "SPOTL requires gcc, gfortran, and make."
missing=0
for cmd in gcc gfortran make; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "  missing: $cmd"
    missing=1
  else
    echo "  found: $cmd -> $(command -v "$cmd")"
  fi
done

if command -v gcc >/dev/null 2>&1; then
  echo "  gcc version: $(gcc -dumpfullversion -dumpversion 2>/dev/null || gcc -dumpversion)"
fi
if command -v gfortran >/dev/null 2>&1; then
  echo "  gfortran version: $(gfortran -dumpfullversion -dumpversion 2>/dev/null || gfortran -dumpversion)"
fi

if (( missing )); then
  echo
  echo "Python setup is complete, but SPOTL still needs a GNU compiler toolchain."
  echo "On Sherlock run:"
  echo "  module load gcc/14.2.0"
  echo "  bash scripts/tides/install_spotl.sh"
else
  echo
  echo "GNU compiler toolchain is available. Installing SPOTL ..."
  bash scripts/tides/install_spotl.sh
fi

echo
echo "Setup complete."
echo "For Sherlock OnDemand JupyterLab, restart the JupyterLab session after first-time setup"
echo "and choose the kernel: SAFOD tides (.venv)"
echo "For command-line runs, RUN_ON_SHERLOCK.sh automatically uses $VENV/bin/python."
echo "To execute the notebook and make a viewable HTML without OnDemand, run: bash MAKE_NOTEBOOK_HTML.sh"
