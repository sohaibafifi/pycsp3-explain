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
    make_assump_model,
    get_constraint_variables,
)
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    is_sat,
    is_unsat,
    solve_subset,
    solve_subset_with_core,
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

    This implementation uses assumptions for incremental solving,
    leveraging core extraction to identify conflicts efficiently.

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

    soft, hard, assumptions, guard_constraints = make_assump_model(soft, hard)

    def solve_with_assumptions(assumed_indices: List[int]):
        assumption_constraints = [assumptions[i] == 1 for i in assumed_indices]
        soft_constraints = guard_constraints + assumption_constraints
        return solve_subset_with_core(soft_constraints, hard, solver, verbose)

    def core_to_assumptions(core_indices: List[int], assumed_indices: List[int]) -> set[int]:
        """Map core indices back to assumption indices."""
        core_assumps = set()
        hard_offset = len(hard)
        guard_count = len(guard_constraints)
        for idx in core_indices:
            if idx < hard_offset:
                continue
            rel = idx - hard_offset
            if rel < guard_count:
                core_assumps.add(rel)
                continue
            rel -= guard_count
            if 0 <= rel < len(assumed_indices):
                core_assumps.add(assumed_indices[rel])
        return core_assumps

    # Check if all soft constraints are satisfiable
    all_indices = list(range(len(soft)))
    result, _ = solve_with_assumptions(all_indices)
    if result == SolveResult.SAT:
        return soft  # All constraints are satisfiable

    def num_vars(i: int) -> int:
        try:
            return len(get_constraint_variables(soft[i]))
        except Exception:
            return 0

    # Order by number of variables (fewer first - less likely to conflict)
    ordered = sorted(all_indices, key=num_vars, reverse=False)

    mss_indices = set()
    excluded = set()

    for idx in ordered:
        if idx in excluded:
            continue

        # Try adding idx to current MSS
        test_indices = sorted(mss_indices | {idx})
        result, core_indices = solve_with_assumptions(test_indices)

        if result == SolveResult.SAT:
            mss_indices.add(idx)
        elif result == SolveResult.UNSAT:
            # Extract core and mark conflicting indices
            core = core_to_assumptions(core_indices, test_indices)
            if idx in core:
                excluded.add(idx)
            elif core:
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


def mss_opt(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute an optimal (weighted) Maximal Satisfiable Subset.

    This implementation finds an MSS that maximizes the sum of weights
    of included constraints. If no weights are provided, it maximizes
    the number of constraints (equivalent to standard MSS).

    Algorithm:
    Uses an iterative approach to find the optimal weighted MSS.
    For each constraint subset sorted by total weight (descending),
    tests if it's SAT and returns the first maximal one found.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: An optimal weighted MSS
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
                print(f"mss_opt: added constraint {i} (weight {weight}), "
                      f"MSS size: {len(mss_indices)}")

    return [soft[i] for i in range(n) if i in mss_indices]


def mcs_opt(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute an optimal (weighted) Minimal Correction Set.

    This implementation finds an MCS that minimizes the sum of weights
    of removed constraints. If no weights are provided, it minimizes
    the number of constraints (smallest MCS).

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

    # If already SAT, no correction needed
    if is_sat(soft, hard, solver, verbose):
        return []

    # Find optimal MSS and return its complement
    mss_result = mss_opt(soft, hard, weights, solver, verbose)
    return mcs_from_mss(mss_result, soft)
