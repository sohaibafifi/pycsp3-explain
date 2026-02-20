#!/usr/bin/env python3
"""
Benchmark CPMPy MARCO methods on shared UNSAT cases.

Compares:
- CPMPy original MARCO (`cpmpy.tools.explain.marco.marco`)
- CPMPy MARCO-ADAPTIVE (`benchmarks.cpmpy_marco_adaptive.marco_adaptive`)

Usage:
    python benchmarks/bench_cpmpy_marco_methods.py
    python benchmarks/bench_cpmpy_marco_methods.py --solver z3 --map-solver z3
    python benchmarks/bench_cpmpy_marco_methods.py --repeats 7 --warmup 1 --verbose
    python benchmarks/bench_cpmpy_marco_methods.py --output-csv benchmarks/cpmpy_marco_runs.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Sequence, Tuple

try:
    import cpmpy as cp
except ImportError:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "libs" / "cpmpy"))
    import cpmpy as cp

from cpmpy.tools.explain.marco import marco as cpmpy_marco

if __package__:
    from .cpmpy_marco_adaptive import marco_adaptive
else:
    from cpmpy_marco_adaptive import marco_adaptive

Constraint = object
CaseBuilder = Callable[[], Tuple[List[Constraint], List[Constraint]]]
MarcoMethod = Callable[..., Iterator[Tuple[str, List[Constraint]]]]


def case_pair_conflict() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 9, name="x")
    return [x == 5, x == 7], []


def case_three_way_conflict() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 9, name="x")
    return [x == 1, x == 2, x == 3], []


def case_hard_conflict() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 9, shape=2, name="x")
    hard = [x[0] >= 5]
    soft = [x[0] <= 3, x[1] >= 0]
    return soft, hard


def case_two_disjoint_conflicts() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 9, shape=3, name="x")
    soft = [
        x[0] >= 7,
        x[0] <= 2,
        x[1] == 1,
        x[1] == 2,
        x[2] >= 1,
    ]
    return soft, []


def case_alldiff_collision() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 4, shape=5, name="x")
    soft = [
        cp.AllDifferent(x),
        x[0] == 0,
        x[1] == 1,
        x[2] == 2,
        x[3] == 3,
        x[4] == 0,
        cp.sum(x) >= 0,
    ]
    return soft, []


def case_large_irrelevant_pair_80() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 99, shape=40, name="x")
    soft: List[Constraint] = [
        x[0] == 1,
        x[0] == 2,
    ]
    for i in range(1, 40):
        soft.append(x[i] >= 0)
        soft.append(x[i] <= 99)
    return soft, []


def case_large_irrelevant_pair_200() -> Tuple[List[Constraint], List[Constraint]]:
    """
    One tiny conflict embedded in a much larger soft set (200 soft constraints, 100 vars).
    """
    x = cp.intvar(0, 999, shape=100, name="x")
    soft: List[Constraint] = [
        x[0] == 1,
        x[0] == 2,
    ]
    for i in range(1, 100):
        soft.append(x[i] >= 0)
        soft.append(x[i] <= 999)
    return soft, []


def case_two_conflicts_irrelevant_60() -> Tuple[List[Constraint], List[Constraint]]:
    x = cp.intvar(0, 99, shape=30, name="x")
    soft: List[Constraint] = [
        x[0] == 1,
        x[0] == 2,
        x[1] == 3,
        x[1] == 4,
    ]
    for i in range(2, 30):
        soft.append(x[i] >= 0)
        soft.append(x[i] <= 99)
    return soft, []


def case_three_conflicts_irrelevant_120() -> Tuple[List[Constraint], List[Constraint]]:
    """
    Three disjoint conflicts plus many irrelevant constraints (120 soft constraints, 60 vars).
    """
    x = cp.intvar(0, 199, shape=60, name="x")
    soft: List[Constraint] = [
        x[0] == 1,
        x[0] == 2,
        x[1] == 3,
        x[1] == 4,
        x[2] == 5,
        x[2] == 6,
    ]
    for i in range(3, 60):
        soft.append(x[i] >= 0)
        soft.append(x[i] <= 199)
    return soft, []


def case_hard_conflict_irrelevant_150() -> Tuple[List[Constraint], List[Constraint]]:
    """
    Soft-vs-hard singleton conflict with many irrelevant soft constraints
    (150 soft constraints, 75 vars).
    """
    x = cp.intvar(0, 99, shape=75, name="x")
    hard = [x[0] >= 20]
    soft: List[Constraint] = [
        x[0] <= 10,
        x[1] >= 0,
    ]
    for i in range(1, 75):
        soft.append(x[i] >= 0)
        soft.append(x[i] <= 99)
    return soft, hard


def case_alldiff_dense_core_24() -> Tuple[List[Constraint], List[Constraint]]:
    n = 24
    x = cp.intvar(0, n - 1, shape=n, name="x")
    soft: List[Constraint] = [cp.AllDifferent(x)]
    for i in range(n - 1):
        soft.append(x[i] == i)
    soft.append(x[n - 1] == 0)
    return soft, []


def case_alldiff_dense_core_36() -> Tuple[List[Constraint], List[Constraint]]:
    """
    Larger dense AllDifferent setting with one duplicate assignment (36 vars).
    """
    n = 36
    x = cp.intvar(0, n - 1, shape=n, name="x")
    soft: List[Constraint] = [cp.AllDifferent(x)]
    for i in range(n - 1):
        soft.append(x[i] == i)
    soft.append(x[n - 1] == 0)
    return soft, []


CASES: Dict[str, CaseBuilder] = {
    "pair_conflict": case_pair_conflict,
    "three_way_conflict": case_three_way_conflict,
    "hard_conflict": case_hard_conflict,
    "two_disjoint_conflicts": case_two_disjoint_conflicts,
    "alldiff_collision": case_alldiff_collision,
    "large_irrelevant_pair_80": case_large_irrelevant_pair_80,
    "large_irrelevant_pair_200": case_large_irrelevant_pair_200,
    "two_conflicts_irrelevant_60": case_two_conflicts_irrelevant_60,
    "three_conflicts_irrelevant_120": case_three_conflicts_irrelevant_120,
    "hard_conflict_irrelevant_150": case_hard_conflict_irrelevant_150,
    "alldiff_dense_core_24": case_alldiff_dense_core_24,
    "alldiff_dense_core_36": case_alldiff_dense_core_36,
}

METHODS: Dict[str, MarcoMethod] = {
    "marco": cpmpy_marco,
    "marco_adaptive": marco_adaptive,
}


@dataclass
class RunRecord:
    case: str
    method: str
    run_id: int
    elapsed_s: float
    success: bool
    valid_mus: bool
    valid_mcs: bool
    mus_count: int
    mcs_count: int
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
    mus_count_median: Optional[float]
    mcs_count_median: Optional[float]


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


def _is_unsat(constraints: List[Constraint], hard: List[Constraint], solver: str) -> bool:
    return cp.Model(hard + list(constraints)).solve(solver=solver) is False


def _is_sat(constraints: List[Constraint], hard: List[Constraint], solver: str) -> bool:
    return cp.Model(hard + list(constraints)).solve(solver=solver) is True


def is_mus_candidate(mus: List[Constraint], hard: List[Constraint], solver: str) -> bool:
    if not _is_unsat(mus, hard, solver):
        return False
    for i in range(len(mus)):
        subset = mus[:i] + mus[i + 1 :]
        if _is_unsat(subset, hard, solver):
            return False
    return True


def is_mcs_candidate(
    mcs: List[Constraint],
    soft: List[Constraint],
    hard: List[Constraint],
    solver: str,
) -> bool:
    mcs_ids = {id(c) for c in mcs}
    kept = [c for c in soft if id(c) not in mcs_ids]

    if not _is_sat(kept, hard, solver):
        return False

    for c in mcs:
        if _is_sat(kept + [c], hard, solver):
            return False
    return True


def run_once(
    case_name: str,
    builder: CaseBuilder,
    method_name: str,
    method: MarcoMethod,
    solver: str,
    map_solver: str,
    validate: bool,
    run_id: int,
    do_solution_hint: bool,
    handoff_threshold: int,
    batch_base_ratio: int,
    sat_backoff_cap: int,
    feedback_enabled: bool,
    feedback_sat_clause_max: int,
    feedback_unsat_clause_max: int,
    feedback_max_clauses: int,
) -> RunRecord:
    soft, hard = builder()

    t0 = time.perf_counter()
    try:
        method_kwargs = {
            "hard": hard,
            "solver": solver,
            "map_solver": map_solver,
            "return_mus": True,
            "return_mcs": True,
            "do_solution_hint": do_solution_hint,
        }
        if method_name == "marco_adaptive":
            if handoff_threshold > 0:
                method_kwargs["handoff_threshold"] = handoff_threshold
            method_kwargs["batch_base_ratio"] = batch_base_ratio
            method_kwargs["sat_backoff_cap"] = sat_backoff_cap
            method_kwargs["feedback_enabled"] = feedback_enabled
            method_kwargs["feedback_sat_clause_max"] = feedback_sat_clause_max
            method_kwargs["feedback_unsat_clause_max"] = feedback_unsat_clause_max
            method_kwargs["feedback_max_clauses"] = feedback_max_clauses

        pairs = list(method(soft, **method_kwargs))
        elapsed = time.perf_counter() - t0

        muses = [subset for kind, subset in pairs if kind == "MUS"]
        mcses = [subset for kind, subset in pairs if kind == "MCS"]

        if validate:
            valid_mus = all(is_mus_candidate(mus, hard=hard, solver=solver) for mus in muses)
            valid_mcs = all(is_mcs_candidate(mcs, soft, hard=hard, solver=solver) for mcs in mcses)
        else:
            valid_mus = True
            valid_mcs = True

        return RunRecord(
            case=case_name,
            method=method_name,
            run_id=run_id,
            elapsed_s=elapsed,
            success=True,
            valid_mus=valid_mus,
            valid_mcs=valid_mcs,
            mus_count=len(muses),
            mcs_count=len(mcses),
            error="",
        )
    except Exception as exc:  # pragma: no cover
        elapsed = time.perf_counter() - t0
        return RunRecord(
            case=case_name,
            method=method_name,
            run_id=run_id,
            elapsed_s=elapsed,
            success=False,
            valid_mus=False,
            valid_mcs=False,
            mus_count=0,
            mcs_count=0,
            error=str(exc),
        )


def summarize(records: List[RunRecord]) -> List[SummaryRow]:
    rows: List[SummaryRow] = []
    grouped: Dict[Tuple[str, str], List[RunRecord]] = {}
    for rec in records:
        grouped.setdefault((rec.case, rec.method), []).append(rec)

    for (case_name, method_name), recs in sorted(grouped.items()):
        valid_recs = [r for r in recs if r.success and r.valid_mus and r.valid_mcs]
        valid_times = [r.elapsed_s for r in valid_recs]
        valid_mus_counts = [r.mus_count for r in valid_recs]
        valid_mcs_counts = [r.mcs_count for r in valid_recs]

        success_rate = sum(1 for r in recs if r.success) / len(recs)
        valid_rate = len(valid_recs) / len(recs)

        rows.append(
            SummaryRow(
                case=case_name,
                method=method_name,
                runs=len(recs),
                success_rate=success_rate,
                valid_rate=valid_rate,
                median_ms=(statistics.median(valid_times) * 1000.0) if valid_times else None,
                p90_ms=(percentile(valid_times, 0.90) * 1000.0) if valid_times else None,
                mus_count_median=statistics.median(valid_mus_counts) if valid_mus_counts else None,
                mcs_count_median=statistics.median(valid_mcs_counts) if valid_mcs_counts else None,
            )
        )
    return rows


def print_summary(rows: List[SummaryRow], baseline: str) -> None:
    by_case: Dict[str, List[SummaryRow]] = {}
    for row in rows:
        by_case.setdefault(row.case, []).append(row)

    for case_name in sorted(by_case):
        print(f"\nCase: {case_name}")
        print("method              median_ms   p90_ms   succ  valid  mus  mcs")
        for row in sorted(
            by_case[case_name],
            key=lambda r: (r.median_ms is None, r.median_ms if r.median_ms is not None else float("inf")),
        ):
            median_txt = f"{row.median_ms:9.3f}" if row.median_ms is not None else "      n/a"
            p90_txt = f"{row.p90_ms:7.3f}" if row.p90_ms is not None else "   n/a"
            mus_txt = f"{row.mus_count_median:.1f}" if row.mus_count_median is not None else "n/a"
            mcs_txt = f"{row.mcs_count_median:.1f}" if row.mcs_count_median is not None else "n/a"
            print(
                f"{row.method:18} {median_txt} {p90_txt} "
                f"{row.success_rate:5.2f} {row.valid_rate:5.2f} {mus_txt:>4} {mcs_txt:>4}"
            )

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
            print(f"  {method_name:16} x{gmean:.3f} ({len(ratios)} cases)")


def write_csv(path: Path, run_records: List[RunRecord], summary_rows: List[SummaryRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case",
                "method",
                "run_id",
                "elapsed_s",
                "success",
                "valid_mus",
                "valid_mcs",
                "mus_count",
                "mcs_count",
                "error",
            ]
        )
        for rec in run_records:
            writer.writerow(
                [
                    rec.case,
                    rec.method,
                    rec.run_id,
                    f"{rec.elapsed_s:.9f}",
                    rec.success,
                    rec.valid_mus,
                    rec.valid_mcs,
                    rec.mus_count,
                    rec.mcs_count,
                    rec.error,
                ]
            )

    summary_path = path.with_name(f"{path.stem}_summary{path.suffix or '.csv'}")
    with summary_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case",
                "method",
                "runs",
                "success_rate",
                "valid_rate",
                "median_ms",
                "p90_ms",
                "mus_count_median",
                "mcs_count_median",
            ]
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
                    "" if row.mus_count_median is None else f"{row.mus_count_median:.6f}",
                    "" if row.mcs_count_median is None else f"{row.mcs_count_median:.6f}",
                ]
            )

    print(f"\nWrote run CSV: {path}")
    print(f"Wrote summary CSV: {summary_path}")


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark CPMPy MARCO methods")
    parser.add_argument("--repeats", type=int, default=7, help="Measured runs per method/case")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per method/case")
    parser.add_argument("--solver", default="ortools", help="CPMPy SAT solver backend")
    parser.add_argument("--map-solver", default="ortools", help="CPMPy map solver backend")
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
        default="marco",
        help="Baseline method for speedup summary (default: marco)",
    )
    parser.add_argument(
        "--core-handoff",
        type=int,
        default=-1,
        help="Optional handoff threshold for marco_adaptive (<=0 means algorithm default)",
    )
    parser.add_argument(
        "--core-base-ratio",
        type=int,
        default=2,
        help="Batch base ratio for marco_adaptive",
    )
    parser.add_argument(
        "--core-backoff-cap",
        type=int,
        default=8,
        help="SAT backoff exponent cap for marco_adaptive",
    )
    parser.add_argument("--no-feedback", action="store_true", help="Disable dual-side feedback learning")
    parser.add_argument(
        "--feedback-sat-clause-max",
        type=int,
        default=12,
        help="Max learned SAT block clause length (complement size)",
    )
    parser.add_argument(
        "--feedback-unsat-clause-max",
        type=int,
        default=12,
        help="Max learned UNSAT block clause size (core size)",
    )
    parser.add_argument(
        "--feedback-max-clauses",
        type=int,
        default=2000,
        help="Max learned feedback clauses for marco_adaptive (<=0 means unbounded)",
    )
    parser.add_argument("--no-solution-hint", action="store_true", help="Disable map-solver solution hints")
    parser.add_argument("--skip-validate", action="store_true", help="Skip MUS/MCS validity checks")
    parser.add_argument("--output-csv", default="", help="Write run-level CSV to this path")
    parser.add_argument("--verbose", action="store_true", help="Print per-run benchmark progress")
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
    do_solution_hint = not args.no_solution_hint
    feedback_enabled = not args.no_feedback

    print("Benchmark configuration:")
    print(f"  solver    : {args.solver}")
    print(f"  map-solver: {args.map_solver}")
    print(f"  methods   : {', '.join(selected_methods)}")
    print(f"  cases     : {', '.join(selected_cases)}")
    print(f"  warmup    : {args.warmup}")
    print(f"  repeats   : {args.repeats}")
    print(f"  core-hnd  : {args.core_handoff}")
    print(f"  core-rat  : {args.core_base_ratio}")
    print(f"  core-cap  : {args.core_backoff_cap}")
    print(f"  fb-enable : {feedback_enabled}")
    print(f"  fb-satmax : {args.feedback_sat_clause_max}")
    print(f"  fb-unmax  : {args.feedback_unsat_clause_max}")
    print(f"  fb-maxcls : {args.feedback_max_clauses}")
    print(f"  hint      : {do_solution_hint}")
    print(f"  validate  : {validate}")
    print(f"  verbose   : {args.verbose}")

    for case_name in selected_cases:
        builder = CASES[case_name]
        for method_name in selected_methods:
            method = METHODS[method_name]

            if args.verbose:
                print(f"\n[bench] case={case_name} method={method_name} warmup={args.warmup} repeats={args.repeats}")

            for w in range(max(0, args.warmup)):
                _ = run_once(
                    case_name=case_name,
                    builder=builder,
                    method_name=method_name,
                    method=method,
                    solver=args.solver,
                    map_solver=args.map_solver,
                    validate=False,
                    run_id=-1,
                    do_solution_hint=do_solution_hint,
                    handoff_threshold=args.core_handoff,
                    batch_base_ratio=args.core_base_ratio,
                    sat_backoff_cap=args.core_backoff_cap,
                    feedback_enabled=feedback_enabled,
                    feedback_sat_clause_max=args.feedback_sat_clause_max,
                    feedback_unsat_clause_max=args.feedback_unsat_clause_max,
                    feedback_max_clauses=args.feedback_max_clauses,
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
                    map_solver=args.map_solver,
                    validate=validate,
                    run_id=run_id,
                    do_solution_hint=do_solution_hint,
                    handoff_threshold=args.core_handoff,
                    batch_base_ratio=args.core_base_ratio,
                    sat_backoff_cap=args.core_backoff_cap,
                    feedback_enabled=feedback_enabled,
                    feedback_sat_clause_max=args.feedback_sat_clause_max,
                    feedback_unsat_clause_max=args.feedback_unsat_clause_max,
                    feedback_max_clauses=args.feedback_max_clauses,
                )
                run_records.append(rec)
                if args.verbose:
                    status = "ok" if rec.success and rec.valid_mus and rec.valid_mcs else "fail"
                    print(
                        f"  [run {run_id + 1}/{args.repeats}] {status} "
                        f"time={rec.elapsed_s * 1000.0:.3f}ms mus={rec.mus_count} mcs={rec.mcs_count}"
                    )
                    if rec.error:
                        print(f"    error: {rec.error}")

    summary_rows = summarize(run_records)
    print_summary(summary_rows, baseline=args.baseline)

    if args.output_csv:
        write_csv(Path(args.output_csv), run_records, summary_rows)


if __name__ == "__main__":
    main()
