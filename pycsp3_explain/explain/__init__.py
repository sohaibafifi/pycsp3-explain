"""
Explanation algorithms for constraint satisfaction problems.

This module provides implementations of:
- MUS (Minimal Unsatisfiable Subset) algorithms
- MSS (Maximal Satisfiable Subset) algorithms
- MCS (Minimal Correction Set) algorithms
- MARCO enumeration algorithm (coming soon)
"""

from pycsp3_explain.explain.mus import (
    mus,
    mus_naive,
    quickxplain_naive,
    is_mus,
    all_mus_naive,
)

from pycsp3_explain.explain.mss import (
    mss,
    mss_naive,
    is_mss,
    mcs,
    mcs_naive,
    mcs_from_mss,
    is_mcs,
)

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    get_constraint_variables,
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
    # MSS algorithms
    "mss",
    "mss_naive",
    "is_mss",
    # MCS algorithms
    "mcs",
    "mcs_naive",
    "mcs_from_mss",
    "is_mcs",
    # Utilities
    "flatten_constraints",
    "get_constraint_variables",
    "ConstraintTracker",
    "make_assump_model",
    "order_by_num_variables",
]
