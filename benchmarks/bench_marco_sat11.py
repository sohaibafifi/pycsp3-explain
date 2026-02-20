#!/usr/bin/env python3
"""
Benchmark MARCO variants on SAT11 MUS-track CNF instances (.cnf.bz2).

This script is separate from synthetic-case benchmarks and is designed for the
SAT11 dataset under:
    benchmarks/SAT11-Competition-MUS-SelectedBenchmarks

It supports:
- size-based instance filtering (vars/clauses),
- optional random sub-sampling,
- per-run timeout isolation via subprocesses,
- partial enumeration metrics (MUS/MCS produced before timeout),
- optional MUS/MCS validation (expensive on large instances).
"""

from __future__ import annotations

import argparse
import bz2
import csv
import math
import multiprocessing as mp
import queue
import random
import re
import statistics
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import cpmpy as cp
except ImportError:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "libs" / "cpmpy"))
    import cpmpy as cp

from cpmpy.tools.explain.marco import marco as cpmpy_marco

if __package__:
    from .cpmpy_marco_core import marco_core
else:
    from cpmpy_marco_core import marco_core


P_HEADER = re.compile(r"^p\s+cnf\s+(\d+)\s+(\d+)\s*$")


@dataclass
class InstanceMeta:
    path: str
    relpath: str
    nvars: int
    nclauses: int
    compressed_bytes: int


@dataclass
class RunRecord:
    instance: str
    method: str
    run_id: int
    elapsed_s: float
    success: bool
    timed_out: bool
    completed: bool
    valid_mus: bool
    valid_mcs: bool
    outputs_count: int
    mus_count: int
    mcs_count: int
    first_output_s: Optional[float]
    first_mus_s: Optional[float]
    first_mcs_s: Optional[float]
    error: str


@dataclass
class MethodSummary:
    method: str
    runs: int
    completed_rate: float
    timeout_rate: float
    valid_rate: float
    median_ms: Optional[float]
    p90_ms: Optional[float]
    median_outputs: Optional[float]
    median_mus: Optional[float]
    median_mcs: Optional[float]
    median_first_mus_ms: Optional[float]


