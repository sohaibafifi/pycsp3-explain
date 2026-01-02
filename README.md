# PyCSP3-Explain

Explanation tools for PyCSP3 constraint models. Find minimal unsatisfiable subsets (MUS) to debug and understand infeasible constraint problems.

## Features and roadmap

- **MUS (Minimal Unsatisfiable Subset)**: Assumption-based MUS using ACE core extraction and a naive deletion-based MUS
- **QuickXplain (naive)**: Preferred MUS based on constraint ordering
- **MSS/MCS/MARCO**: Planned (not implemented yet)

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
print("MUS (assumption-based):", minimal_conflict)
print("Valid:", is_mus(minimal_conflict, solver="ace"))

# Naive MUS (works with any solver, but slower)
minimal_conflict_naive = mus_naive(soft=constraints, solver="ace")
print("MUS (naive):", minimal_conflict_naive)
```

## Examples

```bash
python examples/example_simple_conflict.py
python examples/example_scheduling_conflict.py
python examples/example_nqueens_conflict.py
```

## Notes

- `mus()` uses ACE core extraction; if you pass a non-ACE solver it will fall back to `mus_naive()`.
- Examples print both assumption-based and naive MUS results for comparison.

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
