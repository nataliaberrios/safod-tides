#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
JUPYTER="$ROOT/.venv/bin/jupyter"
NOTEBOOK="$ROOT/notebooks/SAFOD_tides_model_framework.ipynb"
EXECUTED="$ROOT/notebooks/SAFOD_tides_model_framework.executed.ipynb"
HTML="$ROOT/notebooks/SAFOD_tides_model_framework.executed.html"

if [[ ! -x "$PY" ]]; then
  echo "ERROR: project virtual environment not found: $PY"
  echo "Run: bash scripts/tides/setup_sherlock.sh"
  exit 1
fi

if [[ ! -f "$NOTEBOOK" ]]; then
  echo "ERROR: notebook not found: $NOTEBOOK"
  exit 2
fi

if ! "$PY" -c 'import nbconvert, nbformat, ipykernel' >/dev/null 2>&1; then
  echo "ERROR: notebook export dependencies are missing from .venv."
  echo "Run: bash scripts/tides/setup_sherlock.sh"
  exit 3
fi

if [[ ! -f "$ROOT/outputs/tides/model_results.csv" ]]; then
  echo "ERROR: model outputs are missing."
  echo "Run the scientific pipeline first: bash RUN_ON_SHERLOCK.sh"
  exit 4
fi

echo "Executing notebook with kernel: safod-tides"
"$JUPYTER" nbconvert \
  --to notebook \
  --execute "$NOTEBOOK" \
  --output "$(basename "$EXECUTED")" \
  --output-dir "$(dirname "$EXECUTED")" \
  --ExecutePreprocessor.kernel_name=safod-tides \
  --ExecutePreprocessor.timeout=600

echo
echo "Converting executed notebook to HTML"
"$JUPYTER" nbconvert \
  --to html \
  "$EXECUTED" \
  --output "$(basename "$HTML")" \
  --output-dir "$(dirname "$HTML")"

echo
echo "Notebook HTML complete."
echo "Executed notebook: $EXECUTED"
echo "Viewable HTML:      $HTML"
