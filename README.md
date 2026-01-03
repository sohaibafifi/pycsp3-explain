# PyCSP3-Explain

Explanation tools for PyCSP3 constraint models. Find minimal unsatisfiable subsets (MUS), maximal satisfiable subsets (MSS), and minimal correction sets (MCS) to debug and understand infeasible constraint problems.

## Features

- **MUS (Minimal Unsatisfiable Subset)**: Find the minimal set of conflicting constraints
  - `mus()` - Assumption-based using ACE core extraction
  - `mus_naive()` - Deletion-based (works with any solver)
  - `quickxplain_naive()` - Preferred MUS based on constraint ordering
- **MSS (Maximal Satisfiable Subset)**: Find the maximum satisfiable portion
  - `mss()` - Assumption-based with core extraction
  - `mss_naive()` - Greedy growing algorithm
- **MCS (Minimal Correction Set)**: Find the minimal changes needed to restore satisfiability
  - `mcs()` - Via assumption-based MSS complement
  - `mcs_naive()` - Via naive MSS complement
- **MARCO**: Planned (not implemented yet)

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

### Finding Conflicts (MUS)

```python
from pycsp3 import *
from pycsp3_explain import mus, mus_naive, is_mus

# Define an infeasible model
clear()
x = VarArray(size=3, dom=range(10))

constraints = [
    x[0] + x[1] == 5,
    x[1] + x[2] == 3,
    x[0] + x[2] == 10,
    x[0] == x[1],
    x[1] == x[2],
]

# Find a minimal unsatisfiable subset (assumption-based with ACE)
minimal_conflict = mus(soft=constraints, solver="ace")
print("MUS:", minimal_conflict)
print("Valid MUS:", is_mus(minimal_conflict, solver="ace"))
```

### Finding Relaxations (MSS/MCS)

```python
from pycsp3 import *
from pycsp3_explain import mss, mcs, is_mss, is_mcs

clear()
x = VarArray(size=3, dom=range(10))

constraints = [
    x[0] == 5,       # c0
    x[1] >= 3,       # c1
    x[0] == 7,       # c2 - conflicts with c0
    x[2] <= 8,       # c3
]

# Find maximum satisfiable subset
max_sat = mss(soft=constraints, solver="ace")
print("MSS:", max_sat)  # e.g., [c0, c1, c3]

# Find minimum correction set (constraints to remove)
correction = mcs(soft=constraints, solver="ace")
print("MCS:", correction)  # e.g., [c2]
```

## Examples

```bash
# MUS examples
python examples/example_simple_conflict.py
python examples/example_scheduling_conflict.py
python examples/example_nqueens_conflict.py

# MSS/MCS example
python examples/example_mss_relaxation.py
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
- `quickxplain_naive(soft, hard=None, solver="ace")` - Preferred MUS
- `is_mus(subset, hard=None, solver="ace")` - Verify MUS validity

### MSS/MCS Functions
- `mss(soft, hard=None, solver="ace")` - Assumption-based MSS
- `mss_naive(soft, hard=None, solver="ace")` - Greedy growing MSS
- `is_mss(subset, soft, hard=None, solver="ace")` - Verify MSS validity
- `mcs(soft, hard=None, solver="ace")` - Assumption-based MCS
- `mcs_naive(soft, hard=None, solver="ace")` - Naive MCS
- `is_mcs(subset, soft, hard=None, solver="ace")` - Verify MCS validity

## License

MIT License

## References

- [PyCSP3](https://github.com/xcsp3team/pycsp3) - Python library for constraint programming
- [CPMpy](https://github.com/CPMpy/cpmpy) - Constraint Programming and Modeling in Python
- Liffiton et al. (2016) - "Fast, flexible MUS enumeration"
- Junker (2004) - "QuickXplain: Preferred explanations and relaxations"
