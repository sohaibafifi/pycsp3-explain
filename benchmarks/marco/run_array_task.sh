#!/usr/bin/env bash

# set -euo pipefail
. /nfs/opt/env/env.sh
module load conda
conda activate csp


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

DATASET_ROOT="${DATASET_ROOT:-$REPO_ROOT/benchmarks/SAT11-Competition-MUS-SelectedBenchmarks}"
RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"

TIMEOUT_S="${TIMEOUT_S:-3600}"

RUN_VALIDATE="${RUN_VALIDATE:-0}"
RUN_VERIFY_UNSAT="${RUN_VERIFY_UNSAT:-0}"
MAX_OUTPUTS="${MAX_OUTPUTS:-0}"
NO_SOLUTION_HINT="${NO_SOLUTION_HINT:-0}"

CORE_HANDOFF="${CORE_HANDOFF:--1}"
CORE_BASE_RATIO="${CORE_BASE_RATIO:-2}"
CORE_BACKOFF_CAP="${CORE_BACKOFF_CAP:-8}"
NO_FEEDBACK="${NO_FEEDBACK:-0}"
FEEDBACK_SAT_CLAUSE_MAX="${FEEDBACK_SAT_CLAUSE_MAX:-12}"
FEEDBACK_UNSAT_CLAUSE_MAX="${FEEDBACK_UNSAT_CLAUSE_MAX:-12}"
FEEDBACK_MAX_CLAUSES="${FEEDBACK_MAX_CLAUSES:-2000}"

SOLVER="${SOLVER:-ortools}"
MAP_SOLVER="${MAP_SOLVER:-ortools}"

TASK_ID="${SLURM_ARRAY_TASK_ID:-${OAR_ARRAY_INDEX:-${OAR_JOBARRAY_INDEX:-${TASK_ID:-}}}}"
TASK_LABEL="${TASK_ID:-param}"

instance_rel=""
method=""
rep_id=""
param_solver=""
param_map_solver=""

# Mode A: first argument is a params file (line selection by task index).
if [[ $# -ge 1 && -f "${1}" ]]; then
  PARAMS_FILE="${1}"
  if [[ -z "${TASK_ID}" ]]; then
    echo "No task index found. Provide SLURM_ARRAY_TASK_ID/OAR_ARRAY_INDEX/OAR_JOBARRAY_INDEX/TASK_ID."
    exit 1
  fi

  line="$(sed -n "${TASK_ID}p" "${PARAMS_FILE}")"
  if [[ -z "${line}" ]]; then
    echo "No params row for task index ${TASK_ID} in ${PARAMS_FILE}"
    exit 1
  fi

  IFS=$'\t' read -r instance_rel method rep_id param_solver param_map_solver _ <<< "${line}"
  if [[ -z "${instance_rel}" || -z "${method}" || -z "${rep_id}" ]]; then
    read -r instance_rel method rep_id param_solver param_map_solver _ <<< "${line}"
  fi
else
  # Mode B: direct row arguments (for OAR --array-param-file), expected:
  #   run_array_task.sh <instance_rel> <method> <rep_id> [solver] [map_solver]
  instance_rel="${1:-}"
  method="${2:-}"
  rep_id="${3:-}"
  param_solver="${4:-}"
  param_map_solver="${5:-}"
fi

if [[ -z "${instance_rel}" || -z "${method}" || -z "${rep_id}" ]]; then
  echo "Invalid task parameters. Need: <instance_rel> <method> <rep_id>."
  echo "Either call with a params file + task index env, or pass direct args."
  exit 1
fi

# Precedence: per-task params > env vars > defaults.
if [[ -n "${param_solver}" ]]; then
  SOLVER="${param_solver}"
fi
if [[ -n "${param_map_solver}" ]]; then
  MAP_SOLVER="${param_map_solver}"
fi

# Each array task runs a single method; keep baseline aligned to avoid CLI mismatch.
BASELINE="$method"

mkdir -p "$RESULTS_DIR/runs" "$RESULTS_DIR/logs"

# Activate project venv if available.
if [[ -f "$REPO_ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
fi

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

JOB_LABEL="${SLURM_ARRAY_JOB_ID:-${OAR_JOB_ID:-local}}"
instance_tag="$(printf "%s" "$instance_rel" | tr '/.' '__' | tr -cd '[:alnum:]_-' | cut -c1-80)"
CSV_OUT="$RESULTS_DIR/runs/${method}__rep${rep_id}__${instance_tag}__job${JOB_LABEL}__task${TASK_LABEL}.csv"

CMD=(
  /nfs/home/exterieur/slafifi/.local/bin/uv run python "$REPO_ROOT/benchmarks/bench_marco_sat11.py"
  --dataset-root "$DATASET_ROOT"
  --methods "$method"
  --baseline "$BASELINE"
  --instances "$instance_rel"
  --max-vars 0
  --max-clauses 0
  --max-files 1
  --repeats 1
  --warmup 0
  --timeout-s "$TIMEOUT_S"
  --solver "$SOLVER"
  --map-solver "$MAP_SOLVER"
  --max-outputs "$MAX_OUTPUTS"
  --core-handoff "$CORE_HANDOFF"
  --core-base-ratio "$CORE_BASE_RATIO"
  --core-backoff-cap "$CORE_BACKOFF_CAP"
  --feedback-sat-clause-max "$FEEDBACK_SAT_CLAUSE_MAX"
  --feedback-unsat-clause-max "$FEEDBACK_UNSAT_CLAUSE_MAX"
  --feedback-max-clauses "$FEEDBACK_MAX_CLAUSES"
  --output-csv "$CSV_OUT"
)

if [[ "$RUN_VALIDATE" == "1" ]]; then
  CMD+=(--validate)
fi
if [[ "$RUN_VERIFY_UNSAT" == "1" ]]; then
  CMD+=(--verify-unsat)
fi
if [[ "$NO_SOLUTION_HINT" == "1" ]]; then
  CMD+=(--no-solution-hint)
fi
if [[ "$NO_FEEDBACK" == "1" ]]; then
  CMD+=(--no-feedback)
fi

echo "[task] id=${TASK_LABEL} method=$method rep=$rep_id"
echo "[task] instance=$instance_rel"
echo "[task] solver=$SOLVER map_solver=$MAP_SOLVER"
echo "[task] output=$CSV_OUT"
echo "[task] command: $CMD"

cd "$REPO_ROOT"
"${CMD[@]}"
