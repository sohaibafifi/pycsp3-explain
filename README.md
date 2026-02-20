# PyCSP3-Explain

Explanation tools for PyCSP3 constraint models. Find minimal unsatisfiable subsets (MUS), maximal satisfiable subsets (MSS), and minimal correction sets (MCS) to debug and understand infeasible constraint problems.

Algorithmic descriptions are documented in [ALGORITHMS.md](ALGORITHMS.md).

## Features

- **MUS (Minimal Unsatisfiable Subset)**: Find the minimal set of conflicting constraints
  - `mus()` - Assumption-based using ACE core extraction
  - `mus_naive()` - Deletion-based (works with any solver)
  - `mus_bicore()` - Core-guided batched exact MUS shrinking
  - `mus_cpqx()` - Core-Projected QuickXplain (exact hybrid)
  - `mus_bicore_qx()` - Hybrid BiCore bulk elimination + QuickXplain (exact)
  - `quickxplain()` - Preferred MUS using QuickXplain (Junker, 2004)
- **Optimal MUS (SMUS/OCUS)**: Prefer smaller or lower-weight explanations
  - `smus()` - Smallest MUS (fewest constraints)
  - `optimal_mus()` - Minimum total weight MUS
  - `optimal_mus_naive()` - Deprecated exhaustive minimum-weight MUS 
  - `ocus()` - OCUS with subset constraints/predicates
  - `ocus_naive()` - Deprecated exhaustive OCUS with subset constraints/predicates
  > Note: IHS uses a small CP model in PyCSP3 and falls back to enumeration if needed.
- **MSS (Maximal Satisfiable Subset)**: Find the maximum satisfiable portion
  - `mss()` - Assumption-based with core extraction
  - `mss_naive()` - Greedy growing algorithm
- **Weighted MSS/MCS**: Optimize which constraints to keep/remove
  - `mss_opt()` - Exact weighted MSS (Maximize total weight of kept constraints)
  - `mcs_opt()` - Exact weighted MCS (Minimize total weight of removed constraints)
  - `mss_heuristic()` - Greedy weighted MSS approximation
  - `mcs_heuristic()` - Greedy weighted MCS approximation
- **MCS (Minimal Correction Set)**: Find the minimal changes needed to restore satisfiability
  - `mcs()` - Via assumption-based MSS complement
  - `mcs_naive()` - Via naive MSS complement
- **MARCO**: Enumerate all MUSes and MCSes
  - `marco()` - Generator over MUS/MCS
  - `marco_core()` - Core-informed MARCO (core intersection + BiCore/QX shrink)
  - `marco_naive()` - Naive MARCO implementation
  - `all_mus()` / `all_mcs()` - Convenience wrappers
  - `all_mus_core()` / `all_mcs_core()` - `marco_core()` convenience wrappers
  - `all_mus_naive()` - Naive MUS enumeration

## Installation

```bash
# Clone the repository
git clone https://github.com/sohaibafifi/pycsp3-explain.git
cd pycsp3-explain

# Install dependencies
pip install -e .
```

## Requirements

- Python 3.10+
- PyCSP3 (>= 2.5)
- lxml (>= 4.9)
- Java runtime (for ACE/Choco)

## Quick Start

### Using satisfy() with Explain Tools

```python
from pycsp3 import *
from pycsp3_explain import *


x = VarArray(size=2, dom=range(10))

satisfy( [
    x[0] == 5,
    x[0] == 7,  # conflicts with x[0] == 5
    x[1] >= 3,
])

constraints  = flatten_constraints(posted())
if solve() == UNSAT:
    print("MUS:", mus(constraints))
    print("Optimal MUS:", optimal_mus(constraints, weights=[1, 1, 1]))
    for kind, subset in marco(constraints):
        print(kind, subset)

    # or use the helper function
    mus_result = explain_unsat("mus", soft=constraints, check=False)
    print("MUS:", mus_result)

    optimal = explain_unsat("optimal_mus", soft=constraints, check=False, weights=[1] * len(constraints))
    print("Optimal MUS:", optimal)

    for kind, subset in explain_unsat("marco", soft=constraints, check=False):
        print(kind, subset)
```

## Notes

- `mus()` and `mss()` use ACE core extraction for efficiency; they fall back to naive versions for non-ACE solvers.
- MCS is the complement of MSS: `MCS = Soft \ MSS`
- Removing MCS constraints from soft constraints leaves MSS, which is satisfiable.

## How It Works

### Constraint Explanation Problem

Given an infeasible constraint satisfaction problem (CSP), explanation tools help identify:

| Concept | Question | Description |
|---------|----------|-------------|
| **MUS** | Why is it infeasible? | Minimal Unsatisfiable Subset - the smallest set of constraints that conflict |
| **MSS** | What can be satisfied? | Maximal Satisfiable Subset - the largest set of constraints that can hold together |
| **MCS** | What to fix? | Minimal Correction Set - the smallest set of constraints to remove for satisfiability |

### Relationships

