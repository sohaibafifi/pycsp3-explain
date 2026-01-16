"""
MARCO algorithm for MUS/MCS enumeration.

This module provides an implementation of the MARCO algorithm for
enumerating all Minimal Unsatisfiable Subsets (MUSes) and Minimal
Correction Sets (MCSes) of an unsatisfiable constraint model.

Based on:
    Liffiton, Mark H., et al. "Fast, flexible MUS enumeration."
    Constraints 21 (2016): 223-250.

Algorithm Overview (from the paper):
    MARCO uses two solvers:
    1. A "map solver" that tracks which subsets have been explored using blocking clauses
    2. A "constraint solver" that tests satisfiability of candidate subsets

    The map solver uses Boolean selector variables s_i for each soft constraint i:
    - s_i = True means constraint i is in the current subset
    - s_i = False means constraint i is not in the current subset

    Blocking clauses ensure completeness without redundant exploration:
    - MUS blocking: For MUS {i1, ..., ik}, add clause (¬s_i1 ∨ ... ∨ ¬s_ik)
      This prevents exploring any SUPERSET of the MUS (all supersets are UNSAT)
    - MSS blocking: For MSS with complement (MCS) {l1, ..., ln}, add clause (s_l1 ∨ ... ∨ s_ln)
      This prevents exploring any SUBSET of the MSS (all subsets are SAT)

    Main loop:
    while map_solver.solve():
        seed = current_assignment
        if constraint_solver.is_sat(seed):
            mss = grow(seed)  # Grow to maximal satisfiable subset
            yield ("MCS", complement(mss))
            block_down(mss)  # Block subsets
        else:
            mus = shrink(seed)  # Shrink to minimal unsatisfiable subset
            yield ("MUS", mus)
            block_up(mus)  # Block supersets
"""

from typing import List, Any, Optional, Iterator, Tuple, Literal, Set, Dict, FrozenSet

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