def percentile(values: Sequence[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return ordered[idx]


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def read_dimacs_header(path: Path) -> Tuple[Optional[int], Optional[int]]:
    with bz2.open(path, "rt", encoding="ascii", errors="ignore") as f:
        for line in f:
            m = P_HEADER.match(line.strip())
            if m:
                return int(m.group(1)), int(m.group(2))
    return None, None


def scan_instances(root: Path) -> List[InstanceMeta]:
    metas: List[InstanceMeta] = []
    for path in sorted(root.rglob("*.cnf.bz2")):
        nvars, nclauses = read_dimacs_header(path)
        if nvars is None or nclauses is None:
            continue
        metas.append(
            InstanceMeta(
                path=str(path),
                relpath=str(path.relative_to(root)),
                nvars=nvars,
                nclauses=nclauses,
                compressed_bytes=path.stat().st_size,
            )
        )
    return metas


def select_instances(
    all_instances: List[InstanceMeta],
    include_patterns: List[str],
    max_vars: int,
    max_clauses: int,
    max_files: int,
    shuffle: bool,
    seed: int,
) -> List[InstanceMeta]:
    selected = list(all_instances)

    if include_patterns:
        pats = [p.lower() for p in include_patterns]
        selected = [
            m
            for m in selected
            if any(p in m.relpath.lower() or p in Path(m.relpath).name.lower() for p in pats)
        ]

    if max_vars > 0:
        selected = [m for m in selected if m.nvars <= max_vars]
    if max_clauses > 0:
        selected = [m for m in selected if m.nclauses <= max_clauses]

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(selected)
    else:
        selected.sort(key=lambda m: (m.nclauses, m.nvars, m.relpath))

    if max_files > 0:
        selected = selected[:max_files]

    return selected


def read_dimacs_constraints(path: str) -> Tuple[List, int, int]:
    """
    Read .cnf.bz2 DIMACS as a list of CPMPy clause constraints.
    """
    clauses_ints: List[List[int]] = []
    nvars_header: Optional[int] = None
    nclauses_header: Optional[int] = None
    cur_clause: List[int] = []

    with bz2.open(path, "rt", encoding="ascii", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                m = P_HEADER.match(line)
                if not m:
                    raise ValueError(f"Invalid DIMACS header in {path}: {line}")
                nvars_header = int(m.group(1))
                nclauses_header = int(m.group(2))
                continue

            for tok in line.split():
                lit = int(tok)
                if lit == 0:
                    clauses_ints.append(cur_clause)
                    cur_clause = []
                else:
                    cur_clause.append(lit)

    if cur_clause:
        raise ValueError(f"Last clause not terminated by 0 in {path}")

    max_var = 0
    for cl in clauses_ints:
        for lit in cl:
            max_var = max(max_var, abs(lit))

    nvars = nvars_header if nvars_header is not None else max_var
    if nvars < max_var:
        raise ValueError(f"Header vars too small in {path}: header={nvars}, seen={max_var}")

    bvs = cp.boolvar(shape=nvars, name="x")
    soft: List = []

    for clause in clauses_ints:
        if not clause:
            # Empty clause is equivalent to False.
            z = cp.boolvar(name="empty_clause_false")
            soft.append(cp.all([z, ~z]))
            continue
        lits = []
        for lit in clause:
            idx = abs(lit) - 1
            if idx < 0 or idx >= nvars:
                raise ValueError(f"Literal index out of range in {path}: {lit}")
            v = bvs[idx]
            lits.append(v if lit > 0 else ~v)
        soft.append(cp.any(lits))

    if nclauses_header is not None and len(soft) != nclauses_header:
        raise ValueError(
            f"Header clause count mismatch in {path}: header={nclauses_header}, parsed={len(soft)}"
        )

    return soft, nvars, len(soft)


def _is_unsat(constraints: List, hard: List, solver: str) -> bool:
    return cp.Model(hard + list(constraints)).solve(solver=solver) is False


def _is_sat(constraints: List, hard: List, solver: str) -> bool:
    return cp.Model(hard + list(constraints)).solve(solver=solver) is True


def is_mus_candidate(mus: List, hard: List, solver: str) -> bool:
    if not _is_unsat(mus, hard, solver):
        return False
    for i in range(len(mus)):
        subset = mus[:i] + mus[i + 1 :]
        if _is_unsat(subset, hard, solver):
            return False
    return True


def is_mcs_candidate(mcs: List, soft: List, hard: List, solver: str) -> bool:
    mcs_ids = {id(c) for c in mcs}
    kept = [c for c in soft if id(c) not in mcs_ids]
    if not _is_sat(kept, hard, solver):
        return False
    for c in mcs:
        if _is_sat(kept + [c], hard, solver):
            return False
    return True


def worker_enumerate(payload: Dict, out_q: mp.Queue) -> None:
    """
    Worker process for one (instance, method, run).
    """
    t0 = time.perf_counter()
    try:
        soft, _, _ = read_dimacs_constraints(payload["instance_path"])
        hard: List = []

        solver = payload["solver"]
        map_solver = payload["map_solver"]
        method_name = payload["method_name"]
        validate = payload["validate"]
        verify_unsat = payload["verify_unsat"]
        max_outputs = payload["max_outputs"]
        do_solution_hint = payload["do_solution_hint"]

        if verify_unsat and cp.Model(hard + soft).solve(solver=solver) is not False:
            out_q.put(
                {
                    "type": "done",
                    "status": "error",
                    "elapsed_s": time.perf_counter() - t0,
                    "error": "instance is not UNSAT under the selected solver",
                }
            )
            return

        if method_name == "marco":
            method = cpmpy_marco
            kwargs = {
                "hard": hard,
                "solver": solver,
                "map_solver": map_solver,
                "return_mus": True,
                "return_mcs": True,
                "do_solution_hint": do_solution_hint,
            }
        elif method_name == "marco_core":
            method = marco_core
            kwargs = {
                "hard": hard,
                "solver": solver,
                "map_solver": map_solver,
                "return_mus": True,
                "return_mcs": True,
                "do_solution_hint": do_solution_hint,
                "handoff_threshold": payload["core_handoff"]
                if payload["core_handoff"] > 0
                else None,
                "batch_base_ratio": payload["core_base_ratio"],
                "sat_backoff_cap": payload["core_backoff_cap"],
                "feedback_enabled": payload["feedback_enabled"],
                "feedback_sat_clause_max": payload["feedback_sat_clause_max"],
                "feedback_unsat_clause_max": payload["feedback_unsat_clause_max"],
                "feedback_max_clauses": payload["feedback_max_clauses"],
            }
        else:
            raise ValueError(f"unknown method: {method_name}")

        outputs = 0
        mus_count = 0
        mcs_count = 0
        first_output_s: Optional[float] = None
        first_mus_s: Optional[float] = None
        first_mcs_s: Optional[float] = None
        valid_mus = True
        valid_mcs = True
        stopped_by_cap = False

        for kind, subset in method(soft, **kwargs):
            now = time.perf_counter() - t0
            outputs += 1
            if first_output_s is None:
                first_output_s = now
            if kind == "MUS":
                mus_count += 1
                if first_mus_s is None:
                    first_mus_s = now
                if validate:
                    valid_mus = valid_mus and is_mus_candidate(subset, hard=hard, solver=solver)
            elif kind == "MCS":
                mcs_count += 1
                if first_mcs_s is None:
                    first_mcs_s = now
                if validate:
                    valid_mcs = valid_mcs and is_mcs_candidate(subset, soft=soft, hard=hard, solver=solver)

            if outputs == 1 or outputs % 10 == 0:
                out_q.put(
                    {
                        "type": "progress",
                        "outputs_count": outputs,
                        "mus_count": mus_count,
                        "mcs_count": mcs_count,
                        "first_output_s": first_output_s,
                        "first_mus_s": first_mus_s,
                        "first_mcs_s": first_mcs_s,
                        "valid_mus": valid_mus,
                        "valid_mcs": valid_mcs,
                    }
                )

            if max_outputs > 0 and outputs >= max_outputs:
                stopped_by_cap = True
                break

        out_q.put(
            {
                "type": "done",
                "status": "ok",
                "elapsed_s": time.perf_counter() - t0,
                "completed": not stopped_by_cap,
                "outputs_count": outputs,
                "mus_count": mus_count,
                "mcs_count": mcs_count,
                "first_output_s": first_output_s,
                "first_mus_s": first_mus_s,
                "first_mcs_s": first_mcs_s,
                "valid_mus": valid_mus,
                "valid_mcs": valid_mcs,
                "error": "",
            }
        )
    except Exception as exc:  # pragma: no cover
        out_q.put(
            {
                "type": "done",
                "status": "error",
                "elapsed_s": time.perf_counter() - t0,
                "error": f"{exc}\n{traceback.format_exc()}",
            }
        )


def run_with_timeout(payload: Dict, timeout_s: float) -> Dict:
    ctx = mp.get_context("spawn")
    out_q: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=worker_enumerate, args=(payload, out_q))

    progress = {
        "outputs_count": 0,
        "mus_count": 0,
        "mcs_count": 0,
        "first_output_s": None,
        "first_mus_s": None,
        "first_mcs_s": None,
        "valid_mus": True,
        "valid_mcs": True,
    }
    done_msg: Optional[Dict] = None
    timed_out = False

    start = time.perf_counter()
    proc.start()
    try:
        while True:
            now = time.perf_counter()
            if timeout_s > 0 and (now - start) > timeout_s:
                timed_out = True
                break

            try:
                msg = out_q.get(timeout=0.20)
            except queue.Empty:
                if not proc.is_alive():
                    break
                continue

            if msg.get("type") == "progress":
                progress.update(msg)
            elif msg.get("type") == "done":
                done_msg = msg
                break

        if timed_out and proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1.0)

        # Drain remaining queue items.
        while True:
            try:
                msg = out_q.get_nowait()
            except queue.Empty:
                break
            if msg.get("type") == "progress":
                progress.update(msg)
            elif msg.get("type") == "done":
                done_msg = msg
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=1.0)

    elapsed = time.perf_counter() - start

    if timed_out:
        return {
            "success": False,
            "timed_out": True,
            "completed": False,
            "elapsed_s": elapsed,
            "error": "timeout",
            **progress,
        }

    if done_msg is None:
        return {
            "success": False,
            "timed_out": False,
            "completed": False,
            "elapsed_s": elapsed,
            "error": "worker exited without completion message",
            **progress,
        }

    if done_msg.get("status") != "ok":
        return {
            "success": False,
            "timed_out": False,
            "completed": False,
            "elapsed_s": done_msg.get("elapsed_s", elapsed),
            "error": done_msg.get("error", "worker error"),
            **progress,
        }

    return {
        "success": True,
        "timed_out": False,
        "completed": bool(done_msg.get("completed", True)),
        "elapsed_s": done_msg.get("elapsed_s", elapsed),
        "error": "",
        "outputs_count": int(done_msg.get("outputs_count", progress["outputs_count"])),
        "mus_count": int(done_msg.get("mus_count", progress["mus_count"])),
        "mcs_count": int(done_msg.get("mcs_count", progress["mcs_count"])),
        "first_output_s": done_msg.get("first_output_s", progress["first_output_s"]),
        "first_mus_s": done_msg.get("first_mus_s", progress["first_mus_s"]),
        "first_mcs_s": done_msg.get("first_mcs_s", progress["first_mcs_s"]),
        "valid_mus": bool(done_msg.get("valid_mus", progress["valid_mus"])),
        "valid_mcs": bool(done_msg.get("valid_mcs", progress["valid_mcs"])),
    }


