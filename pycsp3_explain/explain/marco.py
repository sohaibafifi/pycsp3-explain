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
    _AssumptionSolveSession,
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

    This implementation uses a single reusable assumption session across all
    iterations, and leverages core extraction for efficient MUS shrinking
    (core-guided deletion with clause-set refinement).

    Algorithm (Liffiton et al., 2016):
    1. Use a "map solver" (SAT-based) to generate candidate subsets (seeds)
    2. For each seed:
       - If SAT: grow to MSS via assumption-based incremental solving,
         compute MCS = complement, block down (subsets)
       - If UNSAT: extract core, shrink to MUS via core-guided deletion
         with clause-set refinement, block up (supersets)
    3. Repeat until map solver returns UNSAT (no more unexplored subsets)

    :param soft: List of soft constraints to enumerate MUSes/MCSes of
    :param hard: List of hard constraints (always included, not in MUS/MCS)
    :param solver: Solver name ("ace" for best performance)
    :param return_mus: Whether to yield MUSes (default True)
    :param return_mcs: Whether to yield MCSes (default True)
    :param verbose: Verbosity level (-1 for silent)
    :param max_iterations: Maximum iterations before stopping (safety limit)
    :yields: Tuples of ("MUS", subset) or ("MCS", subset)
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return

    n = len(soft)
    use_core = solver.lower() == "ace"

    # Initialize map solver for tracking explored subsets
    map_solver = MapSolver(n)

    # Heuristic ordering for shrinking: remove high-arity constraints first
    def num_vars(i: int) -> int:
        try:
            return len(get_constraint_variables(soft[i]))
        except (AttributeError, TypeError, ValueError):
            return 0

    deletion_order = {i: -num_vars(i) for i in range(n)}

    with _AssumptionSolveSession(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        name_prefix="marco_s",
    ) as session:

        def solve_seed(
            indices: List[int],
            want_core: bool = False,
        ) -> Tuple[SolveResult, Optional[List[int]]]:
            """
            Two-step solve:
            1) SAT/UNSAT probe without extraction (more stable on SAT),
            2) optional UNSAT core extraction only when needed.
            """
            result, _ = session.solve(indices, extract_core=False)
            if want_core and use_core and result == SolveResult.UNSAT:
                _, core = session.solve(indices, extract_core=True)
                return result, core
            return result, None

        def shrink_to_mus(seed_indices: Set[int], initial_core: Optional[Set[int]]) -> Set[int]:
            """
            Shrink an UNSAT seed to a MUS using core-guided deletion
            with clause-set refinement (matching CPMpy's approach).

            When the solver returns UNSAT after removing a constraint,
            the new core replaces the working set — often dramatically
            reducing the number of deletion tests needed.
            """
            # Start from the core if available (smaller than the full seed)
            if initial_core:
                mus_set = set(initial_core) & seed_indices
                if not mus_set:
                    mus_set = set(seed_indices)
            else:
                mus_set = set(seed_indices)

            ordered = sorted(mus_set, key=lambda i: deletion_order.get(i, 0))

            for idx in ordered:
                if idx not in mus_set:
                    continue
                mus_set.remove(idx)
                if not mus_set:
                    mus_set.add(idx)
                    continue

                result, core = solve_seed(sorted(mus_set), want_core=use_core)

                if result == SolveResult.SAT:
                    # Constraint is necessary for UNSAT — restore it
                    mus_set.add(idx)
                elif result == SolveResult.UNSAT:
                    # Still UNSAT — refine working set from new core
                    if use_core and core:
                        refined = set(core) & mus_set
                        if refined:
                            mus_set = refined
                    # idx stays removed
                else:
                    # UNKNOWN/ERROR — be safe, restore
                    mus_set.add(idx)

            return mus_set

        def grow_to_mss(seed_indices: Set[int]) -> Set[int]:
            """
            Grow a SAT seed to an MSS using assumption-based incremental solving.
            """
            mss_set = set(seed_indices)

            for i in range(n):
                if i in mss_set:
                    continue
                test = sorted(mss_set | {i})
                result, _ = solve_seed(test, want_core=False)
                if result == SolveResult.SAT:
                    mss_set.add(i)

            return mss_set

        # Main MARCO loop
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Get next unexplored seed from map solver
            seed_set = map_solver.solve()
            if seed_set is None:
                if verbose >= 0:
                    print(f"MARCO: enumeration complete after {iteration - 1} iterations")
                break

            if verbose >= 0:
                print(f"MARCO: iteration {iteration}, seed size {len(seed_set)}")

            result, core = solve_seed(sorted(seed_set), want_core=use_core)

            if result == SolveResult.SAT:
                # SAT: grow to MSS, block down (subsets)
                mss_set = grow_to_mss(seed_set)
                map_solver.block_down(mss_set)

                # MCS = complement of MSS
                mcs_set = set(range(n)) - mss_set

                if verbose >= 0:
                    print(f"MARCO: found MSS of size {len(mss_set)}, MCS of size {len(mcs_set)}")

                if return_mcs and mcs_set:
                    yield ("MCS", [soft[i] for i in sorted(mcs_set)])

            elif result == SolveResult.UNSAT:
                # UNSAT: shrink to MUS using core-guided deletion
                core_set = set(core) if (use_core and core) else None
                mus_set = shrink_to_mus(seed_set, core_set)
                map_solver.block_up(mus_set)

                if verbose >= 0:
                    print(f"MARCO: found MUS of size {len(mus_set)}")

                if return_mus and mus_set:
                    yield ("MUS", [soft[i] for i in sorted(mus_set)])

            else:
                # UNKNOWN/ERROR — treat as SAT (grow side) to avoid infinite loop
                if verbose >= 0:
                    print(f"MARCO: solver returned UNKNOWN/ERROR, skipping seed")
                mss_set = grow_to_mss(seed_set)
                map_solver.block_down(mss_set)


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


