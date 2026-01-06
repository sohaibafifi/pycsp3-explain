#!/usr/bin/env python3
"""
Example: Finding Optimal and Smallest MUS using SMUS and weighted optimization.

This example demonstrates:
1. smus() - Find the Smallest MUS (minimum number of constraints)
2. optimal_mus() - Find optimal MUS according to custom weights

These algorithms are useful when:
- You want the simplest explanation (smallest MUS)
- Some constraints are more important/costly to violate than others
- You're looking for the most likely source of error
"""

from pycsp3 import *
from pycsp3_explain import smus, optimal_mus, ocus, is_mus


def main():
    print("=" * 70)
    print("Example: Optimal MUS - Finding the Best Explanation")
    print("=" * 70)

    # =========================================================================
    # Scenario: A scheduling problem with conflicts
    # =========================================================================
    print("""
Scenario: Employee Scheduling Conflict
---------------------------------------
We have constraints about when employees can work:
- Some constraints are from employee preferences (lower priority)
- Some constraints are from legal requirements (higher priority)
- Some constraints are from business needs (medium priority)

When there's a conflict, we want to identify which constraints to review.
""")

    # Clear any previous model
    clear()

    # Create variables representing work hours
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")

    print("Variables:")
    print("   alice_hours: Hours Alice works (0-49)")
    print("   bob_hours: Hours Bob works (0-49)")

    # Create constraints with different priorities
    print("\nConstraints (with importance weights):")

    # Legal requirements (high weight = 100)
    c0 = alice_hours <= 40  # Max 40 hours
    print("   c0: alice_hours <= 40  (Legal: max hours)        [weight: 100]")

    c1 = bob_hours <= 40
    print("   c1: bob_hours <= 40    (Legal: max hours)        [weight: 100]")

    # Business needs (medium weight = 10)
    c2 = alice_hours + bob_hours >= 70  # Need at least 70 total hours
    print("   c2: alice + bob >= 70  (Business: minimum staff) [weight: 10]")

    # Employee preferences (low weight = 1)
    c3 = alice_hours <= 30  # Alice prefers max 30 hours
    print("   c3: alice_hours <= 30  (Preference: Alice)       [weight: 1]")

    c4 = bob_hours <= 25  # Bob prefers max 25 hours
    print("   c4: bob_hours <= 25    (Preference: Bob)         [weight: 1]")

    soft_constraints = [c0, c1, c2, c3, c4]
    constraint_names = [
        "alice_hours <= 40 (Legal)",
        "bob_hours <= 40 (Legal)",
        "alice + bob >= 70 (Business)",
        "alice_hours <= 30 (Pref)",
        "bob_hours <= 25 (Pref)",
    ]
    weights = [100, 10, 10, 1, 1]

    print("\nConflict Analysis:")
    print("   If Alice works max 30 (c3) and Bob works max 25 (c4),")
    print("   total is max 55, but we need at least 70 (c2). Conflict!")

    def print_mus(title, mus_result, show_weights=False):
        print(f"\n{title}")
        print(f"   MUS size: {len(mus_result)} constraints")
        total_weight = 0
        for c in mus_result:
            for i, orig in enumerate(soft_constraints):
                if c is orig:
                    w = weights[i]
                    total_weight += w
                    if show_weights:
                        print(f"      - c{i}: {constraint_names[i]} [weight: {w}]")
                    else:
                        print(f"      - c{i}: {constraint_names[i]}")
                    break
        if show_weights:
            print(f"   Total weight: {total_weight}")
        valid = is_mus(mus_result, solver="ace", verbose=-1)
        print(f"   Valid MUS: {valid}")

    # =========================================================================
    # Method 1: Find the smallest MUS (fewest constraints)
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 1: SMUS - Find Smallest MUS")
    print("-" * 70)

    clear()
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")
    c0 = alice_hours <= 40
    c1 = bob_hours <= 40
    c2 = alice_hours + bob_hours >= 70
    c3 = alice_hours <= 30
    c4 = bob_hours <= 25
    soft_constraints = [c0, c1, c2, c3, c4]

    smallest_mus = smus(soft_constraints, solver="ace", verbose=-1)
    print_mus("Smallest MUS (minimum number of constraints):", smallest_mus)

    print("\n   Interpretation: This shows the simplest conflict in the model.")

    # =========================================================================
    # Method 2: Find optimal MUS with weights
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 2: Weighted Optimal MUS")
    print("-" * 70)

    clear()
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")
    c0 = alice_hours <= 40
    c1 = bob_hours <= 40
    c2 = alice_hours + bob_hours >= 70
    c3 = alice_hours <= 30
    c4 = bob_hours <= 25
    soft_constraints = [c0, c1, c2, c3, c4]
    weights = [100, 100, 10, 1, 1]

    weighted_mus = optimal_mus(soft_constraints, weights=weights, solver="ace", verbose=-1)
    print_mus("Optimal MUS (minimum total weight):", weighted_mus, show_weights=True)

    print("\n   Interpretation: This MUS has the lowest total weight,")
    print("   suggesting these low-priority constraints are the issue.")

    # =========================================================================
    # Method 3: OCUS with additional constraints
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 3: OCUS with Required Constraint")
    print("-" * 70)

    clear()
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")
    c0 = alice_hours <= 40
    c1 = bob_hours <= 40
    c2 = alice_hours + bob_hours >= 70
    c3 = alice_hours <= 30
    c4 = bob_hours <= 25
    soft_constraints = [c0, c1, c2, c3, c4]
    weights = [100, 100, 10, 1, 1]

    def require_business(select):
        return [select[2] == 1]

    def require_business_pred(indices):
        return 2 in indices

    constrained_mus = ocus(
        soft_constraints,
        weights=weights,
        solver="ace",
        verbose=-1,
        subset_constraints=require_business,
        subset_predicate=require_business_pred,
    )
    print_mus("OCUS (must include business constraint c2):", constrained_mus, show_weights=True)

    print("\n   Interpretation: This keeps the business requirement in the explanation.")

    # =========================================================================
    # Method 4: Compare different weight schemes
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 4: Impact of Different Weight Schemes")
    print("-" * 70)

    # Scheme A: All equal weights (same as SMUS)
    clear()
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")
    c0 = alice_hours <= 40
    c1 = bob_hours <= 40
    c2 = alice_hours + bob_hours >= 70
    c3 = alice_hours <= 30
    c4 = bob_hours <= 25
    soft_constraints = [c0, c1, c2, c3, c4]

    equal_weights = [1, 1, 1, 1, 1]
    mus_equal = optimal_mus(soft_constraints, weights=equal_weights, solver="ace", verbose=-1)
    print(f"\n   Equal weights [1,1,1,1,1]:")
    print(f"      MUS size: {len(mus_equal)}, constraints: ", end="")
    for c in mus_equal:
        for i, orig in enumerate(soft_constraints):
            if c is orig:
                print(f"c{i}", end=" ")
    print()

    # Scheme B: Prioritize legal requirements
    clear()
    alice_hours = Var(dom=range(0, 50), id="alice_hours")
    bob_hours = Var(dom=range(0, 50), id="bob_hours")
    c0 = alice_hours <= 40
    c1 = bob_hours <= 40
    c2 = alice_hours + bob_hours >= 70
    c3 = alice_hours <= 30
    c4 = bob_hours <= 25
    soft_constraints = [c0, c1, c2, c3, c4]

    legal_priority = [100, 100, 10, 1, 1]
    mus_legal = optimal_mus(soft_constraints, weights=legal_priority, solver="ace", verbose=-1)
    print(f"\n   Legal priority [100,100,10,1,1]:")
    print(f"      MUS size: {len(mus_legal)}, constraints: ", end="")
    for c in mus_legal:
        for i, orig in enumerate(soft_constraints):
            if c is orig:
                print(f"c{i}", end=" ")
    print()

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    print("""
   - smus() finds the MUS with fewest constraints
   - optimal_mus(weights) finds the MUS with minimum total weight
   - ocus(...) lets you require constraints in the explanation

   Use cases:
   - SMUS: When you want the simplest explanation
   - Weighted: When some constraints are more important to preserve
   - OCUS: When you must keep or avoid specific constraints

   In our scheduling example:
   - The conflict is between employee preferences and business needs
   - Weighted MUS points to preferences as the likely constraints to relax
   - OCUS keeps the business requirement in the explanation
""")
    print("=" * 70)


if __name__ == "__main__":
    main()
