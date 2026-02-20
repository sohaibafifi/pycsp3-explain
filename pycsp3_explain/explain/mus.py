"""
MUS (Minimal Unsatisfiable Subset) algorithms for PyCSP3.

This module provides implementations of:
- mus: Assumption-based MUS using core extraction (ACE)
- mus_naive: Deletion-based MUS using naive re-solving
- mus_bicore: Core-guided + batched exact MUS shrinking
- mus_cpqx: Core-projected QuickXplain (exact hybrid)
- mus_bicore_qx: Hybrid BiCore bulk elimination + QuickXplain (exact)
- quickxplain: Preferred MUS using QuickXplain with core extraction when possible
- optimal_mus: Find optimal MUS according to weights
- smus: Find smallest MUS
- ocus: Optimal Constrained MUS
- ocus_naive: Optimal Constrained MUS (naive version)

A MUS is a minimal subset of constraints that is unsatisfiable:
- The subset itself is UNSAT
- Removing any constraint from the subset makes it SAT
"""

import warnings
from itertools import combinations
from typing import List, Any, Optional, Union, Callable, Set

from pycsp3_explain.explain.utils import (
    flatten_constraints,
    order_by_num_variables,
    make_assump_model,
    get_constraint_variables,
    normalize_constraint_list,
)
from pycsp3_explain.solvers.wrapper import (
    SolveResult,
    is_sat,
    is_unsat,
    solve_subset,
    solve_subset_with_core,
    clean_pycsp3_state,
    _AssumptionSolveSession,
)


class OCUSException(Exception):
    """Exception raised when OCUS cannot find a valid solution."""
    pass


def _solve_selection_model(
    n: int,
    solver: str,
    verbose: int,
    constraints_builder: Callable[[List[Any]], Optional[Any]],
    objective_builder: Optional[Callable[[List[Any]], Any]] = None,
    fixed_selection: Optional[Set[int]] = None,
) -> Union[Optional[Set[int]], bool]:
    from pycsp3 import (
        VarArray,
        satisfy,
        minimize,
        solve,
        value,
        ACE,
        CHOCO,
        SAT,
        OPTIMUM,
    )
    import os
    import tempfile
    import uuid

    fixed = set(fixed_selection) if fixed_selection is not None else None
    if fixed is not None and any(i < 0 or i >= n for i in fixed):
        raise ValueError("fixed_selection contains indices out of range")

    with clean_pycsp3_state():
        var_id = f"hs_{uuid.uuid4().hex}"
        if fixed is None:
            select = VarArray(size=n, dom=range(2), id=var_id)
        else:
            def dom(i):
                return range(1, 2) if i in fixed else range(0, 1)

            select = VarArray(size=n, dom=dom, id=var_id)

        constraints = normalize_constraint_list(constraints_builder(select))
        if constraints:
            satisfy(constraints)
        else:
            satisfy()

        if objective_builder is not None:
            minimize(objective_builder(select))

        solver_type = ACE if solver.lower() == "ace" else CHOCO
        temp_filename = os.path.join(
            tempfile.gettempdir(),
            f"pycsp3_explain_hs_{uuid.uuid4().hex}.xml",
        )
        status = solve(
            solver=solver_type,
            verbose=verbose,
            filename=temp_filename,
        )

        try:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
        except Exception:
            pass

        if objective_builder is None:
            return status in (SAT, OPTIMUM)

        if status not in (SAT, OPTIMUM):
            return None

        return {i for i in range(n) if value(select[i]) == 1}


def _make_subset_checker(
    n: int,
    solver: str,
    verbose: int,
    subset_predicate: Optional[Callable[[Set[int]], bool]],
    subset_constraints: Optional[Callable[[List[Any]], Any]],
) -> Callable[[Set[int]], bool]:
    def check(indices: Set[int]) -> bool:
        if subset_predicate is not None and not subset_predicate(indices):
            return False
        if subset_constraints is None:
            return True

        def constraints_builder(select):
            return normalize_constraint_list(subset_constraints(select))

        return bool(
            _solve_selection_model(
                n=n,
                solver=solver,
                verbose=verbose,
                constraints_builder=constraints_builder,
                objective_builder=None,
                fixed_selection=indices,
            )
        )

    return check


