"""
MSS (Maximal Satisfiable Subset) algorithms for PyCSP3.

This module provides implementations of:
- mss_naive: Greedy growing MSS using naive re-solving
- mss: Assumption-based MSS using incremental solving
- mss_opt: Weighted MSS optimization
- mcs_opt: Weighted MCS optimization

An MSS is a maximal subset of constraints that is satisfiable:
- The subset itself is SAT
- Adding any other constraint from the remaining set makes it UNSAT

Note: MCS (Minimal Correction Set) = Soft \\ MSS
"""

from typing import List, Any, Optional, Union

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    order_by_num_variables,
    get_constraint_variables,
)
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    is_sat,
    _AssumptionSolveSession,
)


def mss_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Maximal Satisfiable Subset using greedy growing algorithm.

    This **naive** implementation re-solves the model from scratch for each
    constraint test. For large models, this can be slow.

    Algorithm:
    1. Start with an empty set (or hard constraints only)
    2. For each constraint c (ordered by number of variables, ascending):
       - Try adding c to the current MSS
       - If still SAT: add c to MSS
       - If UNSAT: skip c (it conflicts with current MSS)
    3. Return the MSS

    :param soft: List of soft constraints (candidates for MSS)
    :param hard: List of hard constraints (always included, not in MSS)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :return: A maximal satisfiable subset of soft constraints
    """
    # Flatten and validate input
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    # If all soft + hard is SAT, return all soft constraints
    if is_sat(soft, hard, solver, verbose):
        return soft

    # Order constraints: try adding constraints with fewer variables first
    # (they are less likely to cause conflicts)
    candidates = order_by_num_variables(soft, descending=False)

    mss = []  # constraints confirmed to be in the MSS

    for i, c in enumerate(candidates):
        if verbose >= 0:
            print(f"MSS: testing constraint {i + 1}/{len(candidates)}, "
                  f"current MSS size: {len(mss)}")

        # Try adding constraint c to current MSS
        if is_sat(mss + [c], hard, solver, verbose):
            # Adding c keeps it SAT, so include c in MSS
            mss.append(c)
            if verbose >= 0:
                print(f"  -> constraint added to MSS")
        else:
            # Adding c makes it UNSAT, skip it
            if verbose >= 0:
                print(f"  -> constraint conflicts, skipping")

    return mss


def mss(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Maximal Satisfiable Subset using assumption indicators.

    This implementation uses assumptions for incremental solving, and reuses one posted assumption model:
    - hard constraints and guard implications are posted once,
    - each subset check only posts/unposts fixing constraints.

    :param soft: List of soft constraints (candidates for MSS)
    :param hard: List of hard constraints (always included, not in MSS)
    :param solver: Solver name ("ace" only for core extraction)
    :param verbose: Verbosity level (-1 for silent)
    :return: A maximal satisfiable subset of soft constraints
    """
    if solver.lower() != "ace":
        if verbose >= 0:
            print("mss: solver does not support core extraction, using mss_naive")
        return mss_naive(soft, hard, solver, verbose)

    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    def num_vars(i: int) -> int:
        try:
            return len(get_constraint_variables(soft[i]))
        except Exception:
            return 0

    with _AssumptionSolveSession(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        name_prefix="mss_assump",
    ) as session:
        all_indices = list(range(len(soft)))
        result, _ = session.solve(all_indices, extract_core=False)
        if result == SolveResult.SAT:
            return soft  # All constraints are satisfiable

        # Order by number of variables (fewer first - less likely to conflict)
        ordered = sorted(all_indices, key=num_vars, reverse=False)

        mss_indices = set()
        excluded = set()

        for idx in ordered:
            if idx in excluded:
                continue

            # Try adding idx to current MSS
            test_indices = sorted(mss_indices | {idx})
            result, core = session.solve(test_indices, extract_core=True)

            if result == SolveResult.SAT:
                mss_indices.add(idx)
            elif result == SolveResult.UNSAT:
                core_set = set(core)
                if idx in core_set:
                    excluded.add(idx)
                elif core_set:
                    # Core doesn't contain idx, but something in mss_indices
                    # This shouldn't happen if we're growing correctly, but handle it
                    excluded.add(idx)
            else:
                # UNKNOWN/ERROR - fall back to naive check
                if is_sat(
                    [soft[i] for i in mss_indices] + [soft[idx]],
                    hard, solver, verbose
                ):
                    mss_indices.add(idx)
                else:
                    excluded.add(idx)

        return [soft[i] for i in range(len(soft)) if i in mss_indices]


