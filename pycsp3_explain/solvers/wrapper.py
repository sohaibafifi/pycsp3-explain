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
import signal
import subprocess
from typing import List, Any, Optional, Tuple, Generator, NamedTuple, Dict, FrozenSet
from enum import Enum
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from collections import OrderedDict

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    normalize_constraint_list,
    Constraint,
    ConstraintList,
)


# ============================================================================
# Solve Result Caching
# ============================================================================

# Default cache size for solve results
DEFAULT_CACHE_SIZE = 1024


class SolveCache:
    """
    LRU cache for solve results to avoid redundant solver calls.

    The cache key is based on constraint object identities (id()) and
    the solver configuration. This allows caching results for constraint
    subsets that are tested multiple times during MUS/MSS computation.
    """

    def __init__(self, maxsize: int = DEFAULT_CACHE_SIZE) -> None:
        self._cache: OrderedDict[Tuple[FrozenSet[int], FrozenSet[int], str], SolveResult] = OrderedDict()
        self._maxsize = maxsize
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        soft: ConstraintList,
        hard: ConstraintList,
        solver: str
    ) -> Tuple[FrozenSet[int], FrozenSet[int], str]:
        """Create a cache key from constraint lists."""
        soft_key = frozenset(id(c) for c in soft)
        hard_key = frozenset(id(c) for c in hard)
        return (soft_key, hard_key, solver.lower())

    def get(
        self,
        soft: ConstraintList,
        hard: ConstraintList,
        solver: str
    ) -> Optional["SolveResult"]:
        """Get cached result if available."""
        key = self._make_key(soft, hard, solver)
        if key in self._cache:
            self._hits += 1
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            return self._cache[key]
        self._misses += 1
        return None

    def put(
        self,
        soft: ConstraintList,
        hard: ConstraintList,
        solver: str,
        result: "SolveResult"
    ) -> None:
        """Store a solve result in the cache."""
        key = self._make_key(soft, hard, solver)
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                # Remove oldest entry
                self._cache.popitem(last=False)
        self._cache[key] = result

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "maxsize": self._maxsize,
        }


# Global solve cache instance
_solve_cache = SolveCache()


def get_solve_cache() -> SolveCache:
    """Get the global solve cache instance."""
    return _solve_cache


def clear_solve_cache() -> None:
    """Clear the global solve cache."""
    _solve_cache.clear()


class SolveResult(Enum):
    """Result of a solve operation."""
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"
    ERROR = "error"


# Regex patterns for core extraction from ACE solver output
_ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
# Pattern: c<number>( - constraint index followed by opening paren
_CORE_PATTERN_WITH_PAREN = re.compile(r"(?<!\()c(\d+)(?=\()")
# Fallback pattern: c<number> - just constraint index
_CORE_PATTERN_SIMPLE = re.compile(r"\bc(\d+)\b")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_ESCAPE.sub("", text)


def _parse_core_indices(core_line: Optional[str]) -> List[int]:
    """
    Parse constraint indices from ACE solver core output.

    ACE outputs core information in various formats:
    - "c0(x[0] == 5) c1(x[0] == 7)" - with constraint content
    - "c0 c1 c2" - just indices

    :param core_line: Raw core output string from solver
    :return: List of constraint indices found in the output
    """
    if not core_line:
        return []

    cleaned = _strip_ansi(core_line)

    # Try pattern with parentheses first (more specific)
    matches = _CORE_PATTERN_WITH_PAREN.findall(cleaned)

    # Fall back to simple pattern if no matches
    if not matches:
        matches = _CORE_PATTERN_SIMPLE.findall(cleaned)

    # Convert to integers and remove duplicates while preserving order
    seen: set[int] = set()
    result: List[int] = []
    for m in matches:
        idx = int(m)
        if idx not in seen:
            seen.add(idx)
            result.append(idx)

    return result


def _normalize_constraints(constraints: Optional[ConstraintList]) -> ConstraintList:
    """Normalize and flatten constraints."""
    items = normalize_constraint_list(constraints)
    return flatten_constraints(items)


def disable_pycsp3_atexit() -> None:
    """
    Disable PyCSP3's atexit callback to prevent errors when Compilation state is invalid.

    PyCSP3 registers an atexit callback that tries to compile the model at exit,
    which can fail when the Compilation state has been modified during MUS computation.
    """
    try:
        from pycsp3 import end as pycsp3_end
        atexit.unregister(pycsp3_end)
    except (ImportError, AttributeError):
        pass