def summarize(records: List[RunRecord]) -> List[MethodSummary]:
    out: List[MethodSummary] = []
    by_method: Dict[str, List[RunRecord]] = {}
    for rec in records:
        by_method.setdefault(rec.method, []).append(rec)

    for method, rows in sorted(by_method.items()):
        completed_rows = [r for r in rows if r.success and r.completed]
        valid_rows = [r for r in rows if r.success and r.valid_mus and r.valid_mcs]

        elapsed_vals = [r.elapsed_s for r in completed_rows]
        output_vals = [r.outputs_count for r in rows if r.success]
        mus_vals = [r.mus_count for r in rows if r.success]
        mcs_vals = [r.mcs_count for r in rows if r.success]
        first_mus_vals = [r.first_mus_s for r in rows if r.success and r.first_mus_s is not None]

        out.append(
            MethodSummary(
                method=method,
                runs=len(rows),
                completed_rate=(len(completed_rows) / len(rows)) if rows else 0.0,
                timeout_rate=(sum(1 for r in rows if r.timed_out) / len(rows)) if rows else 0.0,
                valid_rate=(len(valid_rows) / len(rows)) if rows else 0.0,
                median_ms=(statistics.median(elapsed_vals) * 1000.0) if elapsed_vals else None,
                p90_ms=(percentile(elapsed_vals, 0.90) * 1000.0) if elapsed_vals else None,
                median_outputs=statistics.median(output_vals) if output_vals else None,
                median_mus=statistics.median(mus_vals) if mus_vals else None,
                median_mcs=statistics.median(mcs_vals) if mcs_vals else None,
                median_first_mus_ms=(statistics.median(first_mus_vals) * 1000.0) if first_mus_vals else None,
            )
        )
    return out


