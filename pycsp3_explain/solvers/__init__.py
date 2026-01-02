"""
Solver utilities for PyCSP3-Explain.

This module provides wrappers around PyCSP3 solvers for checking
satisfiability of constraint subsets.
"""

from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    solve_subset,
    is_sat,
    is_unsat,
    disable_pycsp3_atexit,
)

__all__ = [
    "SolveResult",
    "solve_subset",
    "is_sat",
    "is_unsat",
    "disable_pycsp3_atexit",
]

