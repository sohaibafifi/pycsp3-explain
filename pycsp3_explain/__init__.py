"""
PyCSP3-Explain: Explanation tools for PyCSP3 constraint models.

This package provides algorithms for finding:
- MUS (Minimal Unsatisfiable Subsets)
- MSS (Maximal Satisfiable Subsets)
- MCS (Minimal Correction Sets)
- MARCO enumeration of all MUS/MCS

Example usage:
    from pycsp3 import *
    from pycsp3_explain import mus_naive, quickxplain_naive

    # Create variables and constraints
    clear()
    x = VarArray(size=3, dom=range(10))
    constraints = [x[0] == 5, x[0] == 7, x[1] >= 3]

    # Find minimal unsatisfiable subset
    conflict = mus_naive(soft=constraints)
    print("Conflicting constraints:", conflict)
"""

__version__ = "0.1.0"

# Import MUS algorithms
from pycsp3_explain.explain.mus import (
    mus_naive,
    quickxplain_naive,
    is_mus,
    all_mus_naive,
)

# Import utility functions
from pycsp3_explain.explain.utils import (
    flatten_constraints,
    get_constraint_variables,
    ConstraintTracker,
    order_by_num_variables,
)

# Import solver utilities
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    solve_subset,
    is_sat,
    is_unsat,
)

__all__ = [
    # Version
    "__version__",
    # MUS algorithms
    "mus_naive",
    "quickxplain_naive",
    "is_mus",
    "all_mus_naive",
    # Utilities
    "flatten_constraints",
    "get_constraint_variables",
    "ConstraintTracker",
    "order_by_num_variables",
    # Solver utilities
    "SolveResult",
    "solve_subset",
    "is_sat",
    "is_unsat",
]