def _find_optimal_hitting_set(
    n: int,
    correction_sets: List[Set[int]],
    weights: List[Union[int, float]],
    solver: str,
    verbose: int,
    subset_constraints: Optional[Callable[[List[Any]], Any]] = None,
    subset_predicate: Optional[Callable[[Set[int]], bool]] = None,
    subset_checker: Optional[Callable[[Set[int]], bool]] = None,
) -> Optional[Set[int]]:
    if subset_checker is None:
        subset_checker = _make_subset_checker(
            n=n,
            solver=solver,
            verbose=verbose,
            subset_predicate=subset_predicate,
            subset_constraints=subset_constraints,
        )

    if not correction_sets and subset_constraints is None and subset_predicate is None:
        return set(range(n))  # All indices if no correction sets

    if any(len(cs) == 0 for cs in correction_sets):
        return None

    from pycsp3 import Sum
    from pycsp3.tools.utilities import integer_scaling

    if any(isinstance(weight, float) and not weight.is_integer() for weight in weights):
        scaled_w = integer_scaling(weights)
    else:
        scaled_w = [int(weight) for weight in weights]

    def constraints_builder(select):
        constraints: List[Any] = []
        if correction_sets:
            constraints.extend(Sum(select[i] for i in cs) >= 1 for cs in correction_sets)
        if subset_constraints is not None:
            constraints.extend(normalize_constraint_list(subset_constraints(select)))
        return constraints

    def objective_builder(select):
        return Sum(select[i] * scaled_w[i] for i in range(n))

    use_cp = subset_predicate is None or subset_constraints is not None
    if use_cp:
        try:
            hitting_set = _solve_selection_model(
                n=n,
                solver=solver,
                verbose=verbose,
                constraints_builder=constraints_builder,
                objective_builder=objective_builder,
            )
            if hitting_set is not None and subset_checker(hitting_set):
                return hitting_set
        except Exception as exc:
            if verbose >= 0:
                print(f"hitting set CP solve failed ({exc}); using enumeration")

    indexed_weights = [(i, weights[i]) for i in range(n)]
    indexed_weights.sort(key=lambda x: x[1])

    best_set = None
    best_weight = float("inf")

    for size in range(1, n + 1):
        min_possible_weight = sum(indexed_weights[i][1] for i in range(size))
        if min_possible_weight >= best_weight:
            break

        for combo in combinations(range(n), size):
            combo_set = set(combo)
            if not subset_checker(combo_set):
                continue

            combo_weight = sum(weights[i] for i in combo)
            if combo_weight >= best_weight:
                continue

            hits_all = all(bool(combo_set & cs) for cs in correction_sets) if correction_sets else True
            if hits_all:
                best_set = combo_set
                best_weight = combo_weight

    return best_set


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


