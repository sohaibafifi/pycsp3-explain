#!/usr/bin/env python3
"""
Example: Debugging a scheduling conflict using MUS.

This example shows how MUS can help debug an infeasible scheduling problem
where tasks have conflicting time constraints.
"""


from pycsp3 import *
from pycsp3_explain.explain.mus import mus, mus_naive, quickxplain_naive, optimal_mus
from pycsp3_explain.explain.marco import marco


def find_constraint_index(constraint, constraint_list):
    """Find index of constraint using identity comparison (avoids PyCSP3 __eq__ issues)."""
    for i, c in enumerate(constraint_list):
        if c is constraint:
            return i
    return -1


def main():
    print("=" * 60)
    print("Example: Scheduling Conflict Detection")
    print("=" * 60)

    # Clear any previous model
    clear()

    # Scenario: 3 tasks need to be scheduled
    # Each task has a start time variable
    print("\nCreating scheduling problem...")

    # Task start times (0-23 hours)
    task_a_start = Var(dom=range(24))
    task_b_start = Var(dom=range(24))
    task_c_start = Var(dom=range(24))

    # Task durations
    duration_a = 3
    duration_b = 4
    duration_c = 2

    print(f"   Task A: duration {duration_a} hours")
    print(f"   Task B: duration {duration_b} hours")
    print(f"   Task C: duration {duration_c} hours")

    # Constraints
    print("\nCreating constraints...")

    constraints = []
    constraint_names = []
    weights = []

    # Task A must start before 10am
    c1 = task_a_start <= 10
    constraints.append(c1)
    constraint_names.append("Task A must start by 10am")
    weights.append(5)
    print(f"   c1: {constraint_names[-1]}")

    # Task B must start after 6pm (18:00)
    c2 = task_b_start >= 18
    constraints.append(c2)
    constraint_names.append("Task B must start at/after 6pm")
    weights.append(20)
    print(f"   c2: {constraint_names[-1]}")

    # Task C must overlap with Task A
    # (C starts during A, or A starts during C)
    c3 = task_c_start >= task_a_start
    constraints.append(c3)
    constraint_names.append("Task C must start at/after Task A")
    weights.append(3)
    print(f"   c3: {constraint_names[-1]}")

    c4 = task_c_start <= task_a_start + duration_a
    constraints.append(c4)
    constraint_names.append("Task C must start before Task A ends")
    weights.append(3)
    print(f"   c4: {constraint_names[-1]}")

    # Task B must start right after Task A ends
    c5 = task_b_start == task_a_start + duration_a
    constraints.append(c5)
    constraint_names.append("Task B must start when Task A ends")
    weights.append(10)
    print(f"   c5: {constraint_names[-1]}")

    # Task C must be done before Task B starts
    c6 = task_c_start + duration_c <= task_b_start
    constraints.append(c6)
    constraint_names.append("Task C must finish before Task B starts")
    weights.append(2)
    print(f"   c6: {constraint_names[-1]}")

    # The conflict:
    # - A starts <= 10, so A ends <= 13
    # - B starts right after A (c5), so B starts <= 13
    # - But B must start >= 18 (c2)
    # This is the core conflict!

    print("\n1. Finding MUS with mus (assumption-based)...")
    mus_fast = mus(constraints, solver="ace", verbose=-1)

    print(f"\n\tResult: Found {len(mus_fast)} conflicting constraint(s)")
    print("   Minimal Unsatisfiable Subset:")
    for c in mus_fast:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx+1}: {constraint_names[idx]}")

    print("\n2. Finding MUS with mus_naive...")
    mus_slow = mus_naive(constraints, solver="ace", verbose=-1)

    print(f"\n\tNaive Result: Found {len(mus_slow)} conflicting constraint(s)")
    for c in mus_slow:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx+1}: {constraint_names[idx]}")

    same = set(id(c) for c in mus_fast) == set(id(c) for c in mus_slow)
    print("\nComparison:")
    print("   Same constraints:" if same else "   Different MUSes (both minimal)")

    print("\n3. Finding preferred MUS with QuickXplain...")
    print("   (Prefers earlier constraints in case of multiple MUSes)")
    qx_mus = quickxplain_naive(constraints, solver="ace", verbose=-1)

    print(f"\n\tQuickXplain Result: {len(qx_mus)} constraint(s)")
    for c in qx_mus:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx+1}: {constraint_names[idx]}")

    print("\n4. Finding optimal MUS with weights...")
    optimal = optimal_mus(constraints, weights=weights, solver="ace", verbose=-1)
    total_weight = 0
    print("   Optimal MUS (minimum total weight):")
    for c in optimal:
        idx = find_constraint_index(c, constraints)
        weight = weights[idx]
        total_weight += weight
        print(f"   - c{idx+1}: {constraint_names[idx]} [w={weight}]")
    print(f"   Total weight: {total_weight}")

    print("\n5. Enumerating all MUSes and MCSes with MARCO...")
    def format_subset(subset):
        parts = []
        for c in subset:
            idx = find_constraint_index(c, constraints)
            if idx >= 0:
                parts.append(f"c{idx+1}: {constraint_names[idx]}")
        return ", ".join(parts)

    mus_count = 0
    mcs_count = 0
    for result_type, subset in marco(constraints, solver="ace", verbose=-1):
        if result_type == "MUS":
            mus_count += 1
            print(f"   MUS #{mus_count}: {{{format_subset(subset)}}}")
        else:
            mcs_count += 1
            print(f"   MCS #{mcs_count}: {{{format_subset(subset)}}}")
    print(f"   Total: {mus_count} MUSes, {mcs_count} MCSes")

    print("\n" + "=" * 60)
    print("Interpretation:")
    print("  The MUS reveals the core scheduling conflict.")
    print("  Optimal MUS uses weights to focus on low-cost constraints to relax.")
    print("  MARCO enumerates all MUSes and MCSes to explore alternative fixes.")
    print("  To fix the problem, you could:")
    print("  1. Allow Task A to start later")
    print("  2. Allow Task B to start earlier")
    print("  3. Remove the constraint that B follows A immediately")
    print("=" * 60)


if __name__ == "__main__":
    main()
