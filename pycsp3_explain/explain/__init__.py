"""
Explanation algorithms for constraint satisfaction problems.

This module provides implementations of:
- MUS (Minimal Unsatisfiable Subset) algorithms
- MSS (Maximal Satisfiable Subset) algorithms
- MCS (Minimal Correction Set) algorithms
- MARCO enumeration algorithm for complete MUS/MCS enumeration
- Optimal MUS algorithms (SMUS, OCUS)
"""

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

from pycsp3_explain.explain.marco import (
    marco,
    marco_naive,
    all_mus,
    all_mcs,
)

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    get_constraint_variables,
    explain_unsat,
    ConstraintTracker,
    make_assump_model,
    order_by_num_variables,
)

__all__ = [
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
]
