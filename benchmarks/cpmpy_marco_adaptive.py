#!/usr/bin/env python3
"""
CPMPy-native MARCO-ADAPTIVE implementation for benchmark comparisons.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator, List, Literal, Optional, Set, Tuple

try:
    import cpmpy as cp
except ImportError:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "libs" / "cpmpy"))
    import cpmpy as cp
from cpmpy.tools.explain.utils import make_assump_model
from cpmpy.transformations.get_variables import get_variables


def marco_adaptive(
    soft,
    hard=None,
    solver: str = "ortools",
    map_solver: str = "ortools",
    return_mus: bool = True,
    return_mcs: bool = True,
    do_solution_hint: bool = True,
    handoff_threshold: Optional[int] = None,
    batch_base_ratio: int = 2,
    sat_backoff_cap: int = 8,
    feedback_enabled: bool = True,
    feedback_sat_clause_max: int = 12,
    feedback_unsat_clause_max: int = 12,
    feedback_max_clauses: int = 2000,
) -> Iterator[Tuple[Literal["MUS", "MCS"], List]]:
    """
    Enumerate MUSes and MCSes with a BiCore-QX-style MARCO variant, using CPMPy.

    Novel acceleration: stream internal SAT/UNSAT probe outcomes into the map solver.
    - SAT internal seed A => block_down(A)
    - UNSAT internal seed B => block_up(core(B) or B)
    with antichain filtering and gating to limit clause blow-up.
    """
    hard = [] if hard is None else hard

    assert hasattr(
        cp.SolverLookup.get(solver), "get_core"
    ), "marco_adaptive requires a solver that supports assumptions/core extraction"

    model, soft, assump = make_assump_model(soft, hard)
    dmap = dict(zip(assump, soft))
    sat_solver = cp.SolverLookup.get(solver, model)

    map_sat = cp.SolverLookup.get(map_solver)
    map_sat += cp.any(assump)

    do_solution_hint = do_solution_hint and hasattr(map_sat, "solution_hint")
    if do_solution_hint:
        hint = [1] * len(assump)
        map_sat.solution_hint(assump, hint)

    if handoff_threshold is None:
        handoff_threshold = max(8, len(assump) // 3)
    if handoff_threshold < 1:
        raise ValueError("handoff_threshold must be >= 1")
    if batch_base_ratio < 1:
        raise ValueError("batch_base_ratio must be >= 1")
    if sat_backoff_cap < 0:
        raise ValueError("sat_backoff_cap must be >= 0")
    if feedback_sat_clause_max < 0:
        raise ValueError("feedback_sat_clause_max must be >= 0")
    if feedback_unsat_clause_max < 0:
        raise ValueError("feedback_unsat_clause_max must be >= 0")

    deletion_order = {a: -len(get_variables(dmap[a])) for a in assump}
    known_muses: List[Set] = []
    known_mus_keys: Set[frozenset] = set()
    core_isect: Optional[Set] = None
    n_assump = len(assump)

    learned_clause_count = 0
    sat_maximal_sets: List[Set] = []
    unsat_minimal_sets: List[Set] = []
    sat_keyset: Set[frozenset] = set()
    unsat_keyset: Set[frozenset] = set()

    def _feedback_budget_exhausted() -> bool:
        if not feedback_enabled:
            return True
        if feedback_max_clauses <= 0:
            return False
        return learned_clause_count >= feedback_max_clauses

    def _block_down_sat_set(sat_set: Set, force: bool = False) -> bool:
        """
        Add block_down(sat_set) with antichain maintenance over SAT sets.
        Keep only maximal SAT sets (stronger clauses).
        """
        nonlocal learned_clause_count, sat_maximal_sets, map_sat

        sat_set = set(sat_set)
        clause_len = n_assump - len(sat_set)

        if not force:
            if _feedback_budget_exhausted():
                return False
            if clause_len > feedback_sat_clause_max:
                return False

        fs = frozenset(sat_set)
        if fs in sat_keyset:
            return False
        # Existing maximal superset already implies this block.
        if any(sat_set <= old for old in sat_maximal_sets):
            return False

        # Remove dominated strict subsets.
        kept: List[Set] = []
        for old in sat_maximal_sets:
            if old < sat_set:
                sat_keyset.discard(frozenset(old))
            else:
                kept.append(old)
        sat_maximal_sets = kept

        mcs = [a for a in assump if a not in sat_set]
        map_sat += cp.any(mcs)

        sat_maximal_sets.append(sat_set)
        sat_keyset.add(fs)
        if not force:
            learned_clause_count += 1
        return True

    def _block_up_unsat_set(unsat_set: Set, force: bool = False) -> bool:
        """
        Add block_up(unsat_set) with antichain maintenance over UNSAT sets.
        Keep only minimal UNSAT sets (stronger clauses).
        """
        nonlocal learned_clause_count, unsat_minimal_sets, map_sat

        unsat_set = set(unsat_set)
        if not force:
            if _feedback_budget_exhausted():
                return False
            if len(unsat_set) > feedback_unsat_clause_max:
                return False

        fu = frozenset(unsat_set)
        if fu in unsat_keyset:
            return False
        # Existing smaller UNSAT set already implies this block.
        if any(old <= unsat_set for old in unsat_minimal_sets):
            return False

        # Remove dominated strict supersets.
        kept: List[Set] = []
        for old in unsat_minimal_sets:
            if unsat_set < old:
                unsat_keyset.discard(frozenset(old))
            else:
                kept.append(old)
        unsat_minimal_sets = kept

        map_sat += ~cp.all(list(unsat_set))

        unsat_minimal_sets.append(unsat_set)
        unsat_keyset.add(fu)
        if not force:
            learned_clause_count += 1
        return True

    def solve_seed(seed_assump: List, want_core: bool = False, learn_feedback: bool = True):
        is_sat = sat_solver.solve(assumptions=seed_assump)
        core = None

        if is_sat is False:
            need_core = want_core or (learn_feedback and feedback_enabled and not _feedback_budget_exhausted())
            if need_core:
                core = list(sat_solver.get_core())
            if learn_feedback and feedback_enabled and not _feedback_budget_exhausted():
                learned_unsat = set(core) if core else set(seed_assump)
                _block_up_unsat_set(learned_unsat, force=False)
        elif is_sat is True:
            if learn_feedback and feedback_enabled and not _feedback_budget_exhausted():
                _block_down_sat_set(set(seed_assump), force=False)

        return is_sat, core

    def update_core_intersection(seed_set: Set, core_list: Optional[List]) -> None:
        nonlocal core_isect
        if not core_list:
            return
        core_set = set(core_list) & seed_set
        if not core_set:
            return
        if core_isect is None:
            core_isect = set(core_set)
        else:
            core_isect &= core_set

    def shrink_to_mus_deletion(
        seed_set: Set,
        initial_core: Optional[Set] = None,
        locked: Optional[Set] = None,
    ) -> Set:
        if initial_core:
            mus_set = set(initial_core) & seed_set
            if not mus_set:
                mus_set = set(seed_set)
        else:
            mus_set = set(seed_set)

        locked_set = set(locked) if locked else set()
        ordered = sorted(mus_set, key=lambda a: deletion_order.get(a, 0))

        for a in ordered:
            if a not in mus_set or a in locked_set:
                continue

            mus_set.remove(a)
            if not mus_set:
                mus_set.add(a)
                continue

            is_sat, core = solve_seed(list(mus_set), want_core=True)

            if is_sat is True:
                mus_set.add(a)
            elif is_sat is False:
                if core:
                    refined = set(core) & mus_set
                    if refined:
                        mus_set = refined
                        locked_set &= mus_set
            else:
                mus_set.add(a)

        return mus_set

    def preshrink_seed(seed_set: Set, seed_core: Optional[Set]) -> Set:
        projected = set(seed_set)
        for known_mus in sorted(known_muses, key=len):
            if known_mus <= seed_set:
                projected = set(known_mus)
                if seed_core:
                    projected |= (seed_core & seed_set)
                break
        return projected

    def shrink_to_mus_bicore_qx(seed_set: Set, seed_core: Optional[Set]) -> Set:
        projected_seed = preshrink_seed(seed_set, seed_core)

        if seed_core:
            current = set(seed_core) & projected_seed
            if not current:
                current = set(projected_seed)
        else:
            current = set(projected_seed)

        if not current:
            current = set(seed_set)

        locked = set(core_isect & current) if core_isect else set()
        batch_queue: List[Set] = []
        consecutive_sat = 0

        while True:
            unlocked = [a for a in current if a not in locked]
            if len(unlocked) <= handoff_threshold:
                break

            batch = None
            while batch_queue and batch is None:
                queued = batch_queue.pop()
                queued = {a for a in queued if a in current and a not in locked}
                if queued:
                    batch = queued

            if batch is None:
                available = sorted(unlocked, key=lambda a: deletion_order.get(a, 0))
                if not available:
                    break
                exp = min(consecutive_sat, sat_backoff_cap)
                divisor = min(batch_base_ratio * (2 ** exp), len(available))
                batch_size = max(1, len(available) // divisor)
                batch = set(available[:batch_size])

            test_set = set(current) - batch
            if not test_set:
                if len(batch) == 1:
                    locked |= batch
                    continue
                ordered_batch = sorted(batch, key=lambda a: deletion_order.get(a, 0))
                split = len(ordered_batch) // 2
                left = set(ordered_batch[:split])
                right = set(ordered_batch[split:])
                if left:
                    batch_queue.append(left)
                if right:
                    batch_queue.append(right)
                continue

            is_sat, core = solve_seed(list(test_set), want_core=True)

            if is_sat is False:
                consecutive_sat = 0
                if core:
                    refined = {a for a in core if a in test_set}
                    current = refined if refined else set(test_set)
                else:
                    current = set(test_set)
                locked &= current
                continue

            if is_sat is True:
                consecutive_sat += 1
                if len(batch) == 1:
                    locked |= batch
                    continue
                ordered_batch = sorted(batch, key=lambda a: deletion_order.get(a, 0))
                split = len(ordered_batch) // 2
                left = set(ordered_batch[:split])
                right = set(ordered_batch[split:])
                if left:
                    batch_queue.append(left)
                if right:
                    batch_queue.append(right)
                continue

            return shrink_to_mus_deletion(current, locked=locked)

        residual = sorted(current, key=lambda a: deletion_order.get(a, 0))
        if not residual:
            return set()

        locked_residual = [a for a in residual if a in locked]
        unlocked_residual = [a for a in residual if a not in locked]

        def qx_unsat(enabled: List) -> bool:
            qx_sat, _ = solve_seed(enabled, want_core=False, learn_feedback=True)
            return qx_sat is False

        def qx_recursive(soft_part: List, hard_part: List, delta: List) -> List:
            if delta and qx_unsat(hard_part):
                return []
            if len(soft_part) == 1:
                return list(soft_part)

            split = len(soft_part) // 2
            left = soft_part[:split]
            right = soft_part[split:]

            delta2 = qx_recursive(right, hard_part + left, left)
            delta1 = qx_recursive(left, hard_part + delta2, delta2)
            return delta1 + delta2

        if unlocked_residual:
            qx_part = qx_recursive(unlocked_residual, list(locked_residual), [])
            mus_set = set(locked_residual) | set(qx_part)
        else:
            mus_set = set(locked_residual)

        return shrink_to_mus_deletion(mus_set)

    def grow_to_mss(seed: List) -> List:
        seed_set = set(seed)
        mss = [a for a, c in zip(assump, soft) if (a in seed_set) or c.value()]
        mss_set = set(mss)
        for to_add in assump:
            if to_add in mss_set:
                continue
            trial_sat, _ = solve_seed(mss + [to_add], want_core=False, learn_feedback=True)
            if trial_sat is True:
                mss.append(to_add)
                mss_set.add(to_add)
        return mss

    while map_sat.solve():
        seed = [a for a in assump if a.value()]
        seed_set = set(seed)

        is_sat, core = solve_seed(seed, want_core=True)

        if is_sat is True:
            mss = grow_to_mss(seed)
            mss_set = set(mss)
            mcs = [a for a in assump if a not in mss_set]
            _block_down_sat_set(mss_set, force=True)

            if return_mcs:
                yield "MCS", [dmap[a] for a in mcs]

        elif is_sat is False:
            core_set = (set(core) & seed_set) if core else None
            update_core_intersection(seed_set, core)
            mus_set = shrink_to_mus_bicore_qx(seed_set, core_set)
            _block_up_unsat_set(mus_set, force=True)

            mus_key = frozenset(mus_set)
            if mus_key not in known_mus_keys:
                known_mus_keys.add(mus_key)
                known_muses.append(set(mus_set))

            if return_mus:
                yield "MUS", [dmap[a] for a in mus_set]

        else:
            # UNKNOWN: avoid stalling by taking SAT-side blocking.
            mss = grow_to_mss(seed)
            mss_set = set(mss)
            mcs = [a for a in assump if a not in mss_set]
            _block_down_sat_set(mss_set, force=True)
            if return_mcs:
                yield "MCS", [dmap[a] for a in mcs]

        if do_solution_hint:
            map_sat.solution_hint(assump, hint)
