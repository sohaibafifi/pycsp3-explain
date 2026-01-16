"""
Solver utilities for PyCSP3-Explain.

This module provides wrappers around PyCSP3 solvers for checking
satisfiability of constraint subsets.
"""

from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    SolveCache,
    solve_subset,
    solve_subset_with_core,
    is_sat,
    is_unsat,
    disable_pycsp3_atexit,
    clean_pycsp3_state,
    get_solve_cache,
    clear_solve_cache,
)

__all__ = [
    "SolveResult",
    "SolveCache",
    "solve_subset",
    "solve_subset_with_core",
    "is_sat",
    "is_unsat",
    "disable_pycsp3_atexit",
    "clean_pycsp3_state",
    "get_solve_cache",
    "clear_solve_cache",
]
