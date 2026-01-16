"""
Solver wrapper for PyCSP3-Explain.

This module provides utilities for solving constraint models with subsets
of constraints, which is essential for MUS/MSS/MCS computation.
"""

import os
import tempfile
import traceback
import atexit
import re
from typing import List, Any, Optional, Tuple, Generator
from enum import Enum
from contextlib import contextmanager

from pycsp3_explain.explain.utils import flatten_constraints, normalize_constraint_list


class SolveResult(Enum):
    """Result of a solve operation."""
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    ERROR = "error"


_ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _parse_core_indices(core_line: Optional[str]) -> List[int]:
    if not core_line:
        return []
    cleaned = _strip_ansi(core_line)
    matches = re.findall(r"(?<!\()c(\d+)(?=\()", cleaned)
    if not matches:
        matches = re.findall(r"c(\d+)", cleaned)
    return [int(m) for m in matches]


def _normalize_constraints(constraints: Optional[List[Any]]) -> List[Any]:
    """Normalize and flatten constraints."""
    items = normalize_constraint_list(constraints)
    return flatten_constraints(items)


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


@contextmanager
def clean_pycsp3_state() -> Generator[None, None, None]:
    """
    Context manager that saves and restores PyCSP3 global state.

    This is essential for MUS/MSS algorithms that need to solve multiple
    subproblems without polluting the global state.

    Usage:
        with clean_pycsp3_state():
            # Create new variables/constraints
            # Solve subproblem
        # Original state is restored
    """
    disable_pycsp3_atexit()

    from pycsp3.classes.entities import (
        CtrEntities,
        VarEntities,
        ObjEntities,
        AnnEntities,
    )
    from pycsp3.classes.main.variables import Variable
    from pycsp3.classes.main.constraints import auxiliary
    from pycsp3.compiler import Compilation

    # Save constraint/objective/annotation state
    saved_ctr_items = CtrEntities.items[:]
    saved_obj_items = ObjEntities.items[:]
    saved_ann_items = AnnEntities.items[:]
    saved_ann_types = AnnEntities.items_types[:] if hasattr(AnnEntities, "items_types") else []

    # Save variable state
    saved_var_items = VarEntities.items[:]
    saved_var_to_evar = VarEntities.varToEVar.copy()
    saved_var_to_evar_array = VarEntities.varToEVarArray.copy()
    saved_prefix_to_evar_array = VarEntities.prefixToEVarArray.copy()
    saved_name2obj = Variable.name2obj.copy()
    saved_arrays = Variable.arrays[:] if hasattr(Variable, "arrays") else []

    # Save compilation state
    saved_compilation = {
        "done": Compilation.done,
        "model": Compilation.model,
        "string_model": Compilation.string_model,
        "string_data": Compilation.string_data,
        "data": Compilation.data,
        "solve": Compilation.solve,
        "stopwatch": Compilation.stopwatch,
        "stopwatch2": Compilation.stopwatch2,
        "pathname": Compilation.pathname,
        "filename": Compilation.filename,
    }

    # Save auxiliary constraint state
    aux = auxiliary()
    saved_aux_intro = aux._introduced_variables
    saved_aux_collected = aux._collected_constraints
    saved_aux_raw = aux._collected_raw_constraints
    saved_aux_ext = aux._collected_extension_constraints
    saved_aux_cache = aux.cache
    saved_aux_cache_ints = aux.cache_ints.copy()
    saved_aux_cache_nodes = aux.cache_nodes.copy()

    try:
        # Clear all state for fresh subproblem
        CtrEntities.items = []
        ObjEntities.items = []
        AnnEntities.items = []
        if hasattr(AnnEntities, "items_types"):
            AnnEntities.items_types = []
        VarEntities.items = []
        VarEntities.varToEVar = {}
        VarEntities.varToEVarArray = {}
        VarEntities.prefixToEVarArray = {}
        Variable.name2obj = {}
        if hasattr(Variable, "arrays"):
            Variable.arrays = []

        aux._introduced_variables = []
        aux._collected_constraints = []
        aux._collected_raw_constraints = []
        aux._collected_extension_constraints = []
        aux.cache = []
        aux.cache_ints = {}
        aux.cache_nodes = {}

        Compilation.done = False
        Compilation.model = None
        Compilation.string_model = None
        Compilation.string_data = None
        Compilation.data = None
        Compilation.solve = None
        Compilation.stopwatch = None
        Compilation.stopwatch2 = None
        Compilation.pathname = ""
        Compilation.filename = ""

        yield

    finally:
        # Restore all state
        CtrEntities.items = saved_ctr_items
        ObjEntities.items = saved_obj_items
        AnnEntities.items = saved_ann_items
        if hasattr(AnnEntities, "items_types"):
            AnnEntities.items_types = saved_ann_types
        VarEntities.items = saved_var_items
        VarEntities.varToEVar = saved_var_to_evar
        VarEntities.varToEVarArray = saved_var_to_evar_array
        VarEntities.prefixToEVarArray = saved_prefix_to_evar_array
        Variable.name2obj = saved_name2obj
        if hasattr(Variable, "arrays"):
            Variable.arrays = saved_arrays

        aux._introduced_variables = saved_aux_intro
        aux._collected_constraints = saved_aux_collected
        aux._collected_raw_constraints = saved_aux_raw
        aux._collected_extension_constraints = saved_aux_ext
        aux.cache = saved_aux_cache
        aux.cache_ints = saved_aux_cache_ints
        aux.cache_nodes = saved_aux_cache_nodes

        Compilation.done = saved_compilation["done"]
        Compilation.model = saved_compilation["model"]
        Compilation.string_model = saved_compilation["string_model"]
        Compilation.string_data = saved_compilation["string_data"]
        Compilation.data = saved_compilation["data"]
        Compilation.solve = saved_compilation["solve"]
        Compilation.stopwatch = saved_compilation["stopwatch"]
        Compilation.stopwatch2 = saved_compilation["stopwatch2"]
        Compilation.pathname = saved_compilation["pathname"]
        Compilation.filename = saved_compilation["filename"]


