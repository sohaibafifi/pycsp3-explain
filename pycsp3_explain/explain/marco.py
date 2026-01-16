"""
MARCO algorithm for MUS/MCS enumeration.

This module provides an implementation of the MARCO algorithm for
enumerating all Minimal Unsatisfiable Subsets (MUSes) and Minimal
Correction Sets (MCSes) of an unsatisfiable constraint model.

Based on:
    Liffiton, Mark H., et al. "Fast, flexible MUS enumeration."
    Constraints 21 (2016): 223-250.
"""

from typing import List, Any, Optional, Iterator, Tuple, Literal, Set, Dict

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    make_assump_model,
    get_constraint_variables,
    Constraint,
    ConstraintList,
)
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    is_sat,
    is_unsat,
    solve_subset,
    solve_subset_with_core,
)

# Default maximum iterations for MARCO enumeration to prevent infinite loops
DEFAULT_MAX_MARCO_ITERATIONS = 1000


def marco(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    return_mus: bool = True,
    return_mcs: bool = True,
    verbose: int = -1,
    max_iterations: int = DEFAULT_MAX_MARCO_ITERATIONS,
) -> Iterator[Tuple[Literal["MUS", "MCS"], ConstraintList]]:
    """
    Enumerate all MUSes and MCSes using the MARCO algorithm.

    This is a generator that yields tuples of ("MUS", subset) or ("MCS", subset)
    as they are discovered. The enumeration is complete when the generator is
    exhausted.

    Algorithm:
    1. Use a "map solver" to generate candidate subsets (seeds)
    2. For each seed:
       - If SAT: grow to MSS, compute MCS = complement, block MCS
       - If UNSAT: shrink to MUS, block MUS
    3. Repeat until no more seeds can be generated

    The map solver ensures:
    - No superset of a discovered MUS is generated as a seed
    - No subset of a discovered MCS is generated as a seed

    :param soft: List of soft constraints to enumerate MUSes/MCSes of
    :param hard: List of hard constraints (always included, not in MUS/MCS)
    :param solver: Solver name ("ace" for best performance)
    :param return_mus: Whether to yield MUSes (default True)
    :param return_mcs: Whether to yield MCSes (default True)
    :param verbose: Verbosity level (-1 for silent)
    :param max_iterations: Maximum iterations before stopping (safety limit)
    :yields: Tuples of ("MUS", subset) or ("MCS", subset)

    Example:
        >>> for result_type, subset in marco(soft_constraints, hard_constraints):
        ...     if result_type == "MUS":
        ...         print(f"Found MUS with {len(subset)} constraints")
        ...     else:
        ...         print(f"Found MCS with {len(subset)} constraints")
    """
    # Delegate to naive implementation for now
    yield from marco_naive(soft, hard, solver, return_mus, return_mcs, verbose, max_iterations)


