#!/bin/bash
#SBATCH --job-name=safod_tides
#SBATCH --time=01:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=outputs/tides/slurm-%j.out

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Activate the environment before submission, or set this variable:
#   export SAFOD_TIDES_ACTIVATE="source /path/to/conda.sh && conda activate safod-tides"
if [[ -n "${SAFOD_TIDES_ACTIVATE:-}" ]]; then
  eval "$SAFOD_TIDES_ACTIVATE"
fi

bash scripts/tides/run_all.sh
