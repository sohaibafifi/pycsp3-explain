"""
MUS (Minimal Unsatisfiable Subset) algorithms for PyCSP3.

This module provides implementations of:
- mus_naive: Deletion-based MUS using naive re-solving
- quickxplain_naive: Preferred MUS based on constraint ordering

A MUS is a minimal subset of constraints that is unsatisfiable:
- The subset itself is UNSAT
- Removing any constraint from the subset makes it SAT
"""

from typing import List, Any, Optional

from pycsp3_explain.explain.utils import flatten_constraints, order_by_num_variables
from pycsp3_explain.solvers.wrapper import is_sat, is_unsat


def mus_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Minimal Unsatisfiable Subset using deletion-based algorithm.

    This **naive** implementation re-solves the model from scratch for each
    constraint test. For large models, this can be slow.

    Algorithm:
    1. Start with all soft constraints (must be UNSAT)
    2. For each constraint c (ordered by number of variables, descending):
       - Try removing c from the current set
       - If still UNSAT: c is not needed, keep it removed
       - If SAT: c is necessary for unsatisfiability, restore it
    3. Return the remaining constraints (the MUS)

    :param soft: List of soft constraints (candidates for MUS)
    :param hard: List of hard constraints (always included, not in MUS)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :return: A minimal unsatisfiable subset of soft constraints
    :raises AssertionError: If soft + hard is satisfiable
    """
    # Flatten and validate input
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    # Verify the model is UNSAT
    assert is_unsat(soft, hard, solver, verbose), \
        "MUS: model must be UNSAT (soft + hard constraints must be unsatisfiable)"

    # Order constraints: try removing constraints with many variables first
    # (they are more likely to be removable)
    candidates = order_by_num_variables(soft, descending=True)

    mus = []  # constraints confirmed to be in the MUS

    for i, c in enumerate(candidates):
        # Try without constraint c
        remaining = mus + candidates[i + 1:]

        if verbose >= 0:
            print(f"MUS: testing constraint {i + 1}/{len(candidates)}, "
                  f"current MUS size: {len(mus)}")

        if is_sat(remaining, hard, solver, verbose):
            # Removing c makes it SAT, so c must be in the MUS
            mus.append(c)
            if verbose >= 0:
                print(f"  -> constraint is in MUS")
        else:
            # Still UNSAT without c, so c is not needed
            if verbose >= 0:
                print(f"  -> constraint not needed")

    return mus


def quickxplain_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find a preferred MUS based on constraint ordering.

    This algorithm finds a MUS where constraints earlier in the `soft` list
    are preferred over later ones. If multiple MUSes exist, this returns
    one that includes constraints with lower indices when possible.

    Implementation of the QuickXplain algorithm by Junker (2004).

    :param soft: List of soft constraints (order determines preference)
    :param hard: List of hard constraints (always included)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :return: A preferred minimal unsatisfiable subset
    :raises AssertionError: If soft + hard is satisfiable

    Reference:
        Junker, U. "Preferred explanations and relaxations for
        over-constrained problems." AAAI 2004.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    # Verify the model is UNSAT
    assert is_unsat(soft, hard, solver, verbose), \
        "QuickXplain: model must be UNSAT"

    def do_recursion(soft_list: List[Any], hard_list: List[Any], delta: List[Any]) -> List[Any]:
        """
        Recursive QuickXplain procedure.

        :param soft_list: Current soft constraints to analyze
        :param hard_list: Current hard constraints (background)
        :param delta: Constraints added to hard since last check
        :return: Minimal conflict from soft_list
        """
        # If delta is non-empty and hard alone is UNSAT, conflict is in hard
        if delta and is_unsat([], hard_list, solver, verbose):
            return []

        # Base case: only one constraint, it must be in the MUS
        if len(soft_list) == 1:
            return list(soft_list)

        # Split soft constraints
        split = len(soft_list) // 2
        more_preferred = soft_list[:split]  # Earlier = more preferred
        less_preferred = soft_list[split:]

        # Find conflicts from less preferred, treating more preferred as hard
        delta2 = do_recursion(
            less_preferred,
            hard_list + more_preferred,
            more_preferred
        )

        # Find which more preferred constraints are actually needed
        delta1 = do_recursion(
            more_preferred,
            hard_list + delta2,
            delta2
        )

        return delta1 + delta2

    return do_recursion(soft, hard, [])


def is_mus(
    subset: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> bool:
    """
    Verify that a subset is a MUS.

    A valid MUS must be:
    1. UNSAT (with hard constraints)
    2. Minimal: removing any single constraint makes it SAT

    :param subset: The subset to verify
    :param hard: Hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: True if subset is a valid MUS
    """
    subset = flatten_constraints(subset)
    hard = flatten_constraints(hard) if hard else []

    if not subset:
        return False

    # Check UNSAT
    if not is_unsat(subset, hard, solver, verbose):
        if verbose >= 0:
            print("is_mus: subset is SAT, not a MUS")
        return False

    # Check minimality
    for i, c in enumerate(subset):
        reduced = subset[:i] + subset[i + 1:]
        if is_unsat(reduced, hard, solver, verbose):
            if verbose >= 0:
                print(f"is_mus: removing constraint {i} still UNSAT, not minimal")
            return False

    return True


def all_mus_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1,
    max_mus: Optional[int] = None
) -> List[List[Any]]:
    """
    Find all MUSes (up to a maximum count).

    This is a naive implementation that repeatedly finds MUSes and blocks them.
    For complete enumeration, consider using MARCO algorithm.

    WARNING: This can be very slow for models with many MUSes.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :param max_mus: Maximum number of MUSes to find (None for all)
    :return: List of all found MUSes
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    if not is_unsat(soft, hard, solver, verbose):
        return []  # Model is SAT, no MUS

    all_muses = []
    blocked_sets = []  # Sets of constraint indices that have been found

    while True:
        if max_mus is not None and len(all_muses) >= max_mus:
            break

        # Find a MUS avoiding already found ones
        # Use different orderings to find different MUSes
        import random
        shuffled = soft.copy()
        random.shuffle(shuffled)

        mus = mus_naive(shuffled, hard, solver, verbose)

        # Check if this MUS is new
        mus_set = frozenset(id(c) for c in mus)
        if mus_set in blocked_sets:
            # Try with original ordering
            mus = mus_naive(soft, hard, solver, verbose)
            mus_set = frozenset(id(c) for c in mus)

            if mus_set in blocked_sets:
                # No new MUS found
                break

        all_muses.append(mus)
        blocked_sets.append(mus_set)

        if verbose >= 0:
            print(f"Found MUS #{len(all_muses)} with {len(mus)} constraints")

        # Simple termination: if we found a MUS of size 1, we're likely done
        # (this is a heuristic, not complete)
        if len(mus) == 1:
            break

    return all_muses