@contextmanager
def _sigint_kill_solver() -> Generator[None, None, None]:
    """
    Keep a SIGINT handler that raises KeyboardInterrupt and kills the solver process.
    This avoids PyCSP3 swallowing Ctrl-C by overriding the handler internally.
    """
    from pycsp3.tools.utilities import is_windows

    orig_signal = signal.signal
    orig_handler = signal.getsignal(signal.SIGINT)
    orig_popen = subprocess.Popen
    proc_holder: Dict[str, Any] = {"proc": None}

    def popen_wrapper(*args, **kwargs):
        proc = orig_popen(*args, **kwargs)
        proc_holder["proc"] = proc
        return proc

    def sigint_handler(signum, frame):
        proc = proc_holder["proc"]
        if proc and proc.poll() is None:
            try:
                if not is_windows():
                    os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                else:
                    proc.send_signal(signal.SIGINT)
            except Exception:
                pass
        raise KeyboardInterrupt

    def signal_wrapper(sig, handler):
        if sig == signal.SIGINT:
            return orig_handler
        return orig_signal(sig, handler)

    subprocess.Popen = popen_wrapper
    signal.signal = signal_wrapper
    orig_signal(signal.SIGINT, sigint_handler)
    try:
        yield
    finally:
        subprocess.Popen = orig_popen
        signal.signal = orig_signal
        orig_signal(signal.SIGINT, orig_handler)


@dataclass
class _PyCSP3State:
    """Saved PyCSP3 global state for restoration."""
    # Entity state
    ctr_items: List[Any] = field(default_factory=list)
    obj_items: List[Any] = field(default_factory=list)
    ann_items: List[Any] = field(default_factory=list)
    ann_types: List[Any] = field(default_factory=list)
    var_items: List[Any] = field(default_factory=list)
    var_to_evar: Dict[Any, Any] = field(default_factory=dict)
    var_to_evar_array: Dict[Any, Any] = field(default_factory=dict)
    prefix_to_evar_array: Dict[Any, Any] = field(default_factory=dict)
    name2obj: Dict[str, Any] = field(default_factory=dict)
    arrays: List[Any] = field(default_factory=list)

    # Compilation state
    compilation_done: bool = False
    compilation_model: Any = None
    compilation_string_model: Any = None
    compilation_string_data: Any = None
    compilation_data: Any = None
    compilation_solve: Any = None
    compilation_stopwatch: Any = None
    compilation_stopwatch2: Any = None
    compilation_pathname: str = ""
    compilation_filename: str = ""

    # Auxiliary state
    aux_introduced: List[Any] = field(default_factory=list)
    aux_collected: List[Any] = field(default_factory=list)
    aux_raw: List[Any] = field(default_factory=list)
    aux_ext: List[Any] = field(default_factory=list)
    aux_cache: List[Any] = field(default_factory=list)
    aux_cache_ints: Dict[Any, Any] = field(default_factory=dict)
    aux_cache_nodes: Dict[Any, Any] = field(default_factory=dict)


def _save_pycsp3_state() -> _PyCSP3State:
    """Save current PyCSP3 global state."""
    from pycsp3.classes.entities import CtrEntities, VarEntities, ObjEntities, AnnEntities
    from pycsp3.classes.main.variables import Variable
    from pycsp3.classes.main.constraints import auxiliary
    from pycsp3.compiler import Compilation

    aux = auxiliary()

    return _PyCSP3State(
        ctr_items=CtrEntities.items[:],
        obj_items=ObjEntities.items[:],
        ann_items=AnnEntities.items[:],
        ann_types=AnnEntities.items_types[:] if hasattr(AnnEntities, "items_types") else [],
        var_items=VarEntities.items[:],
        var_to_evar=VarEntities.varToEVar.copy(),
        var_to_evar_array=VarEntities.varToEVarArray.copy(),
        prefix_to_evar_array=VarEntities.prefixToEVarArray.copy(),
        name2obj=Variable.name2obj.copy(),
        arrays=Variable.arrays[:] if hasattr(Variable, "arrays") else [],
        compilation_done=Compilation.done,
        compilation_model=Compilation.model,
        compilation_string_model=Compilation.string_model,
        compilation_string_data=Compilation.string_data,
        compilation_data=Compilation.data,
        compilation_solve=Compilation.solve,
        compilation_stopwatch=Compilation.stopwatch,
        compilation_stopwatch2=Compilation.stopwatch2,
        compilation_pathname=Compilation.pathname,
        compilation_filename=Compilation.filename,
        aux_introduced=aux._introduced_variables,
        aux_collected=aux._collected_constraints,
        aux_raw=aux._collected_raw_constraints,
        aux_ext=aux._collected_extension_constraints,
        aux_cache=aux.cache,
        aux_cache_ints=aux.cache_ints.copy(),
        aux_cache_nodes=aux.cache_nodes.copy(),
    )


