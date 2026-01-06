"""
PyCSP3-Explain: Explanation tools for PyCSP3 constraint models.

This package provides algorithms for finding:
- MUS (Minimal Unsatisfiable Subsets)
- MSS (Maximal Satisfiable Subsets)
- MCS (Minimal Correction Sets)
- MARCO enumeration of all MUS/MCS
- Optimal MUS algorithms (SMUS, OCUS)

Example usage:
    from pycsp3 import *
    from pycsp3_explain import mus_naive, mss_naive

    # Create variables and constraints
    clear()
    x = VarArray(size=3, dom=range(10))
    constraints = [x[0] == 5, x[0] == 7, x[1] >= 3]

    # Find minimal unsatisfiable subset
    conflict = mus_naive(soft=constraints)
    print("Conflicting constraints:", conflict)

    # Find maximal satisfiable subset
    satisfiable = mss_naive(soft=constraints)
    print("Satisfiable constraints:", satisfiable)

    # Enumerate all MUSes and MCSes
    from pycsp3_explain import marco
    for result_type, subset in marco(soft=constraints):
        print(f"{result_type}: {len(subset)} constraints")

    # Find smallest MUS
    from pycsp3_explain import smus
    smallest = smus(soft=constraints)
    print("Smallest MUS:", smallest)
"""

__version__ = "0.1.0"

# Import MUS algorithms
from pycsp3_explain.explain.mus import (
    mus,
    mus_naive,
    quickxplain_naive,
    is_mus,
    all_mus_naive,
    optimal_mus,
    optimal_mus_naive,
    smus,
    ocus,
    ocus_naive,
    OCUSException,
)

# Import MSS/MCS algorithms
from pycsp3_explain.explain.mss import (
    mss,
    mss_naive,
    mss_opt,
    is_mss,
    mcs,
    mcs_naive,
    mcs_opt,
    mcs_from_mss,
    is_mcs,
)

# Import MARCO enumeration
from pycsp3_explain.explain.marco import (
    marco,
    marco_naive,
    all_mus,
    all_mcs,
)

# Import utility functions
from pycsp3_explain.explain.utils import (
    flatten_constraints,
    get_constraint_variables,
    explain_unsat,
    ConstraintTracker,
    make_assump_model,
    order_by_num_variables,
)

# Import solver utilities
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    solve_subset,
    solve_subset_with_core,
    is_sat,
    is_unsat,
)

__all__ = [
    # Version
    "__version__",
    # MUS algorithms
    "mus",
    "mus_naive",
    "quickxplain_naive",
    "is_mus",
    "all_mus_naive",
    # Optimal MUS algorithms
    "optimal_mus",
    "optimal_mus_naive",
    "smus",
    "ocus",
    "ocus_naive",
    "OCUSException",
    # MSS algorithms
    "mss",
    "mss_naive",
    "mss_opt",
    "is_mss",
    # MCS algorithms
    "mcs",
    "mcs_naive",
    "mcs_opt",
    "mcs_from_mss",
    "is_mcs",
    # MARCO enumeration
    "marco",
    "marco_naive",
    "all_mus",
    "all_mcs",
    # Utilities
    "flatten_constraints",
    "get_constraint_variables",
    "explain_unsat",
    "ConstraintTracker",
    "make_assump_model",
    "order_by_num_variables",
    # Solver utilities
    "SolveResult",
    "solve_subset",
    "solve_subset_with_core",
    "is_sat",
    "is_unsat",
]
