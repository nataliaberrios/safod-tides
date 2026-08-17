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

# Avoid a full conda solve on Sherlock login nodes.  Python 3.11 is sufficient
# for this project, and PySolid 0.3.4 publishes CPython-3.11 Linux wheels.
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating lightweight virtual environment at $VENV ..."
  "$BASE_PYTHON" -m venv "$VENV"
else
  echo "Using existing virtual environment at $VENV"
fi

echo "Installing/updating Python dependencies with pip ..."
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -r requirements.txt

echo
"$VENV/bin/python" - <<'PY'
import sys
import numpy, pandas, matplotlib, scipy
import pysolid
from importlib.metadata import version
print("Python environment check: PASS")
print("  python :", sys.version.split()[0])
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
