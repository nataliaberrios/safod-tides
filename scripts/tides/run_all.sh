#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"

echo "============================================================"
echo "SAFOD tide-model pipeline"
echo "root: $ROOT"
echo "python: $($PYTHON --version)"
echo "host: $(hostname)"
echo "============================================================"

if [[ ! -x "$ROOT/external/spotl/bin/ertid" ]]; then
  echo "SPOTL executable is missing."
  echo "Run once on a Sherlock login node:"
  echo "  bash scripts/tides/install_spotl.sh"
  exit 10
fi

$PYTHON scripts/tides/run_pysolid_tides.py
$PYTHON scripts/tides/run_spotl_ertid.py
$PYTHON scripts/tides/run_analytic_degree2.py
$PYTHON scripts/tides/compare_forcing.py
$PYTHON scripts/tides/run_models.py

echo
echo "Pipeline complete."
echo "Products are in outputs/tides/"
echo "Open notebooks/SAFOD_tides_model_framework.ipynb"