def _restore_pycsp3_state(state: _PyCSP3State) -> None:
    """Restore PyCSP3 global state from saved state."""
    from pycsp3.classes.entities import CtrEntities, VarEntities, ObjEntities, AnnEntities
    from pycsp3.classes.main.variables import Variable
    from pycsp3.classes.main.constraints import auxiliary
    from pycsp3.compiler import Compilation

    # Restore entity state
    CtrEntities.items = state.ctr_items
    ObjEntities.items = state.obj_items
    AnnEntities.items = state.ann_items
    if hasattr(AnnEntities, "items_types"):
        AnnEntities.items_types = state.ann_types
    VarEntities.items = state.var_items
    VarEntities.varToEVar = state.var_to_evar
    VarEntities.varToEVarArray = state.var_to_evar_array
    VarEntities.prefixToEVarArray = state.prefix_to_evar_array
    Variable.name2obj = state.name2obj
    if hasattr(Variable, "arrays"):
        Variable.arrays = state.arrays

    # Restore auxiliary state
    aux = auxiliary()
    aux._introduced_variables = state.aux_introduced
    aux._collected_constraints = state.aux_collected
    aux._collected_raw_constraints = state.aux_raw
    aux._collected_extension_constraints = state.aux_ext
    aux.cache = state.aux_cache
    aux.cache_ints = state.aux_cache_ints
    aux.cache_nodes = state.aux_cache_nodes

    # Restore compilation state
    Compilation.done = state.compilation_done
    Compilation.model = state.compilation_model
    Compilation.string_model = state.compilation_string_model
    Compilation.string_data = state.compilation_string_data
    Compilation.data = state.compilation_data
    Compilation.solve = state.compilation_solve
    Compilation.stopwatch = state.compilation_stopwatch
    Compilation.stopwatch2 = state.compilation_stopwatch2
    Compilation.pathname = state.compilation_pathname
    Compilation.filename = state.compilation_filename


def _clear_pycsp3_state() -> None:
    """Clear all PyCSP3 global state for a fresh subproblem."""
    from pycsp3.classes.entities import CtrEntities, VarEntities, ObjEntities, AnnEntities
    from pycsp3.classes.main.variables import Variable
    from pycsp3.classes.main.constraints import auxiliary
    from pycsp3.compiler import Compilation

    # Clear entity state
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

    # Clear auxiliary state
    aux = auxiliary()
    aux._introduced_variables = []
    aux._collected_constraints = []
    aux._collected_raw_constraints = []
    aux._collected_extension_constraints = []
    aux.cache = []
    aux.cache_ints = {}
    aux.cache_nodes = {}

    # Clear compilation state
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
    saved_state = _save_pycsp3_state()

    try:
        _clear_pycsp3_state()
        yield
    finally:
        _restore_pycsp3_state(saved_state)


def _solve_subset_internal(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
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
    from pycsp3.dashboard import options as pycsp3_options
    # from pycsp3.compiler import options as pycsp3_options

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

    prev_compactor = pycsp3_options.dontruncompactor

    try:
        pycsp3_options.dontruncompactor = True
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
        with _sigint_kill_solver():
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
        pycsp3_options.dontruncompactor = prev_compactor
        # Restore constraint state only (not variables)
        CtrEntities.items = saved_ctr_items
        ObjEntities.items = saved_obj_items
        AnnEntities.items = saved_ann_items
        if hasattr(AnnEntities, 'items_types'):
            AnnEntities.items_types = saved_ann_types

        # Note: We don't restore Compilation state - it needs to stay as-is
        # for the solve result to be valid


def solve_subset(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    verbose: int = -1,
    timeout: Optional[int] = None,
    use_cache: bool = True
) -> SolveResult:
    """
    Solve a model with a subset of constraints.

    This function creates a fresh PyCSP3 model with the given constraints,
    compiles it, and solves it. Results are cached to avoid redundant
    solver calls for the same constraint subsets.

    :param soft: List of soft constraints to include
    :param hard: List of hard constraints (always included)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :param timeout: Optional timeout in seconds
    :param use_cache: Whether to use result caching (default True)
    :return: SolveResult indicating SAT, UNSAT, or UNKNOWN
    """
    # Normalize constraints for cache lookup
    soft_normalized = _normalize_constraints(soft)
    hard_normalized = _normalize_constraints(hard)

    # Check cache first (only if no timeout, as timeout affects results)
    if use_cache and timeout is None:
        cached = _solve_cache.get(soft_normalized, hard_normalized, solver)
        if cached is not None:
            return cached

    result, _ = _solve_subset_internal(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        timeout=timeout,
        extraction=False,
    )

    # Cache the result (only if no timeout)
    if use_cache and timeout is None:
        _solve_cache.put(soft_normalized, hard_normalized, solver, result)

    return result


def solve_subset_with_core(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
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
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
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
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
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