def _solve_subset_internal(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1,
    timeout: Optional[int] = None,
    extraction: bool = False
) -> Tuple[SolveResult, Optional[str]]:
    """
    Internal solver entry point. When extraction=True, attempts to extract an UNSAT core.
    Returns a tuple of (SolveResult, core_line).
    """
    # Disable PyCSP3's atexit callback to prevent errors
    disable_pycsp3_atexit()

    # Import pycsp3 modules
    from pycsp3 import satisfy, solve, SAT, UNSAT, UNKNOWN, OPTIMUM, CORE, core as pycsp3_core
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

    core_line = None

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
        soft = _normalize_constraints(soft)
        hard = _normalize_constraints(hard)
        all_constraints = hard + soft

        if not all_constraints:
            return SolveResult.SAT, None  # Empty model is SAT

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
        status = solve(
            solver=solver_type,
            verbose=verbose,
            options=options_str,
            filename=temp_filename,
            extraction=extraction,
        )

        if extraction:
            core_line = pycsp3_core()

        # Clean up temp file
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except OSError:
            pass

        if status == SAT or status == OPTIMUM:
            return SolveResult.SAT, core_line
        elif status == UNSAT or status == CORE:
            return SolveResult.UNSAT, core_line
        else:
            return SolveResult.UNKNOWN, core_line

    except Exception as e:
        if verbose >= 0:
            print(f"Solver error: {e}")
            traceback.print_exc()
        return SolveResult.ERROR, core_line

    finally:
        # Restore constraint state only (not variables)
        CtrEntities.items = saved_ctr_items
        ObjEntities.items = saved_obj_items
        AnnEntities.items = saved_ann_items
        if hasattr(AnnEntities, 'items_types'):
            AnnEntities.items_types = saved_ann_types

        # Note: We don't restore Compilation state - it needs to stay as-is
        # for the solve result to be valid


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
    result, _ = _solve_subset_internal(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        timeout=timeout,
        extraction=False,
    )
    return result


def solve_subset_with_core(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1,
    timeout: Optional[int] = None
) -> Tuple[SolveResult, List[int]]:
    """
    Solve a model with constraints and attempt to extract an UNSAT core.

    :return: (SolveResult, core_indices) where core_indices refers to the
             constraint positions in hard + soft.
    """
    result, core_line = _solve_subset_internal(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        timeout=timeout,
        extraction=True,
    )
    return result, _parse_core_indices(core_line)


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