def mus(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a Minimal Unsatisfiable Subset using assumption indicators.

    This implementation relies on ACE's core extraction to seed and refine
    a deletion-based MUS search.

    :param soft: List of soft constraints (candidates for MUS)
    :param hard: List of hard constraints (always included, not in MUS)
    :param solver: Solver name ("ace" only for core extraction)
    :param verbose: Verbosity level (-1 for silent)
    :return: A minimal unsatisfiable subset of soft constraints
    :raises AssertionError: If soft + hard is satisfiable
    """
    if solver.lower() != "ace":
        if verbose >= 0:
            print("mus: solver does not support core extraction, using mus_naive")
        return mus_naive(soft, hard, solver, verbose)

    soft, hard, assumptions, guard_constraints = make_assump_model(soft, hard)

    def solve_with_assumptions(assumed_indices: List[int]):
        assumption_constraints = [assumptions[i] == 1 for i in assumed_indices]
        soft_constraints = guard_constraints + assumption_constraints
        return solve_subset_with_core(soft_constraints, hard, solver, verbose)

    def core_to_assumptions(core_indices: List[int], assumed_indices: List[int]) -> set[int]:
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

    all_indices = list(range(len(soft)))
    result, core_indices = solve_with_assumptions(all_indices)
    assert result == SolveResult.UNSAT, \
        "MUS: model must be UNSAT (soft + hard constraints must be unsatisfiable)"

    core = core_to_assumptions(core_indices, all_indices)
    if not core:
        core = set(all_indices)

    def num_vars(i: int) -> int:
        try:
            return len(get_constraint_variables(soft[i]))
        except Exception:
            return 0

    ordered = sorted(core, key=num_vars, reverse=True)

    for idx in ordered:
        if idx not in core:
            continue
        core.remove(idx)
        assumed = sorted(core)
        result, core_indices = solve_with_assumptions(assumed)
        if result == SolveResult.SAT:
            core.add(idx)
        elif result == SolveResult.UNSAT:
            refined = core_to_assumptions(core_indices, assumed)
            if refined:
                core = set(refined)
        else:
            if verbose >= 0:
                print("mus: solver returned UNKNOWN/ERROR, using mus_naive")
            return mus_naive(soft, hard, solver, verbose)

    return [soft[i] for i in range(len(soft)) if i in core]


def mus_bicore(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a MUS with core-guided batched shrinking.

    The algorithm keeps one reusable assumption session and combines:
    1. core compression (when available),
    2. batched removals (group testing),
    3. binary splitting of SAT batches,
    4. final singleton certification for exact minimality.

    This function is exact: returned subsets are MUSes (not heuristics).
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)
    use_core = solver.lower() == "ace"

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
        name_prefix="mus_bicore",
    ) as session:
        all_indices = list(range(n))
        result, core = session.solve(all_indices, extract_core=use_core)

        if result == SolveResult.SAT:
            raise AssertionError("mus_bicore: model must be UNSAT")
        if result != SolveResult.UNSAT:
            if verbose >= 0:
                print("mus_bicore: solver returned UNKNOWN/ERROR, using mus_naive")
            return mus_naive(soft, hard, solver, verbose)

        current: Set[int] = set(core) if (use_core and core) else set(all_indices)
        locked: Set[int] = set()
        batch_queue: List[Set[int]] = []

        # Phase 1: batched shrinking with core compression.
        while True:
            batch: Optional[Set[int]] = None

            while batch_queue and batch is None:
                queued = batch_queue.pop()
                queued = {i for i in queued if i in current and i not in locked}
                if queued:
                    batch = queued

            if batch is None:
                available = [i for i in sorted(current, key=num_vars, reverse=True) if i not in locked]
                if not available:
                    break
                if len(available) == 1:
                    batch = {available[0]}
                else:
                    batch_size = max(1, len(available) // 2)
                    batch = set(available[:batch_size])

            test = sorted(set(current) - batch)
            result, core = session.solve(test, extract_core=use_core)

            if result == SolveResult.UNSAT:
                if use_core and core:
                    refined = {i for i in core if i in test}
                    current = refined if refined else set(test)
                else:
                    current = set(test)
                locked &= current
                continue

            if result == SolveResult.SAT:
                if len(batch) == 1:
                    locked |= batch
                    continue

                ordered_batch = sorted(batch, key=num_vars, reverse=True)
                split = len(ordered_batch) // 2
                left = set(ordered_batch[:split])
                right = set(ordered_batch[split:])
                if left:
                    batch_queue.append(left)
                if right:
                    batch_queue.append(right)
                continue

            if verbose >= 0:
                print("mus_bicore: solver returned UNKNOWN/ERROR, using mus_naive")
            return mus_naive(soft, hard, solver, verbose)

        # Phase 2: exact singleton certification.
        changed = True
        while changed:
            changed = False
            for idx in sorted(current, key=num_vars, reverse=True):
                test = sorted(set(current) - {idx})
                result, core = session.solve(test, extract_core=use_core)

                if result == SolveResult.UNSAT:
                    if use_core and core:
                        refined = {i for i in core if i in test}
                        current = refined if refined else set(test)
                    else:
                        current = set(test)
                    locked.discard(idx)
                    locked &= current
                    changed = True
                    break

                if result == SolveResult.SAT:
                    locked.add(idx)
                    continue

                if verbose >= 0:
                    print("mus_bicore: solver returned UNKNOWN/ERROR, using mus_naive")
                return mus_naive(soft, hard, solver, verbose)

        return [soft[i] for i in sorted(current)]


def mus_cpqx(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Compute a MUS with Core-Projected QuickXplain (CPQX).

    Strategy:
    1. For tiny soft sets, run QuickXplain directly (lower overhead).
    2. For larger sets with ACE, extract one UNSAT core.
    3. Run QuickXplain on the projected core subset only.

    The method is exact: output is a MUS of the original problem.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    # For small instances, core pre-pass overhead is usually not worth it.
    if len(soft) < 6 or solver.lower() != "ace":
        return quickxplain(soft, hard, solver, verbose)

    result, core_raw = solve_subset_with_core(soft, hard, solver, verbose)
    assert result == SolveResult.UNSAT, "mus_cpqx: model must be UNSAT"

    if not core_raw:
        return quickxplain(soft, hard, solver, verbose)

    hard_offset = len(hard)
    core_indices = sorted({
        i - hard_offset
        for i in core_raw
        if i >= hard_offset and (i - hard_offset) < len(soft)
    })
    if not core_indices or len(core_indices) >= len(soft):
        return quickxplain(soft, hard, solver, verbose)

    reduced_soft = [soft[i] for i in core_indices]
    return quickxplain(reduced_soft, hard, solver, verbose)


def mus_bicore_qx(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1,
    handoff_threshold: Optional[int] = None,
) -> List[Any]:
    """
    Compute a MUS with Hybrid BiCore-QuickXplain.

    This algorithm combines two complementary strategies within a single
    reusable assumption session:

    **Phase 1 — BiCore bulk elimination:**
    Removes large batches of constraints at once (group testing). When a
    batch removal leaves the problem UNSAT the batch is discarded; when SAT
    the batch is binary-split and re-queued. Adaptive batch sizing uses
    exponential backoff: the batch shrinks after consecutive SAT results
    and grows after UNSAT results, tuning itself to the MUS density.
    Core compression at every UNSAT step continuously narrows the working set.

    **Phase 2 — Incremental QuickXplain on residual:**
    Once the working set is small enough (|unlocked| ≤ *handoff_threshold*),
    the algorithm switches to a full QuickXplain recursion operating on
    assumption indices. QuickXplain provides exact minimality with
    O(k · log(m/k)) solver calls where m is the residual size and k the
    final MUS size.

    The algorithm is **exact**: the returned subset is a MUS.

    :param soft: List of soft constraints (candidates for MUS)
    :param hard: List of hard constraints (always included, not in MUS)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :param handoff_threshold: Size of unlocked working set at which Phase 1
        switches to QuickXplain (Phase 2). Default: max(8, n // 3).
    :return: A minimal unsatisfiable subset of soft constraints
    :raises ValueError: If soft is empty
    :raises AssertionError: If soft + hard is satisfiable

    Complexity:
        Phase 1 best case: O(log(n/k)) solver calls to reduce n → ≈ k.
        Phase 2 worst case: O(k · log(m/k)) calls for exact minimality.
        Combined: often significantly fewer calls than pure deletion or
        pure QuickXplain on instances with large n and small k.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)
    use_core = solver.lower() == "ace"

    if handoff_threshold is None:
        handoff_threshold = max(8, n // 3)

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
        name_prefix="mus_bqx",
    ) as session:
        solve_calls = [0]

        def _solve(indices: List[int], extract: bool = False):
            solve_calls[0] += 1
            return session.solve(indices, extract_core=extract)

        # ── verify UNSAT and seed with core ──
        all_indices = list(range(n))
        result, core = _solve(all_indices, extract=use_core)

        if result == SolveResult.SAT:
            raise AssertionError("mus_bicore_qx: model must be UNSAT")
        if result != SolveResult.UNSAT:
            if verbose >= 0:
                print("mus_bicore_qx: solver returned UNKNOWN/ERROR, using mus_naive")
            return mus_naive(soft, hard, solver, verbose)

        current: Set[int] = set(core) if (use_core and core) else set(all_indices)
        locked: Set[int] = set()

        # ── Phase 1: BiCore bulk elimination ──
        batch_queue: List[Set[int]] = []
        # Adaptive batch sizing state
        consecutive_sat = 0
        base_ratio = 2  # start: remove half

        while True:
            unlocked_count = len(current) - len(locked & current)
            if unlocked_count <= handoff_threshold:
                break

            # Pick next batch
            batch: Optional[Set[int]] = None

            while batch_queue and batch is None:
                queued = batch_queue.pop()
                queued = {i for i in queued if i in current and i not in locked}
                if queued:
                    batch = queued

            if batch is None:
                available = [
                    i for i in sorted(current, key=num_vars, reverse=True)
                    if i not in locked
                ]
                if not available:
                    break
                # Adaptive: grow divisor after SAT (smaller batches),
                # reset after UNSAT (larger batches)
                divisor = min(base_ratio * (2 ** consecutive_sat), len(available))
                batch_size = max(1, len(available) // divisor)
                batch = set(available[:batch_size])

            test = sorted(set(current) - batch)
            result, core = _solve(test, extract=use_core)

            if result == SolveResult.UNSAT:
                consecutive_sat = 0
                if use_core and core:
                    refined = {i for i in core if i in test}
                    current = refined if refined else set(test)
                else:
                    current = set(test)
                locked &= current
                if verbose >= 0:
                    print(f"  [phase1] UNSAT: dropped {len(batch)} → "
                          f"|current|={len(current)}, |locked|={len(locked & current)}")
                continue

            if result == SolveResult.SAT:
                consecutive_sat += 1
                if len(batch) == 1:
                    locked |= batch
                    continue
                # Binary-split and re-queue
                ordered_batch = sorted(batch, key=num_vars, reverse=True)
                split = len(ordered_batch) // 2
                left = set(ordered_batch[:split])
                right = set(ordered_batch[split:])
                if left:
                    batch_queue.append(left)
                if right:
                    batch_queue.append(right)
                continue

            # UNKNOWN/ERROR
            if verbose >= 0:
                print("mus_bicore_qx: solver returned UNKNOWN/ERROR, using mus_naive")
            return mus_naive(soft, hard, solver, verbose)

        # ── Phase 2: incremental QuickXplain on residual ──
        residual = sorted(current)

        if verbose >= 0:
            print(f"  [handoff] Phase1→QX: |residual|={len(residual)}, "
                  f"|locked|={len(locked & current)}, calls_so_far={solve_calls[0]}")

        def qx_solve(enabled: List[int]) -> bool:
            """Check UNSAT under the given assumption indices."""
            result, _ = _solve(enabled, extract=False)
            return result == SolveResult.UNSAT

        def qx_recursive(
            soft_idx: List[int],
            hard_idx: List[int],
            delta: List[int],
        ) -> List[int]:
            if delta:
                if qx_solve(hard_idx):
                    return []
            if len(soft_idx) == 1:
                return list(soft_idx)

            split = len(soft_idx) // 2
            more_preferred = soft_idx[:split]
            less_preferred = soft_idx[split:]

            delta2 = qx_recursive(
                less_preferred,
                hard_idx + more_preferred,
                more_preferred,
            )
            delta1 = qx_recursive(
                more_preferred,
                hard_idx + delta2,
                delta2,
            )
            return delta1 + delta2

        mus_indices = qx_recursive(residual, [], [])

        if verbose >= 0:
            print(f"  [done] |MUS|={len(mus_indices)}, total_calls={solve_calls[0]}")

        return [soft[i] for i in mus_indices]


def quickxplain(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find a preferred MUS using the QuickXplain algorithm with core extraction.

    This algorithm finds a MUS where constraints earlier in the `soft` list
    are preferred over later ones. When using ACE solver, it leverages UNSAT
    core extraction to potentially reduce the number of solver calls.

    Algorithm (from Junker, 2004):
    ==============================
    QuickXplain is a divide-and-conquer algorithm that finds a MUS respecting
    a preference ordering. Given constraints C = {c1, c2, ..., cn} ordered by
    preference (earlier = more preferred), it returns a MUS that includes
    as many preferred constraints as possible.

    The key insight is that if C is UNSAT, we can split it into:
    - C1 = more preferred half (earlier constraints)
    - C2 = less preferred half (later constraints)

    Then recursively:
    1. Find conflicts from C2 while treating C1 as background (must hold)
    2. Find which constraints from C1 are actually needed given the conflicts from C2

    Base cases:
    - If |C| = 1, the single constraint must be in the MUS
    - If background B alone is UNSAT, the conflict is in B (return empty)

    Core extraction optimization:
    =============================
    When the solver returns UNSAT, we extract the UNSAT core (subset of
    constraints that caused the conflict). This can help prune the search
    by identifying which constraints are definitely in the MUS.

    Complexity:
    - Worst case: O(n + k * log(n/k)) SAT calls, where k = |MUS|
    - Best case with good core extraction: fewer calls due to core-based pruning

    :param soft: List of soft constraints (order determines preference)
    :param hard: List of hard constraints (always included)
    :param solver: Solver name ("ace" for core extraction)
    :param verbose: Verbosity level (-1 for silent)
    :return: A preferred minimal unsatisfiable subset
    :raises AssertionError: If soft + hard is satisfiable

    References:
        Junker, U. "QUICKXPLAIN: Preferred Explanations and Relaxations for
        Over-Constrained Problems." AAAI 2004, pp. 167-172.

        Junker, U. "QUICKXPLAIN: Conflict Detection for Arbitrary Constraint
        Propagation Algorithms." IJCAI 2001 Workshop on Modelling and Solving
        Problems with Constraints.

    Example:
        >>> # c0 and c1 both conflict with c2, but we prefer c0
        >>> soft = [c0, c1, c2]  # c0 is most preferred
        >>> mus = quickxplain(soft)  # Returns MUS containing c0 if possible
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    # Verify the model is UNSAT
    assert is_unsat(soft, hard, solver, verbose), \
        "QuickXplain: model must be UNSAT"

    n = len(soft)

    def solve_with_core(soft_list: List[Any], hard_list: List[Any]) -> tuple:
        """
        Solve and extract UNSAT core if available.

        Returns (is_unsat, core_indices) where core_indices are indices into
        soft_list that appear in the UNSAT core (empty if SAT or no core).
        """
        if solver.lower() == "ace":
            result, core_raw = solve_subset_with_core(soft_list, hard_list, solver, verbose)
            if result == SolveResult.UNSAT and core_raw:
                # Map core indices back to soft_list indices
                # Core indices reference hard + soft, so subtract hard offset
                hard_offset = len(hard_list)
                core_indices = [idx - hard_offset for idx in core_raw
                               if idx >= hard_offset and idx - hard_offset < len(soft_list)]
                return True, core_indices
            return result == SolveResult.UNSAT, []
        else:
            return is_unsat(soft_list, hard_list, solver, verbose), []

    def quickxplain_recursive(
        soft_list: List[Any],
        hard_list: List[Any],
        delta: List[Any]
    ) -> List[Any]:
        """
        Recursive QuickXplain procedure with core extraction.

        :param soft_list: Current soft constraints to analyze
        :param hard_list: Current hard constraints (background)
        :param delta: Constraints added to hard since last check
        :return: Minimal conflict from soft_list
        """
        # If delta is non-empty and hard alone is UNSAT, conflict is in hard
        if delta:
            unsat, _ = solve_with_core([], hard_list)
            if unsat:
                return []

        # Base case: only one constraint, it must be in the MUS
        if len(soft_list) == 1:
            return list(soft_list)

        # Split soft constraints
        split = len(soft_list) // 2
        more_preferred = soft_list[:split]  # Earlier = more preferred
        less_preferred = soft_list[split:]

        # Find conflicts from less preferred, treating more preferred as hard
        delta2 = quickxplain_recursive(
            less_preferred,
            hard_list + more_preferred,
            more_preferred
        )

        # Find which more preferred constraints are actually needed
        delta1 = quickxplain_recursive(
            more_preferred,
            hard_list + delta2,
            delta2
        )

        return delta1 + delta2

    result = quickxplain_recursive(soft, hard, [])

    if verbose >= 0:
        print(f"quickxplain: found MUS with {len(result)} constraints")

    return result


def quickxplain_incremental(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find a preferred MUS using QuickXplain with incremental solving (reusable assumption sessions)

    The method reuses one posted assumption model (hard + guards) and for each
    subset check only posts/unposts fixing constraints. This reduces model
    rebuilding overhead, although PyCSP3 still recompiles at each solve call.

    :param soft: List of soft constraints (order determines preference)
    :param hard: List of hard constraints (always included)
    :param solver: Solver name ("ace" or "choco")
    :param verbose: Verbosity level (-1 for silent)
    :return: A preferred minimal unsatisfiable subset
    :raises AssertionError: If soft + hard is satisfiable

    References:
        Junker, U. "QUICKXPLAIN: Preferred Explanations and Relaxations for
        Over-Constrained Problems." AAAI 2004, pp. 167-172.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)
    with _AssumptionSolveSession(
        soft=soft,
        hard=hard,
        solver=solver,
        verbose=verbose,
        name_prefix="qx_assump",
    ) as session:
        solve_count = [0]

        def solve_with_assumptions(enabled_indices: List[int]) -> bool:
            solve_count[0] += 1
            result, _ = session.solve(enabled_indices, extract_core=False)
            return result == SolveResult.UNSAT

        # Verify the model is UNSAT with all soft constraints enabled
        all_indices = list(range(n))
        assert solve_with_assumptions(all_indices), \
            "QuickXplain: model must be UNSAT"

        def quickxplain_recursive(
            soft_indices: List[int],
            hard_indices: List[int],
            delta: List[int]
        ) -> List[int]:
            """
            Recursive QuickXplain using assumption indices.

            :param soft_indices: Indices of current soft constraints to analyze
            :param hard_indices: Indices of constraints to treat as hard (must hold)
            :param delta: Indices added to hard since last check
            :return: Indices of minimal conflict from soft_indices
            """
            # If delta is non-empty and hard alone is UNSAT, conflict is in hard
            if delta:
                if solve_with_assumptions(hard_indices):
                    return []

            # Base case: only one constraint
            if len(soft_indices) == 1:
                return list(soft_indices)

            # Split soft constraints
            split = len(soft_indices) // 2
            more_preferred = soft_indices[:split]
            less_preferred = soft_indices[split:]

            # Find conflicts from less preferred, treating more preferred as hard
            delta2 = quickxplain_recursive(
                less_preferred,
                hard_indices + more_preferred,
                more_preferred
            )

            # Find which more preferred constraints are actually needed
            delta1 = quickxplain_recursive(
                more_preferred,
                hard_indices + delta2,
                delta2
            )

            return delta1 + delta2

        result_indices = quickxplain_recursive(all_indices, [], [])
        result = [soft[i] for i in result_indices]

        if verbose >= 0:
            print(f"quickxplain_incremental: found MUS with {len(result)} constraints "
                  f"({solve_count[0]} solver calls)")

        return result


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
    max_mus: Optional[int] = None,
    max_attempts: int = 100
) -> List[List[Any]]:
    """
    Find all MUSes (up to a maximum count).

    This implementation uses systematic constraint ordering strategies to find
    different MUSes. For complete enumeration, consider using MARCO algorithm.

    Ordering strategies used:
    1. Original ordering
    2. Reverse ordering
    3. Rotate constraints to start from different positions
    4. Order by constraint complexity (variable count)

    WARNING: This can be slow for models with many MUSes and is not guaranteed
    to find all MUSes. Use MARCO for complete enumeration.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :param max_mus: Maximum number of MUSes to find (None for all)
    :param max_attempts: Maximum attempts to find new MUSes before giving up
    :return: List of all found MUSes
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        return []

    if not is_unsat(soft, hard, solver, verbose):
        return []  # Model is SAT, no MUS

    n = len(soft)
    all_muses: List[List[Any]] = []
    blocked_sets: Set[frozenset] = set()
    attempts_without_new = 0

    def try_ordering(ordering: List[Any]) -> Optional[List[Any]]:
        """Try to find a new MUS with a given constraint ordering."""
        nonlocal attempts_without_new

        mus = mus_naive(ordering, hard, solver, verbose)
        mus_set = frozenset(id(c) for c in mus)

        if mus_set not in blocked_sets:
            blocked_sets.add(mus_set)
            attempts_without_new = 0
            return mus
        else:
            attempts_without_new += 1
            return None

    # Strategy 1: Original ordering
    result = try_ordering(soft)
    if result:
        all_muses.append(result)
        if verbose >= 0:
            print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")
        if max_mus is not None and len(all_muses) >= max_mus:
            return all_muses

    # Strategy 2: Reverse ordering
    if attempts_without_new < max_attempts:
        result = try_ordering(list(reversed(soft)))
        if result:
            all_muses.append(result)
            if verbose >= 0:
                print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")
            if max_mus is not None and len(all_muses) >= max_mus:
                return all_muses

    # Strategy 3: Order by variable count (ascending and descending)
    if attempts_without_new < max_attempts:
        ordered_asc = order_by_num_variables(soft, descending=False)
        result = try_ordering(ordered_asc)
        if result:
            all_muses.append(result)
            if verbose >= 0:
                print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")
            if max_mus is not None and len(all_muses) >= max_mus:
                return all_muses

    if attempts_without_new < max_attempts:
        ordered_desc = order_by_num_variables(soft, descending=True)
        result = try_ordering(ordered_desc)
        if result:
            all_muses.append(result)
            if verbose >= 0:
                print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")
            if max_mus is not None and len(all_muses) >= max_mus:
                return all_muses

    # Strategy 4: Rotate orderings - start from each constraint
    for start_idx in range(1, n):
        if attempts_without_new >= max_attempts:
            break
        if max_mus is not None and len(all_muses) >= max_mus:
            break

        rotated = soft[start_idx:] + soft[:start_idx]
        result = try_ordering(rotated)
        if result:
            all_muses.append(result)
            if verbose >= 0:
                print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")

    # Strategy 5: Exclude each previously found MUS constraint and retry
    # This helps find MUSes that share some but not all constraints
    for prev_mus in list(all_muses):
        if attempts_without_new >= max_attempts:
            break
        if max_mus is not None and len(all_muses) >= max_mus:
            break

        for exclude_c in prev_mus:
            if attempts_without_new >= max_attempts:
                break

            # Try ordering that puts the excluded constraint last
            remaining = [c for c in soft if id(c) != id(exclude_c)]
            reordered = remaining + [exclude_c]
            result = try_ordering(reordered)
            if result:
                all_muses.append(result)
                if verbose >= 0:
                    print(f"Found MUS #{len(all_muses)} with {len(result)} constraints")
                if max_mus is not None and len(all_muses) >= max_mus:
                    return all_muses

    return all_muses


def optimal_mus_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find an optimal MUS according to a linear objective function.

    Naive exhaustive implementation: enumerate all subsets, keep UNSAT and
    minimal ones, and return the MUS with minimum total weight.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s = SMUS)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: An optimal MUS according to weights
    :raises OCUSException: If no MUS exists
    :raises AssertionError: If model is SAT
    """
    warnings.warn(
        "optimal_mus_naive() is deprecated and kept for compatibility; use optimal_mus().",
        DeprecationWarning,
        stacklevel=2,
    )

    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)

    # Default weights: all 1s (find smallest MUS)
    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")

    # Verify model is UNSAT
    assert is_unsat(soft, hard, solver, verbose), \
        "optimal_mus_naive: model must be UNSAT"

    best_combo: Optional[tuple[int, ...]] = None
    best_weight: Optional[Union[int, float]] = None

    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            combo_subset = [soft[i] for i in combo]
            if solve_subset(combo_subset, hard, solver, verbose) != SolveResult.UNSAT:
                continue

            is_minimal_subset = True
            for pos in range(len(combo)):
                reduced_combo = combo[:pos] + combo[pos + 1:]
                if not reduced_combo:
                    continue
                reduced_subset = [soft[i] for i in reduced_combo]
                if solve_subset(reduced_subset, hard, solver, verbose) == SolveResult.UNSAT:
                    is_minimal_subset = False
                    break
            if not is_minimal_subset:
                continue

            combo_weight = sum(w[i] for i in combo)
            if (
                best_weight is None
                or combo_weight < best_weight
                or (combo_weight == best_weight and (best_combo is None or combo < best_combo))
            ):
                best_weight = combo_weight
                best_combo = combo
                if verbose >= 0:
                    print(
                        f"optimal_mus_naive: candidate MUS size={len(combo)} weight={combo_weight}"
                    )

    if best_combo is None:
        raise OCUSException("No unsatisfiable subset could be found")

    return [soft[i] for i in best_combo]


def smus(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find the Smallest Minimal Unsatisfiable Subset (SMUS).

    This is equivalent to optimal_mus with all weights equal to 1.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: The smallest MUS
    """
    return optimal_mus(soft, hard, weights=None, solver=solver, verbose=verbose)


def optimal_mus(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1
) -> List[Any]:
    """
    Find an optimal MUS according to a linear objective function.

    Canonical implementation using an iterative hitting set loop:
    1. Generate correction subsets from satisfiable grows
    2. Solve a weighted hitting-set problem
    3. Validate/shrink UNSAT hitting sets to MUS

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint (default: all 1s = SMUS)
    :param solver: Solver name
    :param verbose: Verbosity level
    :return: An optimal MUS according to weights
    :raises OCUSException: If no MUS exists
    :raises AssertionError: If model is SAT

    Reference:
        Gamba, Emilio, Bart Bogaerts, and Tias Guns. "Efficiently explaining
        CSPs with unsatisfiable subset optimization."
        Journal of Artificial Intelligence Research 78 (2023): 709-746.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)

    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")

    assert is_unsat(soft, hard, solver, verbose), \
        "optimal_mus: model must be UNSAT"

    correction_subsets: List[set] = []

    while True:
        hitting_set = _find_optimal_hitting_set(
            n=n,
            correction_sets=correction_subsets,
            weights=w,
            solver=solver,
            verbose=verbose,
        )

        if hitting_set is None:
            raise OCUSException("No unsatisfiable subset could be found")

        hitting_set_list = sorted(hitting_set)
        subset = [soft[i] for i in hitting_set_list]

        if verbose >= 0:
            print(
                f"optimal_mus: testing hitting set of size {len(hitting_set)}, "
                f"weight {sum(w[i] for i in hitting_set)}"
            )

        result = solve_subset(subset, hard, solver, verbose)

        if result == SolveResult.UNSAT:
            mus_indices = set(hitting_set)
            ordered = sorted(mus_indices, key=lambda i: -w[i])

            for idx in ordered:
                if idx not in mus_indices:
                    continue
                mus_indices.remove(idx)
                test_subset = [soft[i] for i in sorted(mus_indices)]
                if not test_subset or is_sat(test_subset, hard, solver, verbose):
                    mus_indices.add(idx)

            return [soft[i] for i in range(n) if i in mus_indices]

        if result == SolveResult.SAT:
            mss_indices = set(hitting_set_list)

            for i in range(n):
                if i in mss_indices:
                    continue
                test_indices = sorted(mss_indices | {i})
                test_subset = [soft[j] for j in test_indices]
                if is_sat(test_subset, hard, solver, verbose):
                    mss_indices.add(i)

            correction_subset = set(range(n)) - mss_indices
            if not correction_subset:
                raise OCUSException("Model is SAT, no MUS exists")

            correction_subsets.append(correction_subset)

            if verbose >= 0:
                print(f"optimal_mus: found correction subset of size {len(correction_subset)}")
            continue

        raise OCUSException(f"Solver returned {result}")


def ocus(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1,
    subset_predicate: Optional[Callable[[Set[int]], bool]] = None,
    subset_constraints: Optional[Callable[[List[Any]], Any]] = None,
) -> List[Any]:
    """
    Find an Optimal Constrained Unsatisfiable Subset (OCUS).

    The constraint is defined over the selected subset of soft constraints.
    Use subset_constraints to encode the constraint as PyCSP3 constraints
    on selection variables (0/1). Optionally provide subset_predicate to
    validate subsets during shrinking and enumeration fallback.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint
    :param solver: Solver name
    :param verbose: Verbosity level
    :param subset_predicate: Python predicate on selected indices
    :param subset_constraints: Builder for PyCSP3 constraints on selection vars
    :return: An optimal constrained MUS according to weights
    :raises OCUSException: If no OCUS exists
    :raises AssertionError: If model is SAT
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)

    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")

    assert is_unsat(soft, hard, solver, verbose), \
        "ocus: model must be UNSAT"

    correction_subsets: List[Set[int]] = []

    subset_checker = _make_subset_checker(
        n=n,
        solver=solver,
        verbose=verbose,
        subset_predicate=subset_predicate,
        subset_constraints=subset_constraints,
    )

    while True:
        hitting_set = _find_optimal_hitting_set(
            n=n,
            correction_sets=correction_subsets,
            weights=w,
            solver=solver,
            verbose=verbose,
            subset_constraints=subset_constraints,
            subset_predicate=subset_predicate,
            subset_checker=subset_checker,
        )

        if hitting_set is None:
            raise OCUSException("No unsatisfiable subset could be found")

        hitting_set_list = sorted(hitting_set)
        subset = [soft[i] for i in hitting_set_list]

        if verbose >= 0:
            print(f"ocus: testing hitting set of size {len(hitting_set)}, "
                  f"weight {sum(w[i] for i in hitting_set)}")

        result = solve_subset(subset, hard, solver, verbose)

        if result == SolveResult.UNSAT:
            mus_indices = set(hitting_set)
            ordered = sorted(mus_indices, key=lambda i: -w[i])

            for idx in ordered:
                if idx not in mus_indices:
                    continue
                candidate = mus_indices - {idx}
                if not subset_checker(candidate):
                    continue
                mus_indices.remove(idx)
                test_subset = [soft[i] for i in sorted(mus_indices)]
                if not test_subset or is_sat(test_subset, hard, solver, verbose):
                    mus_indices.add(idx)

            return [soft[i] for i in range(n) if i in mus_indices]

        elif result == SolveResult.SAT:
            mss_indices = set(hitting_set_list)

            for i in range(n):
                if i in mss_indices:
                    continue
                test_indices = sorted(mss_indices | {i})
                test_subset = [soft[j] for j in test_indices]
                if is_sat(test_subset, hard, solver, verbose):
                    mss_indices.add(i)

            correction_subset = set(range(n)) - mss_indices
            if not correction_subset:
                raise OCUSException("Model is SAT, no MUS exists")

            correction_subsets.append(correction_subset)

            if verbose >= 0:
                print(f"ocus: found correction subset of size {len(correction_subset)}")

        else:
            raise OCUSException(f"Solver returned {result}")


def ocus_naive(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    weights: Optional[List[Union[int, float]]] = None,
    solver: str = "ace",
    verbose: int = -1,
    subset_predicate: Optional[Callable[[Set[int]], bool]] = None,
    subset_constraints: Optional[Callable[[List[Any]], Any]] = None,
) -> List[Any]:
    """
    Find an Optimal Constrained Unsatisfiable Subset (OCUS).

    Naive exhaustive implementation:
    enumerate all subsets, filter by optional subset constraints/predicate,
    keep constrained-minimal UNSAT subsets, and return the minimum-weight one.
    Kept for compatibility; use ocus() for the canonical implementation.

    :param soft: List of soft constraints
    :param hard: List of hard constraints
    :param weights: Weight for each soft constraint
    :param solver: Solver name
    :param verbose: Verbosity level
    :param subset_predicate: Python predicate on selected indices
    :param subset_constraints: Builder for PyCSP3 constraints on selection vars
    :return: An optimal constrained MUS according to weights
    :raises OCUSException: If no OCUS exists
    :raises AssertionError: If model is SAT
    """
    warnings.warn(
        "ocus_naive() is deprecated and kept for compatibility; use ocus().",
        DeprecationWarning,
        stacklevel=2,
    )

    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    n = len(soft)
    w: List[Union[int, float]] = weights if weights is not None else [1] * n
    if len(w) != n:
        raise ValueError(f"weights length ({len(w)}) must match soft length ({n})")

    assert is_unsat(soft, hard, solver, verbose), \
        "ocus_naive: model must be UNSAT"

    subset_checker = _make_subset_checker(
        n=n,
        solver=solver,
        verbose=verbose,
        subset_predicate=subset_predicate,
        subset_constraints=subset_constraints,
    )

    best_combo: Optional[tuple[int, ...]] = None
    best_weight: Optional[Union[int, float]] = None

    for size in range(1, n + 1):
        for combo in combinations(range(n), size):
            combo_set = set(combo)
            if not subset_checker(combo_set):
                continue

            combo_subset = [soft[i] for i in combo]
            if solve_subset(combo_subset, hard, solver, verbose) != SolveResult.UNSAT:
                continue

            is_minimal_subset = True
            for pos in range(len(combo)):
                reduced_combo = combo[:pos] + combo[pos + 1:]
                reduced_set = set(reduced_combo)
                if not subset_checker(reduced_set):
                    continue
                reduced_subset = [soft[i] for i in reduced_combo]
                if solve_subset(reduced_subset, hard, solver, verbose) == SolveResult.UNSAT:
                    is_minimal_subset = False
                    break

            if not is_minimal_subset:
                continue

            combo_weight = sum(w[i] for i in combo)
            if (
                best_weight is None
                or combo_weight < best_weight
                or (combo_weight == best_weight and (best_combo is None or combo < best_combo))
            ):
                best_combo = combo
                best_weight = combo_weight
                if verbose >= 0:
                    print(
                        f"ocus_naive: candidate OCUS size={len(combo)} weight={combo_weight}"
                    )

    if best_combo is None:
        raise OCUSException("No constrained unsatisfiable subset could be found")

    return [soft[i] for i in best_combo]
