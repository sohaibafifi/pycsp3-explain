#!/usr/bin/env python3
"""
Build an array parameter file from a SAT11 instance manifest.

Input manifest format (TSV, from build_manifest.py):
    <relative_path>\t<nvars>\t<nclauses>\t<compressed_bytes>

Output array params format (TSV, no header):
    <relative_path>\t<method>\t<repeat_id>
Optional extended format:
    <relative_path>\t<method>\t<repeat_id>\t<solver>\t<map_solver>
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List


def parse_csv_list(raw: str) -> List[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build array params TSV for cluster execution")
    parser.add_argument(
        "--manifest",
        default="benchmarks/marco/sat11_manifest.tsv",
        help="Input manifest TSV (from build_manifest.py)",
    )
    parser.add_argument(
        "--methods",
        default="marco,marco_adaptive",
        help="Comma-separated methods",
    )
    parser.add_argument("--repeats", type=int, default=1, help="Number of repeats per instance/method")
    parser.add_argument(
        "--solver",
        default="",
        help="Optional solver column written to array params (per-task override)",
    )
    parser.add_argument(
        "--map-solver",
        default="",
        help="Optional map solver column written to array params (defaults to --solver when omitted)",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/marco/array_params.tsv",
        help="Output array params TSV",
    )
    args = parser.parse_args()

    manifest = Path(args.manifest)
    if not manifest.exists():
        raise FileNotFoundError(f"manifest not found: {manifest}")
    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")

    methods = parse_csv_list(args.methods)
    if not methods:
        raise ValueError("No methods specified")
    allowed = {"marco", "marco_adaptive"}
    unknown = [m for m in methods if m not in allowed]
    if unknown:
        raise ValueError(f"Unknown methods: {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})")

    instances: List[str] = []
    with manifest.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cols = line.split("\t")
            if not cols or not cols[0]:
                continue
            instances.append(cols[0])

    if not instances:
        raise ValueError(f"No instance rows found in {manifest}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    solver_col = args.solver.strip()
    map_solver_col = args.map_solver.strip() or solver_col
    write_solver_cols = bool(solver_col or map_solver_col)
    nrows = 0
    with out.open("w", encoding="utf-8") as f:
        for rep in range(args.repeats):
            for method in methods:
                for inst in instances:
                    if write_solver_cols:
                        f.write(f"{inst}\t{method}\t{rep}\t{solver_col}\t{map_solver_col}\n")
                    else:
                        f.write(f"{inst}\t{method}\t{rep}\n")
                    nrows += 1

    print("Array params written")
    print(f"  manifest : {manifest}")
    print(f"  methods  : {', '.join(methods)}")
    print(f"  repeats  : {args.repeats}")
    if write_solver_cols:
        print(f"  solver   : {solver_col or '(from env/default)'}")
        print(f"  map-solver: {map_solver_col or '(from env/default)'}")
    print(f"  instances: {len(instances)}")
    print(f"  rows     : {nrows}")
    print(f"  output   : {out}")


if __name__ == "__main__":
    main()