def print_method_summary(rows: List[MethodSummary], baseline: str) -> None:
    print("\nMethod summary")
    print("method            done  timeout valid median_ms   p90_ms  med_out med_mus med_mcs first_mus_ms")
    for row in rows:
        median_txt = f"{row.median_ms:9.3f}" if row.median_ms is not None else "      n/a"
        p90_txt = f"{row.p90_ms:8.3f}" if row.p90_ms is not None else "    n/a"
        out_txt = f"{row.median_outputs:.1f}" if row.median_outputs is not None else "n/a"
        mus_txt = f"{row.median_mus:.1f}" if row.median_mus is not None else "n/a"
        mcs_txt = f"{row.median_mcs:.1f}" if row.median_mcs is not None else "n/a"
        fm_txt = f"{row.median_first_mus_ms:.1f}" if row.median_first_mus_ms is not None else "n/a"
        print(
            f"{row.method:16} {row.completed_rate:5.2f} {row.timeout_rate:7.2f} {row.valid_rate:5.2f} "
            f"{median_txt} {p90_txt} {out_txt:>7} {mus_txt:>7} {mcs_txt:>7} {fm_txt:>12}"
        )

    lookup = {r.method: r for r in rows}
    if baseline in lookup:
        base = lookup[baseline]
        print(f"\nSpeedup vs baseline '{baseline}' (median completed runtime):")
        for row in rows:
            if row.method == baseline:
                continue
            if base.median_ms is None or row.median_ms is None or row.median_ms <= 0:
                print(f"  {row.method:16} n/a")
                continue
            print(f"  {row.method:16} x{base.median_ms / row.median_ms:.3f}")