def marco_core(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    return_mus: bool = True,
    return_mcs: bool = True,
    verbose: int = -1,
    max_iterations: int = DEFAULT_MAX_MARCO_ITERATIONS,
    handoff_threshold: Optional[int] = None,
    batch_base_ratio: int = 2,
    sat_backoff_cap: int = 8,
) -> Iterator[Tuple[Literal["MUS", "MCS"], ConstraintList]]:
    """
    Enumerate all MUSes and MCSes with core-informed MARCO.

    This variant extends `marco()` with three extra accelerations:
    1) core intersection tracking across UNSAT seeds,
    2) seed pre-shrinking when a seed contains a known MUS,
    3) BiCore-QX shrinking (batched elimination + QuickXplain handoff).
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return

    n = len(soft)
    use_core = solver.lower() == "ace"

    if handoff_threshold is None:
        handoff_threshold = max(8, n // 3)
    if handoff_threshold < 1:
        raise ValueError("handoff_threshold must be >= 1")
    if batch_base_ratio < 1:
        raise ValueError("batch_base_ratio must be >= 1")
    if sat_backoff_cap < 0:
        raise ValueError("sat_backoff_cap must be >= 0")

    map_solver = MapSolver(n)

    # Heuristic ordering: remove high-arity constraints first.
    def num_vars(i: int) -> int:
        try:
            return len(get_constraint_variables(soft[i]))
        except (AttributeError, TypeError, ValueError):
            return 0

    deletion_order = {i: -num_vars(i) for i in range(n)}

    known_muses: List[Set[int]] = []
    known_mus_keys: Set[FrozenSet[int]] = set()
    core_isect: Optional[Set[int]] = None

    with _AssumptionSolveSession(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        name_prefix="marco_core_s",
    ) as session:

        def solve_seed(
            indices: List[int],
            want_core: bool = False,
        ) -> Tuple[SolveResult, Optional[List[int]]]:
            result, _ = session.solve(indices, extract_core=False)
            if want_core and use_core and result == SolveResult.UNSAT:
                _, core = session.solve(indices, extract_core=True)
                return result, core
            return result, None

        def update_core_intersection(seed_indices: Set[int], core_indices: Optional[List[int]]) -> None:
            nonlocal core_isect
            if not use_core or not core_indices:
                return
            core_set = set(core_indices) & seed_indices
            if not core_set:
                return
            if core_isect is None:
                core_isect = set(core_set)
            else:
                core_isect &= core_set

        def shrink_to_mus_deletion(
            seed_indices: Set[int],
            initial_core: Optional[Set[int]] = None,
            locked: Optional[Set[int]] = None,
        ) -> Set[int]:
            """
            Exact core-guided deletion fallback/certification pass.
            """
            if initial_core:
                mus_set = set(initial_core) & seed_indices
                if not mus_set:
                    mus_set = set(seed_indices)
            else:
                mus_set = set(seed_indices)

            locked_set = set(locked) if locked else set()
            ordered = sorted(mus_set, key=lambda i: deletion_order.get(i, 0))

            for idx in ordered:
                if idx not in mus_set or idx in locked_set:
                    continue

                mus_set.remove(idx)
                if not mus_set:
                    mus_set.add(idx)
                    continue

                result, core = solve_seed(sorted(mus_set), want_core=use_core)

                if result == SolveResult.SAT:
                    mus_set.add(idx)
                elif result == SolveResult.UNSAT:
                    if use_core and core:
                        refined = set(core) & mus_set
                        if refined:
                            mus_set = refined
                            locked_set &= mus_set
                else:
                    mus_set.add(idx)

            return mus_set

        def preshrink_seed(
            seed_indices: Set[int],
            seed_core: Optional[Set[int]],
        ) -> Set[int]:
            projected = set(seed_indices)
            if seed_core:
                projected &= seed_core | seed_indices

            # If this seed contains a known MUS, begin from MUS + fresh core info.
            for known_mus in sorted(known_muses, key=len):
                if known_mus <= seed_indices:
                    projected = set(known_mus)
                    if seed_core:
                        projected |= (seed_core & seed_indices)
                    if verbose >= 1:
                        print(
                            "MARCO-CORE: pre-shrink seed via known MUS "
                            f"(|seed|={len(seed_indices)} -> |projected|={len(projected)})"
                        )
                    break
            return projected

        def shrink_to_mus_bicore_qx(seed_indices: Set[int], seed_core: Optional[Set[int]]) -> Set[int]:
            """
            Shrink an UNSAT seed with BiCore-QX:
            - Phase 1: batched removals with adaptive splitting,
            - Phase 2: QX recursion on the residual.
            """
            projected_seed = preshrink_seed(seed_indices, seed_core)

            if seed_core:
                current = set(seed_core) & projected_seed
                if not current:
                    current = set(projected_seed)
            else:
                current = set(projected_seed)

            if not current:
                current = set(seed_indices)

            locked: Set[int] = set(core_isect & current) if core_isect else set()

            batch_queue: List[Set[int]] = []
            consecutive_sat = 0
            base_ratio = batch_base_ratio

            # Phase 1: BiCore batch elimination.
            while True:
                unlocked = [i for i in current if i not in locked]
                if len(unlocked) <= handoff_threshold:
                    break

                batch: Optional[Set[int]] = None

                while batch_queue and batch is None:
                    queued = batch_queue.pop()
                    queued = {i for i in queued if i in current and i not in locked}
                    if queued:
                        batch = queued

                if batch is None:
                    available = sorted(unlocked, key=lambda i: deletion_order.get(i, 0))
                    if not available:
                        break
                    exp = min(consecutive_sat, sat_backoff_cap)
                    divisor = min(base_ratio * (2 ** exp), len(available))
                    batch_size = max(1, len(available) // divisor)
                    batch = set(available[:batch_size])

                test_set = set(current) - batch
                if not test_set:
                    # Can't remove everything at once: split or lock.
                    if len(batch) == 1:
                        locked |= batch
                        continue
                    ordered_batch = sorted(batch, key=lambda i: deletion_order.get(i, 0))
                    split = len(ordered_batch) // 2
                    left = set(ordered_batch[:split])
                    right = set(ordered_batch[split:])
                    if left:
                        batch_queue.append(left)
                    if right:
                        batch_queue.append(right)
                    continue

                result, core = solve_seed(sorted(test_set), want_core=use_core)

                if result == SolveResult.UNSAT:
                    consecutive_sat = 0
                    if use_core and core:
                        refined = {i for i in core if i in test_set}
                        current = refined if refined else set(test_set)
                    else:
                        current = set(test_set)
                    locked &= current
                    continue

                if result == SolveResult.SAT:
                    consecutive_sat += 1
                    if len(batch) == 1:
                        locked |= batch
                        continue
                    ordered_batch = sorted(batch, key=lambda i: deletion_order.get(i, 0))
                    split = len(ordered_batch) // 2
                    left = set(ordered_batch[:split])
                    right = set(ordered_batch[split:])
                    if left:
                        batch_queue.append(left)
                    if right:
                        batch_queue.append(right)
                    continue

                # UNKNOWN/ERROR: use exact deletion fallback on current set.
                if verbose >= 0:
                    print("MARCO-CORE: solver returned UNKNOWN/ERROR during batch phase, fallback to deletion")
                return shrink_to_mus_deletion(current, locked=locked)

            # Phase 2: QuickXplain handoff on residual.
            residual = sorted(current)
            if not residual:
                return set()

            locked_residual = sorted(i for i in residual if i in locked)
            unlocked_residual = [i for i in residual if i not in locked]

            def qx_unsat(enabled: List[int]) -> bool:
                result, _ = solve_seed(enabled, want_core=False)
                return result == SolveResult.UNSAT

            def qx_recursive(
                soft_idx: List[int],
                hard_idx: List[int],
                delta: List[int],
            ) -> List[int]:
                if delta and qx_unsat(hard_idx):
                    return []
                if len(soft_idx) == 1:
                    return list(soft_idx)

                split = len(soft_idx) // 2
                left = soft_idx[:split]
                right = soft_idx[split:]

                delta2 = qx_recursive(right, hard_idx + left, left)
                delta1 = qx_recursive(left, hard_idx + delta2, delta2)
                return delta1 + delta2

            if unlocked_residual:
                qx_part = qx_recursive(unlocked_residual, list(locked_residual), [])
                mus_set = set(locked_residual) | set(qx_part)
            else:
                mus_set = set(locked_residual)

            # Certification pass keeps output exact even if lock heuristics are noisy.
            return shrink_to_mus_deletion(mus_set)

        def grow_to_mss(seed_indices: Set[int]) -> Set[int]:
            mss_set = set(seed_indices)
            for i in range(n):
                if i in mss_set:
                    continue
                result, _ = solve_seed(sorted(mss_set | {i}), want_core=False)
                if result == SolveResult.SAT:
                    mss_set.add(i)
            return mss_set

        iteration = 0
        while iteration < max_iterations:
            iteration += 1

            seed_set = map_solver.solve()
            if seed_set is None:
                if verbose >= 0:
                    print(f"MARCO-CORE: enumeration complete after {iteration - 1} iterations")
                break

            if verbose >= 0:
                print(f"MARCO-CORE: iteration {iteration}, seed size {len(seed_set)}")

            result, core = solve_seed(sorted(seed_set), want_core=use_core)

            if result == SolveResult.SAT:
                mss_set = grow_to_mss(seed_set)
                map_solver.block_down(mss_set)
                mcs_set = set(range(n)) - mss_set

                if verbose >= 0:
                    print(f"MARCO-CORE: found MSS size {len(mss_set)}, MCS size {len(mcs_set)}")

                if return_mcs and mcs_set:
                    yield ("MCS", [soft[i] for i in sorted(mcs_set)])
                continue

            if result == SolveResult.UNSAT:
                core_set = set(core) & seed_set if (use_core and core) else None
                update_core_intersection(seed_set, core)
                mus_set = shrink_to_mus_bicore_qx(seed_set, core_set)
                map_solver.block_up(mus_set)

                # Optional extra blocking from larger UNSAT cores discovered en route.
                if core_set and core_set != mus_set:
                    map_solver.block_up(core_set)

                mus_key = frozenset(mus_set)
                if mus_key not in known_mus_keys:
                    known_mus_keys.add(mus_key)
                    known_muses.append(set(mus_set))

                if verbose >= 0:
                    isect_size = len(core_isect) if core_isect is not None else 0
                    print(f"MARCO-CORE: found MUS size {len(mus_set)} (core_isect={isect_size})")

                if return_mus and mus_set:
                    yield ("MUS", [soft[i] for i in sorted(mus_set)])
                continue

            if verbose >= 0:
                print("MARCO-CORE: solver returned UNKNOWN/ERROR, treating as SAT-side skip")
            mss_set = grow_to_mss(seed_set)
            map_solver.block_down(mss_set)


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


def all_mus_core(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    max_mus: Optional[int] = None,
    verbose: int = -1,
    handoff_threshold: Optional[int] = None,
    batch_base_ratio: int = 2,
    sat_backoff_cap: int = 8,
) -> List[ConstraintList]:
    """
    Find all MUSes using core-informed MARCO (`marco_core`).
    """
    muses: List[ConstraintList] = []
    for result_type, subset in marco_core(
        soft,
        hard,
        solver,
        return_mus=True,
        return_mcs=False,
        verbose=verbose,
        handoff_threshold=handoff_threshold,
        batch_base_ratio=batch_base_ratio,
        sat_backoff_cap=sat_backoff_cap,
    ):
        if result_type == "MUS":
            muses.append(subset)
            if max_mus is not None and len(muses) >= max_mus:
                break
    return muses


def all_mcs_core(
    soft: ConstraintList,
    hard: Optional[ConstraintList] = None,
    solver: str = "ace",
    max_mcs: Optional[int] = None,
    verbose: int = -1,
    handoff_threshold: Optional[int] = None,
    batch_base_ratio: int = 2,
    sat_backoff_cap: int = 8,
) -> List[ConstraintList]:
    """
    Find all MCSes using core-informed MARCO (`marco_core`).
    """
    mcses: List[ConstraintList] = []
    for result_type, subset in marco_core(
        soft,
        hard,
        solver,
        return_mus=False,
        return_mcs=True,
        verbose=verbose,
        handoff_threshold=handoff_threshold,
        batch_base_ratio=batch_base_ratio,
        sat_backoff_cap=sat_backoff_cap,
    ):
        if result_type == "MCS":
            mcses.append(subset)
            if max_mcs is not None and len(mcses) >= max_mcs:
                break
    return mcses