def is_mss(
    subset: List[Any],
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> bool:
    """
    Verify that a subset is an MSS (Maximal Satisfiable Subset).

    A valid MSS must be:
    1. SAT (with hard constraints)
    2. Maximal: adding any constraint from soft \\ subset makes it UNSAT

    :param subset: The subset to verify
    :param soft: The full set of soft constraints
    :param hard: Hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: True if subset is a valid MSS
    """
    subset = flatten_constraints(subset)
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    # Check SAT
    if not is_sat(subset, hard, solver, verbose):
        if verbose >= 0:
            print("is_mss: subset is UNSAT, not an MSS")
        return False

    # Check maximality - adding any constraint from soft \ subset should make it UNSAT
    subset_ids = set(id(c) for c in subset)
    remaining = [c for c in soft if id(c) not in subset_ids]

    for c in remaining:
        if is_sat(subset + [c], hard, solver, verbose):
            if verbose >= 0:
                print("is_mss: can add more constraints, not maximal")
            return False

    return True


def mcs_from_mss(
    mss: List[Any],
    soft: List[Any]
) -> List[Any]:
    """
    Compute the MCS (Minimal Correction Set) from an MSS.

    MCS = soft \\ MSS (the complement of MSS relative to soft constraints)

    :param mss: A maximal satisfiable subset
    :param soft: The full set of soft constraints
    :return: The minimal correction set (constraints to remove to restore SAT)
    """
    mss_ids = set(id(c) for c in mss)
    return [c for c in soft if id(c) not in mss_ids]


def mcs_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Minimal Correction Set via MSS complement.

    An MCS is the complement of an MSS: the minimal set of constraints
    that must be removed to make the remaining constraints satisfiable.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: A minimal correction set
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    # If already SAT, no correction needed
    if is_sat(soft, hard, solver, verbose):
        return []

    # Find MSS and return its complement
    mss_result = mss_naive(soft, hard, solver, verbose)
    return mcs_from_mss(mss_result, soft)


def mcs(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Minimal Correction Set using assumption-based MSS.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: A minimal correction set
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    # If already SAT, no correction needed
    if is_sat(soft, hard, solver, verbose):
        return []

    # Find MSS and return its complement
    mss_result = mss(soft, hard, solver, verbose)
    return mcs_from_mss(mss_result, soft)


def is_mcs(
    subset: List[Any],
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> bool:
    """
    Verify that a subset is an MCS (Minimal Correction Set).

    A valid MCS must be:
    1. Its complement (soft \\ subset) must be SAT
    2. Minimal: removing any constraint from subset makes the complement UNSAT

    :param subset: The subset to verify as MCS
    :param soft: The full set of soft constraints
    :param hard: Hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: True if subset is a valid MCS
    """
    subset = flatten_constraints(subset)
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    # Compute complement
    subset_ids = set(id(c) for c in subset)
    complement = [c for c in soft if id(c) not in subset_ids]

    # Check that complement is SAT
    if not is_sat(complement, hard, solver, verbose):
        if verbose >= 0:
            print("is_mcs: complement is UNSAT, not a valid MCS")
        return False

    # Check minimality: removing any constraint from MCS makes complement UNSAT
    for i, c in enumerate(subset):
        reduced_mcs = subset[:i] + subset[i + 1:]
        reduced_mcs_ids = set(id(x) for x in reduced_mcs)
        new_complement = [x for x in soft if id(x) not in reduced_mcs_ids]

        if is_sat(new_complement, hard, solver, verbose):
            if verbose >= 0:
                print(f"is_mcs: removing constraint {i} still gives SAT complement, not minimal")
            return False

    return True


def _solve_weighted_mss_exact(
    soft: List[Any],
    hard: List[Any],
    weights: Optional[List[Union[int, float]]],
    solver: str,
    verbose: int,
) -> List[Any]:
    """
    Solve weighted MSS exactly with a single optimization model.

    The objective is lexicographic:
    1. Maximize total selected weight.
    2. Break ties by maximizing number of selected constraints.
    """
    from pycsp3 import (
        VarArray,
        imply,
        satisfy,
        maximize,
        Sum,
        solve,
        value,
        ACE,
        CHOCO,
        SAT,
        OPTIMUM,
        UNSAT,
    )
    from pycsp3.classes.entities import CtrEntities, ObjEntities, AnnEntities
    from pycsp3.compiler import Compilation
    from pycsp3.dashboard import options as pycsp3_options
    from pycsp3.tools.utilities import integer_scaling
    import os
    import tempfile
    import uuid

    if not soft:
        return []

    n = len(soft)
    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")
    if any(weight < 0 for weight in w):
        raise ValueError("weights must be non-negative")

    # Scale float weights to integers for CP objective terms.
    if any(isinstance(weight, float) and not weight.is_integer() for weight in w):
        scaled_w = integer_scaling(w)
    else:
        scaled_w = [int(weight) for weight in w]

    # Preserve variable state and only reset posted constraints/objectives.
    saved_ctr_items = CtrEntities.items[:]
    saved_obj_items = ObjEntities.items[:]
    saved_ann_items = AnnEntities.items[:]
    saved_ann_types = AnnEntities.items_types[:] if hasattr(AnnEntities, "items_types") else []
    saved_compilation_done = Compilation.done
    saved_compilation_model = Compilation.model
    saved_compilation_string_model = Compilation.string_model

    selected_indices: Optional[List[int]] = None
    status = None

    solver_type = ACE if solver.lower() == "ace" else CHOCO
    temp_filename = os.path.join(
        tempfile.gettempdir(),
        f"pycsp3_explain_mss_opt_{uuid.uuid4().hex}.xml",
    )
    prev_compactor = pycsp3_options.dontruncompactor

    try:
        pycsp3_options.dontruncompactor = True

        Compilation.done = False
        Compilation.model = None
        Compilation.string_model = None

        CtrEntities.items = []
        ObjEntities.items = []
        AnnEntities.items = []
        if hasattr(AnnEntities, "items_types"):
            AnnEntities.items_types = []

        select = VarArray(size=n, dom=range(2), id=f"mss_sel_{uuid.uuid4().hex[:8]}")

        if hard:
            satisfy(hard)
        satisfy([imply(select[i], soft[i]) for i in range(n)])

        tie_multiplier = n + 1
        maximize(Sum(select[i] * (scaled_w[i] * tie_multiplier + 1) for i in range(n)))

        status = solve(solver=solver_type, verbose=verbose, filename=temp_filename)

        if status in (SAT, OPTIMUM):
            selected_indices = [i for i in range(n) if value(select[i]) == 1]
        elif status == UNSAT:
            selected_indices = []
    except Exception as exc:
        if verbose >= 0:
            print(f"mss_opt: exact solve failed ({exc}), falling back to heuristic")
        return mss_heuristic(soft, hard, w, solver, verbose)
    finally:
        pycsp3_options.dontruncompactor = prev_compactor
        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except OSError:
            pass

        CtrEntities.items = saved_ctr_items
        ObjEntities.items = saved_obj_items
        AnnEntities.items = saved_ann_items
        if hasattr(AnnEntities, "items_types"):
            AnnEntities.items_types = saved_ann_types

        Compilation.done = saved_compilation_done
        Compilation.model = saved_compilation_model
        Compilation.string_model = saved_compilation_string_model

    if selected_indices is not None:
        return [soft[i] for i in selected_indices]

    if verbose >= 0:
        print(f"mss_opt: exact solve returned {status}, falling back to heuristic")
    return mss_heuristic(soft, hard, w, solver, verbose)


def mss_opt(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute an optimal (weighted) Maximal Satisfiable Subset.

    This implementation builds and solves one optimization model:
    - Decision variables select which soft constraints are enabled.
    - Guard constraints enforce that selected constraints must hold.
    - Objective maximizes total selected weight.
    - Ties are broken by selecting more constraints.


    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: An optimal weighted MSS
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []
    return _solve_weighted_mss_exact(soft, hard, weights, solver, verbose)


def mcs_opt(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute an optimal (weighted) Minimal Correction Set.

    This implementation derives MCS from the exact weighted MSS:
    MCS = soft \\ MSS_opt.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: An optimal weighted MCS
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    # Find optimal MSS and return its complement
    mss_result = mss_opt(soft, hard, weights, solver, verbose)
    return mcs_from_mss(mss_result, soft)


def mss_heuristic(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a weighted Maximal Satisfiable Subset using greedy heuristics.

    This implementation uses a GREEDY approach that prioritizes high-weight
    constraints. It is NOT guaranteed to find the globally optimal MSS
    (the one with maximum total weight). For true optimality, an ILP-based
    or branch-and-bound approach would be needed.

    Algorithm:
    1. Sort constraints by weight (descending)
    2. Greedily add constraints if they don't cause unsatisfiability
    3. Return the resulting MSS

    The greedy approach works well in practice but may miss the optimal
    solution when there are complex interactions between constraints.

    Example where greedy fails:
    - Constraints: A (weight=5), B (weight=4), C (weight=4)
    - A conflicts with both B and C, but B and C are compatible
    - Greedy picks A (total=5), missing {B,C} (total=8)

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: A weighted MSS (may not be globally optimal)
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    n = len(soft)

    # Default weights: all 1s
    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")
    if any(weight < 0 for weight in w):
        raise ValueError("weights must be non-negative")

    # If all constraints are SAT, return all
    if is_sat(soft, hard, solver, verbose):
        return soft

    # Greedy approach: order by weight (higher weight first)
    # Try to include high-weight constraints first
    indexed_constraints = [(i, soft[i], w[i]) for i in range(n)]
    indexed_constraints.sort(key=lambda x: -x[2])  # Sort by weight descending

    mss_indices: set = set()

    for i, c, weight in indexed_constraints:
        # Try adding constraint to current MSS
        test_subset = [soft[j] for j in mss_indices] + [c]
        if is_sat(test_subset, hard, solver, verbose):
            mss_indices.add(i)
            if verbose >= 0:
                print(f"mss_heuristic: added constraint {i} (weight {weight}), "
                      f"MSS size: {len(mss_indices)}")

    return [soft[i] for i in range(n) if i in mss_indices]


def mcs_heuristic(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a weighted Minimal Correction Set using greedy heuristics.

    This implementation finds an MCS by computing the complement of a
    greedy weighted MSS. Since the underlying MSS computation is greedy,
    the resulting MCS is NOT guaranteed to be globally optimal (minimum
    total weight of removed constraints).

    The greedy approach works well in practice but may not find the
    true minimum-weight correction set.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: A weighted MCS (may not be globally optimal)
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    n = len(soft)
    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")
    if any(weight < 0 for weight in w):
        raise ValueError("weights must be non-negative")

    # If already SAT, no correction needed
    if is_sat(soft, hard, solver, verbose):
        return []

    # Find heuristic MSS and return its complement
    mss_result = mss_heuristic(soft, hard, w, solver, verbose)
    return mcs_from_mss(mss_result, soft)
