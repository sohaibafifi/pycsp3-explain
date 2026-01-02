#!/usr/bin/env python3
"""
Example: Finding a simple constraint conflict using MUS.

This example demonstrates how to use mus_naive to find the minimal
set of conflicting constraints in an infeasible model.
"""


from pycsp3 import *
from pycsp3_explain.explain.mus import mus_naive, is_mus


def main():
    print("=" * 60)
    print("Example: Simple Constraint Conflict Detection")
    print("=" * 60)

    # Clear any previous model
    clear()

    # Create variables
    print("\n1. Creating variables...")
    x = VarArray(size=3, dom=range(10))
    print(f"   Variables: x[0], x[1], x[2] with domain [0, 9]")

    # Create constraints
    print("\n2. Creating constraints...")

    c0 = x[0] == 5
    print(f"   c0: x[0] == 5")

    c1 = x[1] >= 3
    print(f"   c1: x[1] >= 3")

    c2 = x[0] + x[1] == 10
    print(f"   c2: x[0] + x[1] == 10")

    c3 = x[0] == 7
    print(f"   c3: x[0] == 7")

    c4 = x[2] <= 8
    print(f"   c4: x[2] <= 8")

    # The conflict is between c0 (x[0]==5) and c3 (x[0]==7)
    # c1, c2, c4 are independent and not part of the conflict

    soft_constraints = [c0, c1, c2, c3, c4]

    print("\n3. Finding Minimal Unsatisfiable Subset (MUS)...")
    print("   This identifies the minimal set of conflicting constraints.")

    mus = mus_naive(soft_constraints, solver="ace", verbose=-1)

    print(f"\n4. Result: MUS contains {len(mus)} constraint(s)")
    print("   Conflicting constraints:")
    for i, c in enumerate(mus):
        # Find original index
        for j, orig_c in enumerate(soft_constraints):
            if c is orig_c:
                print(f"   - c{j}: {['x[0] == 5', 'x[1] >= 3', 'x[0] + x[1] == 10', 'x[0] == 7', 'x[2] <= 8'][j]}")
                break

    print("\n5. Verifying the MUS...")
    if is_mus(mus, solver="ace", verbose=-1):
        print("   The MUS is valid (UNSAT and minimal)")
    else:
        print("   WARNING: The MUS verification failed")

    print("\n" + "=" * 60)
    print("Explanation:")
    print("  The MUS shows that x[0] cannot be both 5 AND 7.")
    print("  To fix the model, remove or modify one of these constraints.")
    print("=" * 60)


if __name__ == "__main__":
    main()
