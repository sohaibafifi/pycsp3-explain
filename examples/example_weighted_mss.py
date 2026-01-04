#!/usr/bin/env python3
"""
Example: Weighted MSS/MCS Optimization.

This example demonstrates how to use weighted MSS/MCS algorithms to find:
- mss_opt: MSS that maximizes total weight of satisfied constraints
- mcs_opt: MCS that minimizes total weight of removed constraints

Use case: When constraints have different importance/costs, we want to
maximize value of kept constraints or minimize cost of removed constraints.
"""

from pycsp3 import *
from pycsp3_explain.explain.mss import mss_opt, mcs_opt, mss_naive, mcs_naive


def main():
    print("=" * 70)
    print("Example: Weighted MSS/MCS Optimization")
    print("=" * 70)

    # Scenario: Resource allocation with constraints of varying importance
    # We have 3 resources and constraints with different priorities/costs
    print("\nScenario: Resource Allocation Problem")
    print("-" * 50)
    print("We have 3 resources (x0, x1, x2) with domain [0, 10].")
    print("Various stakeholders have constraints, each with a priority weight.")
    print("The constraints form an UNSAT system - we must relax some.")
    print()

    # Clear any previous model
    clear()

    # Create variables
    x = VarArray(size=3, dom=range(11))

    # Create constraints with different priorities (weights)
    # Higher weight = more important to keep
    constraints = []
    weights = []
    labels = []

    # High priority constraints (weight 10)
    c0 = x[0] >= 5
    constraints.append(c0)
    weights.append(10)
    labels.append("x[0] >= 5 (Safety requirement)")

    c1 = x[1] <= 8
    constraints.append(c1)
    weights.append(10)
    labels.append("x[1] <= 8 (Capacity limit)")

    # Medium priority constraints (weight 5)
    c2 = x[0] + x[1] <= 12
    constraints.append(c2)
    weights.append(5)
    labels.append("x[0] + x[1] <= 12 (Budget constraint)")

    c3 = x[2] >= 3
    constraints.append(c3)
    weights.append(5)
    labels.append("x[2] >= 3 (Minimum reserve)")

    # Low priority constraints (weight 1) - these create the conflict
    c4 = x[0] == 9
    constraints.append(c4)
    weights.append(1)
    labels.append("x[0] == 9 (Preferred allocation)")

    c5 = x[1] == 7
    constraints.append(c5)
    weights.append(1)
    labels.append("x[1] == 7 (Preferred allocation)")

    c6 = x[0] + x[1] == 10  # Conflicts with c4+c5 (9+7=16 != 10)
    constraints.append(c6)
    weights.append(1)
    labels.append("x[0] + x[1] == 10 (Target sum)")

    # Print constraints
    print("Constraints and their weights:")
    for i, (label, w) in enumerate(zip(labels, weights)):
        print(f"  c{i}: {label} [weight={w}]")

    print(f"\nTotal weight of all constraints: {sum(weights)}")

    # Helper to get constraint info
    def get_constraint_info(subset, all_constraints, all_weights, all_labels):
        """Get labels and weights for constraints in subset."""
        info = []
        total_weight = 0
        for c in subset:
            for j, orig_c in enumerate(all_constraints):
                if c is orig_c:
                    info.append((j, all_labels[j], all_weights[j]))
                    total_weight += all_weights[j]
                    break
        return info, total_weight

    def complement_constraints(subset, all_constraints):
        """Return constraints not in subset using identity comparison."""
        subset_ids = {id(c) for c in subset}
        return [c for c in all_constraints if id(c) not in subset_ids]

    # 1. Standard MSS (no weights - maximizes count)
    print("\n" + "=" * 70)
    print("1. Standard MSS (maximizes number of constraints)")
    print("=" * 70)

    mss_standard = mss_naive(constraints, solver="ace", verbose=-1)
    info, total = get_constraint_info(mss_standard, constraints, weights, labels)

    print(f"\nMSS contains {len(mss_standard)} constraints (total weight: {total}):")
    for idx, label, w in info:
        print(f"  c{idx}: {label} [w={w}]")

    mcs_standard = complement_constraints(mss_standard, constraints)
    info_mcs, total_mcs = get_constraint_info(mcs_standard, constraints, weights, labels)
    print(f"\nMCS (removed): {len(mcs_standard)} constraints (total weight: {total_mcs}):")
    for idx, label, w in info_mcs:
        print(f"  c{idx}: {label} [w={w}]")

    # 2. Weighted MSS (maximizes total weight)
    print("\n" + "=" * 70)
    print("2. Weighted MSS (maximizes total weight of kept constraints)")
    print("=" * 70)

    mss_weighted = mss_opt(constraints, weights=weights, solver="ace", verbose=-1)
    info, total = get_constraint_info(mss_weighted, constraints, weights, labels)

    print(f"\nWeighted MSS contains {len(mss_weighted)} constraints (total weight: {total}):")
    for idx, label, w in info:
        print(f"  c{idx}: {label} [w={w}]")

    mcs_weighted = complement_constraints(mss_weighted, constraints)
    info_mcs, total_mcs = get_constraint_info(mcs_weighted, constraints, weights, labels)
    print(f"\nWeighted MCS (removed): {len(mcs_weighted)} constraints (total weight: {total_mcs}):")
    for idx, label, w in info_mcs:
        print(f"  c{idx}: {label} [w={w}]")

    # 3. Direct MCS optimization (minimizes removal cost)
    print("\n" + "=" * 70)
    print("3. Weighted MCS (minimizes total weight of removed constraints)")
    print("=" * 70)

    mcs_opt_result = mcs_opt(constraints, weights=weights, solver="ace", verbose=-1)
    info_mcs, total_mcs = get_constraint_info(mcs_opt_result, constraints, weights, labels)

    print(f"\nOptimal MCS removes {len(mcs_opt_result)} constraints (total weight: {total_mcs}):")
    for idx, label, w in info_mcs:
        print(f"  c{idx}: {label} [w={w}]")

    remaining = complement_constraints(mcs_opt_result, constraints)
    info_remaining, total_remaining = get_constraint_info(remaining, constraints, weights, labels)
    print(f"\nRemaining constraints: {len(remaining)} (total weight: {total_remaining}):")
    for idx, label, w in info_remaining:
        print(f"  c{idx}: {label} [w={w}]")

    # 4. Comparison summary
    print("\n" + "=" * 70)
    print("Summary: Weighted vs Unweighted Optimization")
    print("=" * 70)

    _, std_kept_weight = get_constraint_info(mss_standard, constraints, weights, labels)
    _, std_removed_weight = get_constraint_info(
        complement_constraints(mss_standard, constraints),
        constraints, weights, labels
    )

    _, weighted_kept_weight = get_constraint_info(mss_weighted, constraints, weights, labels)
    _, weighted_removed_weight = get_constraint_info(
        complement_constraints(mss_weighted, constraints),
        constraints, weights, labels
    )

    print(f"\n{'Method':<25} {'Kept':<12} {'Removed':<12} {'Kept Weight':<15} {'Removed Weight'}")
    print("-" * 70)
    print(f"{'Standard MSS':<25} {len(mss_standard):<12} {len(constraints)-len(mss_standard):<12} {std_kept_weight:<15} {std_removed_weight}")
    print(f"{'Weighted MSS':<25} {len(mss_weighted):<12} {len(constraints)-len(mss_weighted):<12} {weighted_kept_weight:<15} {weighted_removed_weight}")

    print("\n" + "=" * 70)
    print("Key Insight:")
    print("  - Standard MSS maximizes the COUNT of satisfied constraints")
    print("  - Weighted MSS maximizes the TOTAL WEIGHT of satisfied constraints")
    print("  - Use weighted optimization when constraints have different importance")
    print("=" * 70)


if __name__ == "__main__":
    main()
