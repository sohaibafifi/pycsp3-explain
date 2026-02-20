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

RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"
mkdir -p "$RESULTS_DIR/logs"

CORES="${CORES:-1}"
WALLTIME="${WALLTIME:-2:00:00}"
JOB_NAME="${JOB_NAME:-marco-sat11}"
USE_LOOP="${USE_LOOP:-0}"

echo "Submitting OAR jobs"
echo "  manifest      : $MANIFEST"
echo "  instances     : $N_INSTANCES"
echo "  methods       : $METHODS_CSV"
echo "  repeats       : $REPEATS"
echo "  total tasks   : $TOTAL"
echo "  resources     : core=$CORES walltime=$WALLTIME"

COMMON_ENV="REPO_ROOT=$REPO_ROOT MANIFEST=$MANIFEST RESULTS_DIR=$RESULTS_DIR METHODS_CSV=$METHODS_CSV REPEATS=$REPEATS"

if [[ "$USE_LOOP" == "1" ]]; then
  echo "Using loop submission mode (one oarsub per task)"
  for i in $(seq 0 $((TOTAL - 1))); do
    oarsub \
      -n "$JOB_NAME" \
      -l "/nodes=1/core=${CORES},walltime=${WALLTIME}" \
      "export $COMMON_ENV TASK_ID=$i; bash $SCRIPT_DIR/run_array_task.sh" \
      "$@"
  done
else
  echo "Using OAR array submission mode"
  oarsub \
    -n "$JOB_NAME" \
    --array "0-$((TOTAL - 1))" \
    -l "/nodes=1/core=${CORES},walltime=${WALLTIME}" \
    "export $COMMON_ENV; bash $SCRIPT_DIR/run_array_task.sh" \
    "$@"
fi
