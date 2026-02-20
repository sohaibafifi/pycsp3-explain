#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

MANIFEST="${MANIFEST:-$SCRIPT_DIR/sat11_manifest.tsv}"
if [[ ! -f "$MANIFEST" ]]; then
  echo "Manifest not found: $MANIFEST"
  echo "Build it first with: python3 $SCRIPT_DIR/build_manifest.py"
  exit 1
fi

METHODS_CSV="${METHODS_CSV:-marco,marco_core_cpmpy}"
REPEATS="${REPEATS:-1}"

IFS=',' read -r -a METHODS <<< "$METHODS_CSV"
N_METHODS="${#METHODS[@]}"
N_INSTANCES="$(awk 'NF{c++} END{print c+0}' "$MANIFEST")"
TOTAL=$((N_INSTANCES * N_METHODS * REPEATS))
if (( TOTAL <= 0 )); then
  echo "No jobs to submit (instances=$N_INSTANCES methods=$N_METHODS repeats=$REPEATS)"
  exit 1
fi

ARRAY_MAX_PARALLEL="${ARRAY_MAX_PARALLEL:-64}"
CPUS_PER_TASK="${CPUS_PER_TASK:-1}"
MEM_PER_TASK="${MEM_PER_TASK:-8G}"
WALLTIME="${WALLTIME:-02:00:00}"
JOB_NAME="${JOB_NAME:-marco-sat11}"

RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"
mkdir -p "$RESULTS_DIR/logs"
LOG_PATTERN="${LOG_PATTERN:-$RESULTS_DIR/logs/%A_%a.out}"

echo "Submitting Slurm array"
echo "  manifest      : $MANIFEST"
echo "  instances     : $N_INSTANCES"
echo "  methods       : $METHODS_CSV"
echo "  repeats       : $REPEATS"
echo "  total tasks   : $TOTAL"
echo "  array limit   : $ARRAY_MAX_PARALLEL"
echo "  resources     : cpu=$CPUS_PER_TASK mem=$MEM_PER_TASK time=$WALLTIME"

sbatch \
  --job-name="$JOB_NAME" \
  --array="0-$((TOTAL-1))%$ARRAY_MAX_PARALLEL" \
  --cpus-per-task="$CPUS_PER_TASK" \
  --mem="$MEM_PER_TASK" \
  --time="$WALLTIME" \
  --output="$LOG_PATTERN" \
  --export=ALL,REPO_ROOT="$REPO_ROOT",MANIFEST="$MANIFEST",RESULTS_DIR="$RESULTS_DIR",METHODS_CSV="$METHODS_CSV",REPEATS="$REPEATS" \
  "$SCRIPT_DIR/run_array_task.sh" \
  "$@"
