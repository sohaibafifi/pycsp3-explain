# PyCSP3-Explain

Explanation tools for PyCSP3 constraint models. Find minimal unsatisfiable subsets (MUS), maximal satisfiable subsets (MSS), and minimal correction sets (MCS) to debug and understand infeasible constraint problems.

## Features and roadmap

- **MUS (Minimal Unsatisfiable Subset)**: Find the smallest set of constraints that cause infeasibility
- **MSS (Maximal Satisfiable Subset)**: Find the largest subset of constraints that can be satisfied
- **MCS (Minimal Correction Set)**: Find the minimal set of constraints to remove for feasibility
- **MARCO**: Enumerate all MUS and MCS for complete analysis

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
- PyCSP3

## Quick Start

```python
from pycsp3 import *
from pycsp3_explain import mus_naive, mcs_naive

# Define an infeasible model
x = VarArray(size=3, dom=range(10))

constraints = [
    x[0] + x[1] == 5,
    x[1] + x[2] == 3,
    x[0] + x[2] == 10,
    x[0] == x[1],
    x[1] == x[2],
]

# Find a minimal unsatisfiable subset
minimal_conflict = mus_naive(soft=constraints)
print("MUS:", minimal_conflict)

# Find minimal corrections needed
corrections = mcs_naive(soft=constraints)
print("MCS:", corrections)
```


## How It Works

### Constraint Explanation Problem

Given an infeasible constraint satisfaction problem (CSP), explanation tools help identify:

1. **Why is it infeasible?** (MUS) - The minimal set of conflicting constraints
2. **What can be satisfied?** (MSS) - The maximum satisfiable portion
3. **What to fix?** (MCS) - The minimal changes needed

## License

MIT License

## References

- [PyCSP3](https://github.com/xcsp3team/pycsp3) - Python library for constraint programming
- [CPMpy](https://github.com/CPMpy/cpmpy) - Constraint Programming and Modeling in Python
- Liffiton et al. (2016) - "Fast, flexible MUS enumeration"
- Junker (2004) - "QuickXplain: Preferred explanations and relaxations"
