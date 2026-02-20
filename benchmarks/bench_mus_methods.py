#!/usr/bin/env python3
"""
Benchmark MUS extraction methods on a shared set of UNSAT cases.

Usage:
    uv run python benchmarks/bench_mus_methods.py
    uv run python benchmarks/bench_mus_methods.py --repeats 11 --warmup 1
    uv run python benchmarks/bench_mus_methods.py --verbose
    uv run python benchmarks/bench_mus_methods.py --method-verbose 0
    uv run python benchmarks/bench_mus_methods.py --output-csv benchmarks/mus_runs.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pycsp3 import AllDifferent, Sum, Var, VarArray, clear

from pycsp3_explain import (
    mus,
    mus_bicore,
    mus_bicore_qx,
    mus_cpqx,
    mus_naive,
    quickxplain,
    quickxplain_incremental,
)
from pycsp3_explain.explain.mus import is_mus
from pycsp3_explain.solvers.wrapper import clear_solve_cache

Constraint = Any
CaseBuilder = Callable[[], Tuple[List[Constraint], List[Constraint]]]
MethodFn = Callable[..., List[Constraint]]


def case_pair_conflict() -> Tuple[List[Constraint], List[Constraint]]:
    x = Var(dom=range(10))
    return [x == 5, x == 7], []


def case_with_irrelevant_soft() -> Tuple[List[Constraint], List[Constraint]]:
    x = VarArray(size=6, dom=range(10))
    soft = [
        x[0] == 1,
        x[0] == 2,  # conflict pair
        x[1] == 3,
        x[2] >= 2,
        x[2] <= 8,
        x[3] >= 1,
        x[4] <= 9,
        x[5] >= 0,
    ]
    return soft, []


def case_hard_conflict() -> Tuple[List[Constraint], List[Constraint]]:
    x = VarArray(size=2, dom=range(10))
    hard = [x[0] >= 5]
    soft = [x[0] <= 3, x[1] >= 0]
    return soft, hard


def case_two_disjoint_conflicts() -> Tuple[List[Constraint], List[Constraint]]:
    x = VarArray(size=3, dom=range(10))
    soft = [
        x[0] >= 7,
        x[0] <= 2,  # conflict A
        x[1] == 1,
        x[1] == 2,  # conflict B
        x[2] >= 1,  # irrelevant
    ]
    return soft, []


def case_alldiff_collision() -> Tuple[List[Constraint], List[Constraint]]:
    # Use dom=range(5): with 5 vars and 5 values, AllDifferent is satisfiable alone.
    # The intended conflict is the duplicate value assignment through x[0]==0 and x[4]==0.
    x = VarArray(size=5, dom=range(5))
    soft = [
        AllDifferent(x),
        x[0] == 0,
        x[1] == 1,
        x[2] == 2,
        x[3] == 3,
        x[4] == 0,  # clashes with x[0] only through AllDifferent
        Sum(x) >= 0,  # irrelevant
    ]
    return soft, []


def case_large_sparse_core() -> Tuple[List[Constraint], List[Constraint]]:
    """
    Large soft set with a tiny conflict core.

    Core conflict:
      - x[0] == 1
      - x[0] == 2

    Remaining constraints are satisfiable and mostly independent, to emulate
    large models with many irrelevant soft constraints.
    """
    n = 50
    x = VarArray(size=n, dom=range(50))
    soft: List[Constraint] = [x[0] == 1, x[0] == 2]

    for i in range(1, n):
        soft.append(x[i] >= (i % 5))
        soft.append(x[i] <= 49 - (i % 7))
        soft.append(x[i] + x[i - 1] >= (i % 3))

    return soft, []


CASES: Dict[str, CaseBuilder] = {
    "pair_conflict": case_pair_conflict,
    "with_irrelevant_soft": case_with_irrelevant_soft,
    "hard_conflict": case_hard_conflict,
    "two_disjoint_conflicts": case_two_disjoint_conflicts,
    "alldiff_collision": case_alldiff_collision,
    "large_sparse_core": case_large_sparse_core,
}

METHODS: Dict[str, MethodFn] = {
    "mus_naive": mus_naive,
    "mus": mus,
    "mus_bicore": mus_bicore,
    "mus_bicore_qx": mus_bicore_qx,
    "mus_cpqx": mus_cpqx,
    "quickxplain": quickxplain,
    "quickxplain_incremental": quickxplain_incremental,
}


@dataclass
class RunRecord:
    case: str
    method: str
    run_id: int
    elapsed_s: float
    success: bool
    valid_mus: bool
    mus_size: int
    error: str


@dataclass
class SummaryRow:
    case: str
    method: str
    runs: int
    success_rate: float
    valid_rate: float
    median_ms: Optional[float]
    p90_ms: Optional[float]
    mus_size_median: Optional[float]


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


def run_once(
    case_name: str,
    builder: CaseBuilder,
    method_name: str,
    method: MethodFn,
    solver: str,
    validate: bool,
    run_id: int,
    method_verbose: int,
) -> RunRecord:
    clear()
    clear_solve_cache()
    soft, hard = builder()

    t0 = time.perf_counter()
    try:
        result = method(soft, hard=hard, solver=solver, verbose=method_verbose)
        elapsed = time.perf_counter() - t0
        valid = is_mus(result, hard=hard, solver=solver, verbose=method_verbose) if validate else True
        return RunRecord(
            case=case_name,
            method=method_name,
            run_id=run_id,
            elapsed_s=elapsed,
            success=True,
            valid_mus=valid,
            mus_size=len(result),
            error="",
        )
    except Exception as exc:  # pragma: no cover - benchmark failure path
        elapsed = time.perf_counter() - t0
        return RunRecord(
            case=case_name,
            method=method_name,
            run_id=run_id,
            elapsed_s=elapsed,
            success=False,
            valid_mus=False,
            mus_size=0,
            error=str(exc),
        )


def summarize(records: List[RunRecord]) -> List[SummaryRow]:
    rows: List[SummaryRow] = []
    grouped: Dict[Tuple[str, str], List[RunRecord]] = {}
    for rec in records:
        grouped.setdefault((rec.case, rec.method), []).append(rec)

    for (case_name, method_name), recs in sorted(grouped.items()):
        valid_times = [r.elapsed_s for r in recs if r.success and r.valid_mus]
        valid_sizes = [r.mus_size for r in recs if r.success and r.valid_mus]
        success_rate = sum(1 for r in recs if r.success) / len(recs)
        valid_rate = sum(1 for r in recs if r.success and r.valid_mus) / len(recs)
        rows.append(
            SummaryRow(
                case=case_name,
                method=method_name,
                runs=len(recs),
                success_rate=success_rate,
                valid_rate=valid_rate,
                median_ms=(statistics.median(valid_times) * 1000.0) if valid_times else None,
                p90_ms=(percentile(valid_times, 0.90) * 1000.0) if valid_times else None,
                mus_size_median=statistics.median(valid_sizes) if valid_sizes else None,
            )
        )
    return rows


def print_summary(rows: List[SummaryRow], baseline: str) -> None:
    by_case: Dict[str, List[SummaryRow]] = {}
    for row in rows:
        by_case.setdefault(row.case, []).append(row)

    for case_name in sorted(by_case):
        print(f"\nCase: {case_name}")
        print("method                      median_ms   p90_ms   succ  valid  mus_size")
        for row in sorted(
            by_case[case_name],
            key=lambda r: (r.median_ms is None, r.median_ms if r.median_ms is not None else float("inf")),
        ):
            median_txt = f"{row.median_ms:9.3f}" if row.median_ms is not None else "      n/a"
            p90_txt = f"{row.p90_ms:7.3f}" if row.p90_ms is not None else "   n/a"
            mus_txt = f"{row.mus_size_median:.1f}" if row.mus_size_median is not None else "n/a"
            print(
                f"{row.method:26} {median_txt} {p90_txt} "
                f"{row.success_rate:5.2f} {row.valid_rate:5.2f} {mus_txt}"
            )

    # Geometric mean speedup relative to baseline.
    speedups: Dict[str, List[float]] = {}
    lookup = {(row.case, row.method): row for row in rows}
    methods = sorted(set(row.method for row in rows if row.method != baseline))
    for method_name in methods:
        ratios: List[float] = []
        for case_name in sorted(set(row.case for row in rows)):
            base = lookup.get((case_name, baseline))
            cur = lookup.get((case_name, method_name))
            if not base or not cur:
                continue
            if base.median_ms is None or cur.median_ms is None:
                continue
            if cur.median_ms <= 0:
                continue
            ratios.append(base.median_ms / cur.median_ms)
        if ratios:
            speedups[method_name] = ratios

    if speedups:
        print(f"\nGeometric mean speedup vs baseline '{baseline}':")
        for method_name in sorted(speedups):
            ratios = speedups[method_name]
            gmean = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
            print(f"  {method_name:24} x{gmean:.3f} ({len(ratios)} cases)")


def write_csv(path: Path, run_records: List[RunRecord], summary_rows: List[SummaryRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["case", "method", "run_id", "elapsed_s", "success", "valid_mus", "mus_size", "error"]
        )
        for rec in run_records:
            writer.writerow(
                [rec.case, rec.method, rec.run_id, f"{rec.elapsed_s:.9f}", rec.success, rec.valid_mus, rec.mus_size, rec.error]
            )

    summary_path = path.with_name(f"{path.stem}_summary{path.suffix or '.csv'}")
    with summary_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["case", "method", "runs", "success_rate", "valid_rate", "median_ms", "p90_ms", "mus_size_median"]
        )
        for row in summary_rows:
            writer.writerow(
                [
                    row.case,
                    row.method,
                    row.runs,
                    f"{row.success_rate:.6f}",
                    f"{row.valid_rate:.6f}",
                    "" if row.median_ms is None else f"{row.median_ms:.6f}",
                    "" if row.p90_ms is None else f"{row.p90_ms:.6f}",
                    "" if row.mus_size_median is None else f"{row.mus_size_median:.6f}",
                ]
            )

    print(f"\nWrote run CSV: {path}")
    print(f"Wrote summary CSV: {summary_path}")


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark MUS methods")
    parser.add_argument("--repeats", type=int, default=9, help="Measured runs per method/case")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per method/case")
    parser.add_argument("--solver", default="ace", help="Solver backend (default: ace)")
    parser.add_argument(
        "--methods",
        default=",".join(METHODS.keys()),
        help=f"Comma-separated subset of methods: {','.join(METHODS.keys())}",
    )
    parser.add_argument(
        "--cases",
        default=",".join(CASES.keys()),
        help=f"Comma-separated subset of cases: {','.join(CASES.keys())}",
    )
    parser.add_argument(
        "--baseline",
        default="mus",
        help="Baseline method for speedup summary (default: mus)",
    )
    parser.add_argument("--skip-validate", action="store_true", help="Skip is_mus validation checks")
    parser.add_argument("--output-csv", default="", help="Write run-level CSV to this path")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-run benchmark progress and outcomes",
    )
    parser.add_argument(
        "--method-verbose",
        type=int,
        default=-1,
        help="Verbosity forwarded to MUS methods/is_mus (default: -1)",
    )
    args = parser.parse_args()

    selected_methods = parse_csv_list(args.methods)
    selected_cases = parse_csv_list(args.cases)

    for name in selected_methods:
        if name not in METHODS:
            raise ValueError(f"Unknown method '{name}'. Available: {', '.join(METHODS.keys())}")
    for name in selected_cases:
        if name not in CASES:
            raise ValueError(f"Unknown case '{name}'. Available: {', '.join(CASES.keys())}")
    if args.baseline not in selected_methods:
        raise ValueError("Baseline must be included in --methods")

    run_records: List[RunRecord] = []
    validate = not args.skip_validate

    print("Benchmark configuration:")
    print(f"  solver   : {args.solver}")
    print(f"  methods  : {', '.join(selected_methods)}")
    print(f"  cases    : {', '.join(selected_cases)}")
    print(f"  warmup   : {args.warmup}")
    print(f"  repeats  : {args.repeats}")
    print(f"  validate : {validate}")
    print(f"  verbose  : {args.verbose}")
    print(f"  method-v : {args.method_verbose}")

    for case_name in selected_cases:
        builder = CASES[case_name]
        for method_name in selected_methods:
            method = METHODS[method_name]

            if args.verbose:
                print(f"\n[bench] case={case_name} method={method_name} warmup={args.warmup} repeats={args.repeats}")

            # Warmup (not recorded).
            for w in range(max(0, args.warmup)):
                _ = run_once(
                    case_name=case_name,
                    builder=builder,
                    method_name=method_name,
                    method=method,
                    solver=args.solver,
                    validate=False,
                    run_id=-1,
                    method_verbose=args.method_verbose,
                )
                if args.verbose:
                    print(f"  [warmup {w + 1}/{args.warmup}] done")

            for run_id in range(args.repeats):
                rec = run_once(
                    case_name=case_name,
                    builder=builder,
                    method_name=method_name,
                    method=method,
                    solver=args.solver,
                    validate=validate,
                    run_id=run_id,
                    method_verbose=args.method_verbose,
                )
                run_records.append(rec)
                if args.verbose:
                    status = "ok" if rec.success and rec.valid_mus else "fail"
                    print(
                        f"  [run {run_id + 1}/{args.repeats}] {status} "
                        f"time={rec.elapsed_s * 1000.0:.3f}ms size={rec.mus_size}"
                    )
                    if rec.error:
                        print(f"    error: {rec.error}")

    summary_rows = summarize(run_records)
    print_summary(summary_rows, baseline=args.baseline)

    if args.output_csv:
        write_csv(Path(args.output_csv), run_records, summary_rows)


if __name__ == "__main__":
    main()