class MapSolver:
    """
    A SAT-based map solver for MARCO algorithm.

    Maintains blocking clauses in CNF form and generates unexplored seeds
    using a simple DPLL-style backtracking search.

    The map solver uses Boolean selector variables s_i where:
    - s_i = True (positive literal i) means constraint i is in the subset
    - s_i = False (negative literal -i-1) means constraint i is not in the subset

    Blocking clauses are stored as sets of literals (integers):
    - Positive integer i means s_i must be True
    - Negative integer -(i+1) means s_i must be False
    - A clause is satisfied if at least one literal is satisfied

    Example:
        - MUS {0, 2}: block clause {-1, -3} meaning (¬s_0 ∨ ¬s_2)
        - MCS {1}: block clause {1} meaning (s_1)

    Attributes:
        n: Number of soft constraints
        clauses: List of blocking clauses (each clause is a frozenset of literals)
    """

    def __init__(self, n: int) -> None:
        """
        Initialize the map solver.

        :param n: Number of soft constraints (selector variables)
        """
        self.n = n
        self.clauses: List[FrozenSet[int]] = []

    def block_up(self, mus_indices: Set[int]) -> None:
        """
        Add a clause to block all supersets of a MUS.

        For MUS {i1, ..., ik}, adds clause (¬s_i1 ∨ ... ∨ ¬s_ik).
        This ensures no superset of the MUS will be explored.

        :param mus_indices: Set of constraint indices in the MUS
        """
        # Clause: at least one of the MUS constraints must be False
        # Represented as negative literals: -(i+1) for each i in MUS
        clause = frozenset(-(i + 1) for i in mus_indices)
        self.clauses.append(clause)

    def block_down(self, mss_indices: Set[int]) -> None:
        """
        Add a clause to block all subsets of an MSS.

        For MSS with complement (MCS) {l1, ..., ln}, adds clause (s_l1 ∨ ... ∨ s_ln).
        This ensures no subset of the MSS will be explored.

        :param mss_indices: Set of constraint indices in the MSS
        """
        # MCS = complement of MSS
        mcs_indices = set(range(self.n)) - mss_indices
        if not mcs_indices:
            # MSS contains all constraints, no subset to block
            # Add an empty clause to make the formula unsatisfiable
            self.clauses.append(frozenset())
        else:
            # Clause: at least one MCS constraint must be True
            # Represented as positive literals: i for each i in MCS
            clause = frozenset(mcs_indices)
            self.clauses.append(clause)

    def _to_positive(self, lit: int) -> int:
        """Convert a literal to its variable index."""
        return lit if lit >= 0 else -(lit + 1)

    def _is_positive(self, lit: int) -> bool:
        """Check if a literal is positive."""
        return lit >= 0

    def solve(self) -> Optional[Set[int]]:
        """
        Find a satisfying assignment (unexplored seed) using DPLL.

        :return: Set of constraint indices to include, or None if no seed exists
        """
        return self._dpll(set(), set(), 0)

    def _dpll(
        self,
        true_vars: Set[int],
        false_vars: Set[int],
        next_var: int
    ) -> Optional[Set[int]]:
        """
        DPLL algorithm with unit propagation.

        :param true_vars: Variables assigned True
        :param false_vars: Variables assigned False
        :param next_var: Next variable to branch on
        :return: Satisfying assignment or None
        """
        # Unit propagation
        true_vars = set(true_vars)
        false_vars = set(false_vars)

        changed = True
        while changed:
            changed = False
            for clause in self.clauses:
                # Check if clause is already satisfied
                satisfied = False
                unassigned_lits = []
                for lit in clause:
                    var = self._to_positive(lit)
                    is_pos = self._is_positive(lit)
                    if var in true_vars:
                        if is_pos:
                            satisfied = True
                            break
                    elif var in false_vars:
                        if not is_pos:
                            satisfied = True
                            break
                    else:
                        unassigned_lits.append(lit)

                if satisfied:
                    continue

                if not unassigned_lits:
                    # All literals falsified - conflict
                    return None

                if len(unassigned_lits) == 1:
                    # Unit clause - must satisfy this literal
                    lit = unassigned_lits[0]
                    var = self._to_positive(lit)
                    is_pos = self._is_positive(lit)
                    if is_pos:
                        if var in false_vars:
                            return None  # Conflict
                        if var not in true_vars:
                            true_vars.add(var)
                            changed = True
                    else:
                        if var in true_vars:
                            return None  # Conflict
                        if var not in false_vars:
                            false_vars.add(var)
                            changed = True

        # Find next unassigned variable
        while next_var < self.n and (next_var in true_vars or next_var in false_vars):
            next_var += 1

        if next_var >= self.n:
            # All variables assigned - check if all clauses satisfied
            all_satisfied = True
            for clause in self.clauses:
                satisfied = False
                for lit in clause:
                    var = self._to_positive(lit)
                    is_pos = self._is_positive(lit)
                    if is_pos and var in true_vars:
                        satisfied = True
                        break
                    if not is_pos and var in false_vars:
                        satisfied = True
                        break
                if not satisfied:
                    all_satisfied = False
                    break

            if all_satisfied:
                return true_vars
            else:
                return None

        # Try True first (include more constraints - likely UNSAT, find MUS faster)
        result = self._dpll(true_vars | {next_var}, false_vars, next_var + 1)
        if result is not None:
            return result

        # Try False
        return self._dpll(true_vars, false_vars | {next_var}, next_var + 1)


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

    Algorithm (Liffiton et al., 2016):
    1. Use a "map solver" (SAT-based) to generate candidate subsets (seeds)
    2. For each seed:
       - If SAT: grow to MSS, compute MCS = complement, block down (subsets)
       - If UNSAT: shrink to MUS, block up (supersets)
    3. Repeat until map solver returns UNSAT (no more unexplored subsets)

    The map solver uses blocking clauses to ensure:
    - No superset of a discovered MUS is generated (all would be UNSAT)
    - No subset of a discovered MSS is generated (all would be SAT)

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
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return

    n = len(soft)

    # Initialize map solver for tracking explored subsets
    map_solver = MapSolver(n)

    def is_sat_subset(indices: Set[int]) -> bool:
        """Check if the subset of soft constraints is SAT."""
        subset = [soft[i] for i in indices]
        return is_sat(subset, hard, solver, verbose)

    def shrink_to_mus(seed_indices: Set[int]) -> Set[int]:
        """
        Shrink an UNSAT seed to a MUS using deletion-based algorithm.

        Iteratively removes constraints and checks if still UNSAT.
        If removing a constraint makes it SAT, that constraint is necessary.
        """
        mus = set(seed_indices)

        # Sort by number of variables (more vars first -> remove first)
        # This heuristic often leads to faster shrinking
        def num_vars(i: int) -> int:
            try:
                return len(get_constraint_variables(soft[i]))
            except (AttributeError, TypeError, ValueError):
                return 0

        ordered = sorted(mus, key=num_vars, reverse=True)

        for idx in ordered:
            if idx not in mus:
                continue
            mus.remove(idx)
            if not mus or is_sat_subset(mus):
                # Constraint is necessary for UNSAT
                mus.add(idx)

        return mus

    def grow_to_mss(seed_indices: Set[int]) -> Set[int]:
        """
        Grow a SAT seed to an MSS by adding constraints greedily.

        Tries to add each constraint not in seed; keeps it if result is still SAT.
        """
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

        # Get next unexplored seed from map solver
        seed_set = map_solver.solve()
        if seed_set is None:
            # No more unexplored subsets - enumeration complete
            if verbose >= 0:
                print(f"MARCO: enumeration complete after {iteration - 1} iterations")
            break

        if verbose >= 0:
            print(f"MARCO: iteration {iteration}, seed size {len(seed_set)}")

        if is_sat_subset(seed_set):
            # SAT: grow to MSS, block down (subsets)
            mss_set = grow_to_mss(seed_set)
            map_solver.block_down(mss_set)

            # MCS = complement of MSS
            mcs_set = set(range(n)) - mss_set

            if verbose >= 0:
                print(f"MARCO: found MSS of size {len(mss_set)}, MCS of size {len(mcs_set)}")

            if return_mcs and mcs_set:
                yield ("MCS", [soft[i] for i in sorted(mcs_set)])

        else:
            # UNSAT: shrink to MUS, block up (supersets)
            mus_set = shrink_to_mus(seed_set)
            map_solver.block_up(mus_set)

            if verbose >= 0:
                print(f"MARCO: found MUS of size {len(mus_set)}")

            if return_mus and mus_set:
                yield ("MUS", [soft[i] for i in sorted(mus_set)])


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
