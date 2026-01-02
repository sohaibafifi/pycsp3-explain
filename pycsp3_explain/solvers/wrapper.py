"""
Solver wrapper for PyCSP3-Explain.

This module provides utilities for solving constraint models with subsets
of constraints, which is essential for MUS/MSS/MCS computation.
"""

import os
import tempfile
import traceback
import atexit
from typing import List, Any, Optional
from enum import Enum


class SolveResult(Enum):
    """Result of a solve operation."""
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    ERROR = "error"


def disable_pycsp3_atexit():
    """
    Disable PyCSP3's atexit callback to prevent errors when Compilation state is invalid.

    PyCSP3 registers an atexit callback that tries to compile the model at exit,
    which can fail when the Compilation state has been modified during MUS computation.
    """
    try:
        from pycsp3 import end as pycsp3_end
        # Unregister PyCSP3's end function from atexit
        atexit.unregister(pycsp3_end)
    except (ImportError, AttributeError):
        pass


def solve_subset(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1,
    timeout: Optional[int] = None
) -> SolveResult:
    """
    Solve a model with a subset of constraints.

    This function creates a fresh PyCSP3 model with the given constraints,
    compiles it, and solves it.

    :param soft: List of soft constraints to include
    :param hard: List of hard constraints (always included)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :param timeout: Optional timeout in seconds
    :return: SolveResult indicating SAT, UNSAT, or UNKNOWN
    """
    # Disable PyCSP3's atexit callback to prevent errors
    disable_pycsp3_atexit()

    # Import pycsp3 modules
    from pycsp3 import satisfy, solve, SAT, UNSAT, UNKNOWN, OPTIMUM
    from pycsp3 import ACE, CHOCO
    from pycsp3.classes.entities import CtrEntities, VarEntities, ObjEntities, AnnEntities
    from pycsp3.compiler import Compilation

    # Save current constraint state (NOT variables - those are managed by the caller)
    saved_ctr_items = CtrEntities.items[:]
    saved_obj_items = ObjEntities.items[:]
    saved_ann_items = AnnEntities.items[:]
    saved_ann_types = AnnEntities.items_types[:] if hasattr(AnnEntities, 'items_types') else []

    # Save and reset compilation state
    saved_compilation_done = Compilation.done
    saved_compilation_model = Compilation.model
    saved_compilation_string_model = Compilation.string_model

    try:
        # Reset compilation state for fresh solve
        Compilation.done = False
        Compilation.model = None
        Compilation.string_model = None

        # Clear only constraints and objectives (keep variables!)
        CtrEntities.items = []
        ObjEntities.items = []
        AnnEntities.items = []
        if hasattr(AnnEntities, 'items_types'):
            AnnEntities.items_types = []

        # Post constraints
        all_constraints = []
        if hard:
            all_constraints.extend(hard)
        all_constraints.extend(soft)

        if not all_constraints:
            return SolveResult.SAT  # Empty model is SAT

        satisfy(*all_constraints)

        # Build solver options
        solver_type = ACE if solver.lower() == "ace" else CHOCO
        options_str = ""
        if timeout:
            options_str = f"-t={timeout}s"

        # Generate a unique temp filename for this solve
        import uuid
        temp_filename = os.path.join(tempfile.gettempdir(), f"pycsp3_explain_{uuid.uuid4().hex}.xml")

        # Solve with explicit filename
        status = solve(solver=solver_type, verbose=verbose, options=options_str, filename=temp_filename)

        # Clean up temp file
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except:
            pass

        if status == SAT or status == OPTIMUM:
            return SolveResult.SAT
        elif status == UNSAT:
            return SolveResult.UNSAT
        else:
            return SolveResult.UNKNOWN

    except Exception as e:
        if verbose >= 0:
            print(f"Solver error: {e}")
            traceback.print_exc()
        return SolveResult.ERROR

    finally:
        # Restore constraint state only (not variables)
        CtrEntities.items = saved_ctr_items
        ObjEntities.items = saved_obj_items
        AnnEntities.items = saved_ann_items
        if hasattr(AnnEntities, 'items_types'):
            AnnEntities.items_types = saved_ann_types

        # Note: We don't restore Compilation state - it needs to stay as-is
        # for the solve result to be valid


def is_sat(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> bool:
    """
    Check if a set of constraints is satisfiable.

    :param soft: List of soft constraints
    :param hard: List of hard constraints (always included)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: True if SAT, False otherwise
    """
    result = solve_subset(soft, hard, solver, verbose)
    return result == SolveResult.SAT


def is_unsat(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> bool:
    """
    Check if a set of constraints is unsatisfiable.

    :param soft: List of soft constraints
    :param hard: List of hard constraints (always included)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: True if UNSAT, False otherwise
    """
    result = solve_subset(soft, hard, solver, verbose)
    return result == SolveResult.UNSAT
