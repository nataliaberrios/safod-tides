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
"$PY" -m pip install "ipykernel>=6.29,<7" nbformat

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
PY

echo
echo "Registering Jupyter kernel..."
"$PY" -m ipykernel install --user \
  --name safod-tides \
  --display-name "SAFOD tides (.venv)"

echo
echo "SPOTL additionally requires gcc, gfortran, and make."
missing=0
for cmd in gcc gfortran make; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "  missing: $cmd"
    missing=1
  else
    echo "  found: $cmd -> $(command -v "$cmd")"
  fi
done

if (( missing )); then
  echo
  echo "Python setup is complete, but SPOTL still needs a GNU compiler toolchain."
  echo "Use 'module spider gcc' to see available compiler modules, load one, then run:"
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
