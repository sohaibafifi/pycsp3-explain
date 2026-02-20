#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

MANIFEST="${MANIFEST:-$SCRIPT_DIR/sat11_manifest.tsv}"
DATASET_ROOT="${DATASET_ROOT:-$REPO_ROOT/benchmarks/SAT11-Competition-MUS-SelectedBenchmarks}"
RESULTS_DIR="${RESULTS_DIR:-$SCRIPT_DIR/results}"

METHODS_CSV="${METHODS_CSV:-marco,marco_core_cpmpy}"
REPEATS="${REPEATS:-1}"
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
if [[ -z "${TASK_ID}" ]]; then
  echo "No task index found. Provide SLURM_ARRAY_TASK_ID, OAR_ARRAY_INDEX, OAR_JOBARRAY_INDEX, or TASK_ID."
  exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "Manifest not found: $MANIFEST"
  exit 1
fi

INSTANCES=()
while IFS= read -r line; do
  [[ -z "${line//[[:space:]]/}" ]] && continue
  INSTANCES+=("$line")
done < "$MANIFEST"
if [[ "${#INSTANCES[@]}" -eq 0 ]]; then
  echo "Manifest is empty: $MANIFEST"
  exit 1
fi

IFS=',' read -r -a METHODS <<< "$METHODS_CSV"
if [[ "${#METHODS[@]}" -eq 0 ]]; then
  echo "METHODS_CSV yielded no methods: $METHODS_CSV"
  exit 1
fi

N_INST="${#INSTANCES[@]}"
N_METHOD="${#METHODS[@]}"
TOTAL=$((N_INST * N_METHOD * REPEATS))

if (( TASK_ID < 0 || TASK_ID >= TOTAL )); then
  echo "TASK_ID=${TASK_ID} out of range [0,$((TOTAL-1))]"
  exit 1
fi

inst_idx=$(( TASK_ID % N_INST ))
tmp=$(( TASK_ID / N_INST ))
meth_idx=$(( tmp % N_METHOD ))
rep_id=$(( tmp / N_METHOD ))

line="${INSTANCES[$inst_idx]}"
instance_rel="$(printf "%s" "$line" | cut -f1)"
method="${METHODS[$meth_idx]}"

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

CSV_OUT="$RESULTS_DIR/runs/${method}__rep${rep_id}__inst${inst_idx}.csv"

CMD=(
  python3 "$REPO_ROOT/benchmarks/bench_marco_sat11.py"
  --dataset-root "$DATASET_ROOT"
  --methods "$method"
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

echo "[task] id=$TASK_ID inst_idx=$inst_idx method=$method rep=$rep_id"
echo "[task] instance=$instance_rel"
echo "[task] output=$CSV_OUT"

cd "$REPO_ROOT"
"${CMD[@]}"
