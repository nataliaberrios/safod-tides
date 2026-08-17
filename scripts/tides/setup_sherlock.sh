#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "This setup intentionally does not guess Sherlock module names."
echo

if command -v conda >/dev/null 2>&1; then
  echo "Creating/updating conda environment 'safod-tides' from environment.yml ..."
  conda env create -f environment.yml 2>/dev/null || conda env update -f environment.yml --prune
  echo
  echo "Activate it with:"
  echo "  conda activate safod-tides"
else
  echo "conda was not found."
  echo "Use an existing Python environment and run:"
  echo "  python -m pip install -r requirements.txt"
fi

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
  echo "Load a GNU compiler toolchain on Sherlock, then run:"
  echo "  bash scripts/tides/install_spotl.sh"
  echo "Use 'module spider gcc' to see available compiler modules."
else
  echo
  bash scripts/tides/install_spotl.sh
fi
