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

# PySolid and the transparent degree-2 calculation are independent of SPOTL.
$PYTHON_BIN scripts/tides/run_pysolid_tides.py
$PYTHON_BIN scripts/tides/run_analytic_degree2.py

if [[ -x "$ROOT/external/spotl/bin/ertid" ]]; then
  echo
  echo "SPOTL executable found; running the independent SPOTL branch."
  $PYTHON_BIN scripts/tides/run_spotl_ertid.py
  $PYTHON_BIN scripts/tides/compare_forcing.py
  $PYTHON_BIN scripts/tides/run_models.py
else
  echo
  echo "WARNING: SPOTL executable is not available yet."
  echo "PySolid + analytic forcing and Models A-D will still be generated."
  echo "The notebook will explicitly mark SPOTL as missing; no surrogate is substituted."
  echo "To add SPOTL later, fix/install external/spotl/bin/ertid and rerun this script."
  $PYTHON_BIN scripts/tides/run_models.py --allow-missing-spotl
fi

# Evaluate transparent depth-dependent stress-sensitivity scenarios. If an
# accepted inputs/awd_depth_localized_thresholds.csv file is present, the
# calculation uses those window-specific empirical thresholds. Otherwise it
# labels the global full-cable Deep-outbound threshold as a placeholder.
$PYTHON_BIN scripts/tides/run_depth_sensitivity.py

# Keep the presentation notebook synchronized with the current mechanics,
# calibration hierarchy, AWD benchmark, and depth-sensitivity scenarios.
$PYTHON_BIN scripts/tides/patch_notebook_model_b.py
$PYTHON_BIN scripts/tides/patch_notebook_depth_sensitivity.py

echo
echo "Pipeline complete."
echo "Products are in outputs/tides/."
echo "Notebook mechanics, model hierarchy, AWD benchmark, and depth-sensitivity sections are synchronized."
echo "Open notebooks/SAFOD_tides_model_framework.ipynb and Run All, or run bash MAKE_NOTEBOOK_HTML.sh."
