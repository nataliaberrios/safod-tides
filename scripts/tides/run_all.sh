#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="python"
fi

echo "============================================================"
echo "SAFOD tide-model pipeline"
echo "root: $ROOT"
echo "python: $($PYTHON_BIN --version)"
echo "python exe: $PYTHON_BIN"
echo "host: $(hostname)"
echo "============================================================"

if [[ ! -x "$ROOT/external/spotl/bin/ertid" ]]; then
  echo "SPOTL executable is missing."
  echo "Run once on a Sherlock login node:"
  echo "  bash scripts/tides/install_spotl.sh"
  exit 10
fi

$PYTHON_BIN scripts/tides/run_pysolid_tides.py
$PYTHON_BIN scripts/tides/run_spotl_ertid.py
$PYTHON_BIN scripts/tides/run_analytic_degree2.py
$PYTHON_BIN scripts/tides/compare_forcing.py
$PYTHON_BIN scripts/tides/run_models.py

# Keep the presentation notebook synchronized with the current Model-B
# formulation without putting package installation/Fortran code into it.
$PYTHON_BIN scripts/tides/patch_notebook_model_b.py

echo
echo "Pipeline complete."
echo "Products are in outputs/tides/"
echo "Notebook Model B / Thomas Figure 3 sections are synchronized."
echo "Open notebooks/SAFOD_tides_model_framework.ipynb and Run All."
