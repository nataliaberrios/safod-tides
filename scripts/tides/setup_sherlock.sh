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

# Sherlock's older glibc cannot use some current manylinux_2_27/2_28 wheels.
# In particular, unconstrained pip may try to build current SciPy from source,
# which then fails because system OpenBLAS development libraries are unavailable.
# Use versions that publish CPython-3.11 manylinux_2_17 wheels instead.
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
echo "Installing binary NumPy/SciPy wheels compatible with older Sherlock glibc ..."
"$PY" -m pip install --only-binary=:all: \
  "numpy==1.26.4" \
  "scipy==1.13.1"

echo
echo "Installing notebook/plotting dependencies ..."
"$PY" -m pip install \
  "pandas>=2.0,<3.0" \
  "matplotlib>=3.7,<4.0" \
  jupyter nbconvert

echo
echo "Installing PySolid build tooling ..."
"$PY" -m pip install cmake scikit-build-core "setuptools_scm[toml]>=6.2"

echo
echo "Installing PySolid 0.3.4 from source against the pinned NumPy ABI ..."
# PySolid's published Linux wheel requires newer glibc than many Sherlock nodes.
# Build the small Fortran extension locally instead. --no-build-isolation keeps
# the build on the NumPy 1.26.4 ABI that will be used at runtime.
"$PY" -m pip install --no-deps --no-build-isolation --no-binary=pysolid "pysolid==0.3.4"

echo
"$PY" - <<'PY'
import sys
import numpy, pandas, matplotlib, scipy
import pysolid
from importlib.metadata import version
print("Python environment check: PASS")
print("  python :", sys.version.split()[0])
print("  numpy  :", numpy.__version__)
print("  scipy  :", scipy.__version__)
print("  pysolid:", version("pysolid"))
PY

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
echo "Setup complete. You do NOT need to activate the venv to use RUN_ON_SHERLOCK.sh;"
echo "the pipeline automatically uses $VENV/bin/python when it exists."