def write_csv(path: Path, runs: List[RunRecord], summary_rows: List[MethodSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "instance",
                "method",
                "run_id",
                "elapsed_s",
                "success",
                "timed_out",
                "completed",
                "valid_mus",
                "valid_mcs",
                "outputs_count",
                "mus_count",
                "mcs_count",
                "first_output_s",
                "first_mus_s",
                "first_mcs_s",
                "error",
            ]
        )
        for r in runs:
            w.writerow(
                [
                    r.instance,
                    r.method,
                    r.run_id,
                    f"{r.elapsed_s:.9f}",
                    r.success,
                    r.timed_out,
                    r.completed,
                    r.valid_mus,
                    r.valid_mcs,
                    r.outputs_count,
                    r.mus_count,
                    r.mcs_count,
                    "" if r.first_output_s is None else f"{r.first_output_s:.9f}",
                    "" if r.first_mus_s is None else f"{r.first_mus_s:.9f}",
                    "" if r.first_mcs_s is None else f"{r.first_mcs_s:.9f}",
                    r.error,
                ]
            )

    summary_path = path.with_name(f"{path.stem}_summary{path.suffix or '.csv'}")
    with summary_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "method",
                "runs",
                "completed_rate",
                "timeout_rate",
                "valid_rate",
                "median_ms",
                "p90_ms",
                "median_outputs",
                "median_mus",
                "median_mcs",
                "median_first_mus_ms",
            ]
        )
        for s in summary_rows:
            w.writerow(
                [
                    s.method,
                    s.runs,
                    f"{s.completed_rate:.6f}",
                    f"{s.timeout_rate:.6f}",
                    f"{s.valid_rate:.6f}",
                    "" if s.median_ms is None else f"{s.median_ms:.6f}",
                    "" if s.p90_ms is None else f"{s.p90_ms:.6f}",
                    "" if s.median_outputs is None else f"{s.median_outputs:.6f}",
                    "" if s.median_mus is None else f"{s.median_mus:.6f}",
                    "" if s.median_mcs is None else f"{s.median_mcs:.6f}",
                    "" if s.median_first_mus_ms is None else f"{s.median_first_mus_ms:.6f}",
                ]
            )

    print(f"\nWrote run CSV: {path}")
    print(f"Wrote summary CSV: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark MARCO methods on SAT11 CNF (.bz2)")
    parser.add_argument(
        "--dataset-root",
        default="benchmarks/SAT11-Competition-MUS-SelectedBenchmarks",
        help="Root folder containing SAT11 .cnf.bz2 files",
    )
    parser.add_argument(
        "--methods",
        default="marco,marco_core",
        help="Comma-separated methods: marco,marco_core",
    )
    parser.add_argument(
        "--instances",
        default="",
        help="Optional comma-separated filename/path substrings to include",
    )
    parser.add_argument("--max-vars", type=int, default=10000, help="Keep instances with vars <= this (<=0 disables)")
    parser.add_argument(
        "--max-clauses",
        type=int,
        default=100000,
        help="Keep instances with clauses <= this (<=0 disables)",
    )
    parser.add_argument("--max-files", type=int, default=40, help="Max selected instances (<=0 means all)")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle selected instances before truncating")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for --shuffle")

    parser.add_argument("--solver", default="ortools", help="CPMPy solver backend")
    parser.add_argument("--map-solver", default="ortools", help="CPMPy map solver backend")
    parser.add_argument("--repeats", type=int, default=1, help="Measured runs per method/instance")
    parser.add_argument("--warmup", type=int, default=0, help="Warmup runs per method/instance")
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=1200.0,
        help="Timeout in seconds per run (<=0 disables timeout)",
    )
    parser.add_argument(
        "--max-outputs",
        type=int,
        default=0,
        help="Cap outputs per run for partial enumeration (<=0 means unbounded)",
    )
    parser.add_argument("--verify-unsat", action="store_true", help="Check each instance is UNSAT before enumeration")
    parser.add_argument("--validate", action="store_true", help="Validate each produced MUS/MCS (expensive)")

    parser.add_argument("--no-solution-hint", action="store_true", help="Disable map solver solution hints")
    parser.add_argument("--core-handoff", type=int, default=-1, help="marco_core handoff threshold")
    parser.add_argument("--core-base-ratio", type=int, default=2, help="marco_core batch base ratio")
    parser.add_argument("--core-backoff-cap", type=int, default=8, help="marco_core SAT backoff cap")
    parser.add_argument("--no-feedback", action="store_true", help="Disable feedback in marco_core")
    parser.add_argument("--feedback-sat-clause-max", type=int, default=12, help="Feedback SAT clause max length")
    parser.add_argument("--feedback-unsat-clause-max", type=int, default=12, help="Feedback UNSAT clause max size")
    parser.add_argument("--feedback-max-clauses", type=int, default=2000, help="Max learned feedback clauses")

    parser.add_argument("--baseline", default="marco", help="Baseline method for speedup reporting")
    parser.add_argument("--output-csv", default="", help="Write run-level CSV to this path")
    parser.add_argument("--verbose", action="store_true", help="Print per-run progress")
    args = parser.parse_args()

    methods = parse_csv_list(args.methods)
    allowed = {"marco", "marco_core"}
    for m in methods:
        if m not in allowed:
            raise ValueError(f"Unknown method '{m}'. Allowed: {', '.join(sorted(allowed))}")
    if args.baseline not in methods:
        raise ValueError("Baseline must be included in --methods")

    root = Path(args.dataset_root)
    if not root.exists():
        raise FileNotFoundError(f"Dataset root not found: {root}")

    patterns = parse_csv_list(args.instances)
    all_instances = scan_instances(root)
    selected = select_instances(
        all_instances=all_instances,
        include_patterns=patterns,
        max_vars=args.max_vars,
        max_clauses=args.max_clauses,
        max_files=args.max_files,
        shuffle=args.shuffle,
        seed=args.seed,
    )

    if not selected:
        raise ValueError("No instances selected after filtering")

    print("SAT11 benchmark configuration:")
    print(f"  dataset       : {root}")
    print(f"  found files   : {len(all_instances)}")
    print(f"  selected      : {len(selected)}")
    print(f"  methods       : {', '.join(methods)}")
    print(f"  solver/map    : {args.solver}/{args.map_solver}")
    print(f"  repeats/warmup: {args.repeats}/{args.warmup}")
    print(f"  timeout_s     : {args.timeout_s}")
    print(f"  max_outputs   : {args.max_outputs}")
    print(f"  verify_unsat  : {args.verify_unsat}")
    print(f"  validate      : {args.validate}")
    print(f"  solution_hint : {not args.no_solution_hint}")
    print(f"  feedback      : {not args.no_feedback}")

    run_records: List[RunRecord] = []
    total_jobs = len(selected) * len(methods) * (args.warmup + args.repeats)
    done_jobs = 0

    for inst_idx, meta in enumerate(selected, start=1):
        if args.verbose:
            print(
                f"\n[instance {inst_idx}/{len(selected)}] {meta.relpath} "
                f"(vars={meta.nvars}, clauses={meta.nclauses}, bz2={meta.compressed_bytes})"
            )

        for method in methods:
            # Warmups
            for w in range(max(0, args.warmup)):
                payload = {
                    "instance_path": meta.path,
                    "method_name": method,
                    "solver": args.solver,
                    "map_solver": args.map_solver,
                    "validate": False,
                    "verify_unsat": False,
                    "max_outputs": args.max_outputs,
                    "do_solution_hint": not args.no_solution_hint,
                    "core_handoff": args.core_handoff,
                    "core_base_ratio": args.core_base_ratio,
                    "core_backoff_cap": args.core_backoff_cap,
                    "feedback_enabled": not args.no_feedback,
                    "feedback_sat_clause_max": args.feedback_sat_clause_max,
                    "feedback_unsat_clause_max": args.feedback_unsat_clause_max,
                    "feedback_max_clauses": args.feedback_max_clauses,
                }
                _ = run_with_timeout(payload, timeout_s=max(0.0, args.timeout_s))
                done_jobs += 1
                if args.verbose:
                    print(f"  [warmup {w + 1}/{args.warmup}] {method} done ({done_jobs}/{total_jobs})")

            for run_id in range(args.repeats):
                payload = {
                    "instance_path": meta.path,
                    "method_name": method,
                    "solver": args.solver,
                    "map_solver": args.map_solver,
                    "validate": args.validate,
                    "verify_unsat": args.verify_unsat,
                    "max_outputs": args.max_outputs,
                    "do_solution_hint": not args.no_solution_hint,
                    "core_handoff": args.core_handoff,
                    "core_base_ratio": args.core_base_ratio,
                    "core_backoff_cap": args.core_backoff_cap,
                    "feedback_enabled": not args.no_feedback,
                    "feedback_sat_clause_max": args.feedback_sat_clause_max,
                    "feedback_unsat_clause_max": args.feedback_unsat_clause_max,
                    "feedback_max_clauses": args.feedback_max_clauses,
                }
                res = run_with_timeout(payload, timeout_s=max(0.0, args.timeout_s))
                done_jobs += 1

                rec = RunRecord(
                    instance=meta.relpath,
                    method=method,
                    run_id=run_id,
                    elapsed_s=float(res["elapsed_s"]),
                    success=bool(res["success"]),
                    timed_out=bool(res["timed_out"]),
                    completed=bool(res["completed"]),
                    valid_mus=bool(res.get("valid_mus", False)),
                    valid_mcs=bool(res.get("valid_mcs", False)),
                    outputs_count=int(res.get("outputs_count", 0)),
                    mus_count=int(res.get("mus_count", 0)),
                    mcs_count=int(res.get("mcs_count", 0)),
                    first_output_s=res.get("first_output_s"),
                    first_mus_s=res.get("first_mus_s"),
                    first_mcs_s=res.get("first_mcs_s"),
                    error=str(res.get("error", "")),
                )
                run_records.append(rec)

                if args.verbose:
                    status = "ok" if rec.success else ("timeout" if rec.timed_out else "fail")
                    print(
                        f"  [run {run_id + 1}/{args.repeats}] {method} {status} "
                        f"time={rec.elapsed_s:.3f}s out={rec.outputs_count} mus={rec.mus_count} mcs={rec.mcs_count} "
                        f"({done_jobs}/{total_jobs})"
                    )
                    if rec.error and rec.error != "timeout":
                        print(f"    error: {rec.error.splitlines()[0]}")

    summary_rows = summarize(run_records)
    print_method_summary(summary_rows, baseline=args.baseline)

    if args.output_csv:
        write_csv(Path(args.output_csv), run_records, summary_rows)


if __name__ == "__main__":
    main()