- Every MUS and every MCS share at least one constraint (hitting set duality)
- `MCS = Soft \ MSS` (MCS is the complement of MSS)
- Multiple MUSes/MSSes/MCSes may exist for a given problem

## API Reference

### MUS Functions
- `mus(soft, hard=None, solver="ace")` - Assumption-based MUS
- `mus_naive(soft, hard=None, solver="ace")` - Deletion-based MUS
- `mus_bicore(soft, hard=None, solver="ace")` - Core-guided batched exact MUS
- `mus_cpqx(soft, hard=None, solver="ace")` - Core-Projected QuickXplain (exact hybrid)
- `mus_bicore_qx(soft, hard=None, solver="ace")` - Hybrid BiCore + QuickXplain (exact)
- `quickxplain(soft, hard=None, solver="ace")` - Assumption-based preferred MUS (Junker, 2004)
- `is_mus(subset, hard=None, solver="ace")` - Verify MUS validity
- `all_mus_naive(soft, hard=None, solver="ace")` - Enumerate MUSes (naive)
- `optimal_mus(soft, hard=None, weights=None, solver="ace")` - Minimum-weight MUS
- `optimal_mus_naive(soft, hard=None, weights=None, solver="ace")` - Deprecated exhaustive minimum-weight MUS (emits `DeprecationWarning`)
- `smus(soft, hard=None, solver="ace")` - Smallest MUS (fewest constraints)
- `ocus(soft, hard=None, weights=None, solver="ace", ...)` - OCUS with subset constraints
- `ocus_naive(soft, hard=None, weights=None, solver="ace", ...)` - Deprecated exhaustive OCUS with subset constraints (emits `DeprecationWarning`)
- `OCUSException` - Exception for optimal MUS/OCUS routines

### MSS/MCS Functions
- `mss(soft, hard=None, solver="ace")` - Assumption-based MSS
- `mss_naive(soft, hard=None, solver="ace")` - Greedy growing MSS
- `mss_opt(soft, hard=None, weights=None, solver="ace")` - Exact weighted MSS
- `mss_heuristic(soft, hard=None, weights=None, solver="ace")` - Greedy weighted MSS approximation
- `is_mss(subset, soft, hard=None, solver="ace")` - Verify MSS validity
- `mcs(soft, hard=None, solver="ace")` - Assumption-based MCS
- `mcs_naive(soft, hard=None, solver="ace")` - Naive MCS
- `mcs_opt(soft, hard=None, weights=None, solver="ace")` - Exact weighted MCS
- `mcs_heuristic(soft, hard=None, weights=None, solver="ace")` - Greedy weighted MCS approximation
- `mcs_from_mss(mss, soft)` - Complement of MSS
- `is_mcs(subset, soft, hard=None, solver="ace")` - Verify MCS validity

### MARCO Enumeration
- `marco(soft, hard=None, solver="ace")` - Generator over MUS/MCS
- `marco_core(soft, hard=None, solver="ace")` - Core-informed MARCO generator
- `marco_naive(soft, hard=None, solver="ace")` - Naive MARCO
- `all_mus(soft, hard=None, solver="ace")` - Collect all MUSes
- `all_mcs(soft, hard=None, solver="ace")` - Collect all MCSes
- `all_mus_core(soft, hard=None, solver="ace")` - Collect all MUSes via `marco_core`
- `all_mcs_core(soft, hard=None, solver="ace")` - Collect all MCSes via `marco_core`

### Benchmark Scripts

- Script: `benchmarks/bench_mus_methods.py`
- Compare: `mus_naive`, `mus`, `mus_bicore`, `mus_bicore_qx`, `mus_cpqx`, `quickxplain`, `quickxplain_incremental`
- Script: `benchmarks/bench_marco_methods.py`
- Compare: `marco_naive`, `marco`, `marco_core`

Examples:

```bash
uv run python benchmarks/bench_mus_methods.py
uv run python benchmarks/bench_mus_methods.py --repeats 11 --warmup 1
uv run python benchmarks/bench_mus_methods.py --verbose
uv run python benchmarks/bench_mus_methods.py --method-verbose 0
uv run python benchmarks/bench_mus_methods.py --output-csv benchmarks/mus_runs.csv
uv run python benchmarks/bench_marco_methods.py
uv run python benchmarks/bench_marco_methods.py --repeats 7 --warmup 1
uv run python benchmarks/bench_marco_methods.py --output-csv benchmarks/marco_runs.csv
uv run python benchmarks/bench_marco_methods.py --cases large_irrelevant_pair_80,two_conflicts_irrelevant_60,alldiff_dense_core_24
uv run python benchmarks/bench_marco_methods.py --core-handoff 4 --core-base-ratio 1 --core-backoff-cap 8
```

## License

MIT License

## References

- [PyCSP3](https://github.com/xcsp3team/pycsp3) - Python library for constraint programming
- [CPMpy](https://github.com/CPMpy/cpmpy) - Constraint Programming and Modeling in Python
- Liffiton et al. (2016) - "Fast, flexible MUS enumeration"
- Junker (2004) - "QuickXplain: Preferred explanations and relaxations"