def marco_naive(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    return_mus: bool = True,
    return_mcs: bool = True,
    verbose: int = -1,
    max_iterations: int = DEFAULT_MAX_MARCO_ITERATIONS,
) -> Iterator[Tuple[Literal["MUS", "MCS"], ConstraintList]]:
    """
    Naive MARCO implementation without assumption variables.

    This version re-solves the model from scratch for each test.
    Use this when the solver doesn't support core extraction.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param return_mus: Whether to yield MUSes
    :param return_mcs: Whether to yield MCSes
    :param verbose: Verbosity level
    :param max_iterations: Maximum iterations before stopping (safety limit)
    :yields: Tuples of ("MUS", subset) or ("MCS", subset)
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return

    n = len(soft)

    def is_sat_subset(indices: Set[int]) -> bool:
        """Check if the subset of soft constraints is SAT."""
        subset = [soft[i] for i in indices]
        return is_sat(subset, hard, solver, verbose)

    # State for map solver simulation
    blocked_mus_sets: List[Set[int]] = []  # MUS sets - no superset explored
    blocked_mss_sets: List[Set[int]] = []  # MSS sets - no subset explored

    def get_next_seed() -> Optional[Set[int]]:
        """
        Get next unexplored seed using an efficient search strategy.

        The seed must:
        1. Not be a superset of any discovered MUS
        2. Not be a subset of any discovered MSS

        Algorithm:
        - Start with middle cardinality to balance between SAT/UNSAT likelihood
        - Use targeted element removal/addition based on blocking constraints
        - Avoid exponential DFS by limiting exploration
        """
        all_indices = set(range(n))

        def is_blocked(candidate: Set[int]) -> bool:
            """Check if a candidate is blocked by MUS or MSS constraints."""
            # Blocked if superset of any MUS (would be UNSAT and not minimal)
            if any(mus_set <= candidate for mus_set in blocked_mus_sets):
                return True
            # Blocked if subset of any MSS (would be SAT and not maximal)
            if any(candidate <= mss_set for mss_set in blocked_mss_sets):
                return True
            return False

        # Strategy 1: Try full set first
        if not is_blocked(all_indices):
            return all_indices

        # Strategy 2: Try removing one element from each blocking MUS
        for mus_set in blocked_mus_sets:
            # Find an element in the MUS to remove
            for elem in mus_set:
                candidate = all_indices - {elem}
                if not is_blocked(candidate):
                    return candidate

        # Strategy 3: Try adding one element to each blocking MSS
        for mss_set in blocked_mss_sets:
            remaining = all_indices - mss_set
            for elem in remaining:
                candidate = mss_set | {elem}
                if not is_blocked(candidate):
                    return candidate

        # Strategy 4: Try middle cardinalities
        # This helps find seeds when we have both MUS and MSS constraints
        for target_size in range(n // 2, 0, -1):
            # Build candidate by starting from all and removing elements
            candidate = set(all_indices)

            # Remove elements that appear in many MUSes first
            mus_counts: Dict[int, int] = {}
            for mus_set in blocked_mus_sets:
                for elem in mus_set:
                    mus_counts[elem] = mus_counts.get(elem, 0) + 1

            # Sort by MUS membership count (descending) to remove most problematic first
            sorted_by_mus = sorted(all_indices, key=lambda x: -mus_counts.get(x, 0))

            for elem in sorted_by_mus:
                if len(candidate) <= target_size:
                    break
                candidate.remove(elem)

            if candidate and not is_blocked(candidate):
                return candidate

        # Strategy 5: Try individual constraints
        for i in all_indices:
            candidate = {i}
            if not is_blocked(candidate):
                return candidate

        # No valid seed found - enumeration complete
        return None

    def shrink_to_mus(seed_indices: Set[int]) -> Set[int]:
        """Shrink an UNSAT seed to a MUS using deletion."""
        mus = set(seed_indices)
        
        # Sort by number of variables (more vars first -> remove first)
        def num_vars(i: int) -> int:
            try:
                return len(get_constraint_variables(soft[i]))
            except Exception:
                return 0
        
        ordered = sorted(mus, key=num_vars, reverse=True)
        
        for idx in ordered:
            if idx not in mus:
                continue
            mus.remove(idx)
            if not mus or is_sat_subset(mus):
                mus.add(idx)
        
        return mus

    def grow_to_mss(seed_indices: Set[int]) -> Set[int]:
        """Grow a SAT seed to an MSS."""
        mss = set(seed_indices)
        
        for i in range(n):
            if i in mss:
                continue
            if is_sat_subset(mss | {i}):
                mss.add(i)
        
        return mss

    # Main MARCO loop
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        
        seed_set = get_next_seed()
        if seed_set is None:
            break  # No more seeds, enumeration complete

        if verbose >= 0:
            print(f"MARCO: iteration {iteration}, seed size {len(seed_set)}")

        if is_sat_subset(seed_set):
            # SAT: grow to MSS
            mss_set = grow_to_mss(seed_set)
            blocked_mss_sets.append(mss_set)
            
            # MCS = complement of MSS
            mcs_set = set(range(n)) - mss_set
            
            if return_mcs and mcs_set:
                yield ("MCS", [soft[i] for i in sorted(mcs_set)])

        else:
            # UNSAT: shrink to MUS
            mus_set = shrink_to_mus(seed_set)
            blocked_mus_sets.append(mus_set)
            
            if return_mus and mus_set:
                yield ("MUS", [soft[i] for i in sorted(mus_set)])


def all_mus(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    max_mus: Optional[int] = None,
    verbose: int = -1
) -> List[ConstraintList]:
    """
    Find all MUSes using the MARCO algorithm.

    This is a convenience function that collects all MUSes from MARCO.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param max_mus: Maximum number of MUSes to find (None for all)
    :param verbose: Verbosity level
    :return: List of all found MUSes
    """
    muses: List[ConstraintList] = []
    for result_type, subset in marco(soft, hard, solver, return_mus=True, return_mcs=False, verbose=verbose):
        if result_type == "MUS":
            muses.append(subset)
            if max_mus is not None and len(muses) >= max_mus:
                break
    return muses


def all_mcs(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    max_mcs: Optional[int] = None,
    verbose: int = -1
) -> List[ConstraintList]:
    """
    Find all MCSes using the MARCO algorithm.

    This is a convenience function that collects all MCSes from MARCO.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param max_mcs: Maximum number of MCSes to find (None for all)
    :param verbose: Verbosity level
    :return: List of all found MCSes
    """
    mcses: List[ConstraintList] = []
    for result_type, subset in marco(soft, hard, solver, return_mus=False, return_mcs=True, verbose=verbose):
        if result_type == "MCS":
            mcses.append(subset)
            if max_mcs is not None and len(mcses) >= max_mcs:
                break
    return mcses
