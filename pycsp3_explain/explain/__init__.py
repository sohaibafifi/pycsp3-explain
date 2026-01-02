"""
Explanation algorithms for constraint satisfaction problems.

This module provides implementations of:
- MUS (Minimal Unsatisfiable Subset) algorithms
- MSS (Maximal Satisfiable Subset) algorithms (coming soon)
- MCS (Minimal Correction Set) algorithms (coming soon)
- MARCO enumeration algorithm (coming soon)
"""

from pycsp3_explain.explain.mus import (
    mus_naive,
    quickxplain_naive,
    is_mus,
    all_mus_naive,
)

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    get_constraint_variables,
    ConstraintTracker,
    order_by_num_variables,
)

__all__ = [
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
]
