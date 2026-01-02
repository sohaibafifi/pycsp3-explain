#!/usr/bin/env python3
"""
Example: Finding a simple constraint conflict using MUS.

This example demonstrates how to compare mus (assumption-based) and
mus_naive to find the minimal set of conflicting constraints in an
infeasible model.
"""


from pycsp3 import *
from pycsp3_explain.explain.mus import mus, mus_naive, is_mus


def main():
    print("=" * 60)
    print("Example: Simple Constraint Conflict Detection")
    print("=" * 60)

    # Clear any previous model
    clear()

    # Create variables
    print("\nCreating variables...")
    x = VarArray(size=3, dom=range(10))
    print(f"   Variables: x[0], x[1], x[2] with domain [0, 9]")

    # Create constraints
    print("\nCreating constraints...")

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
    constraint_labels = [
        "x[0] == 5",
        "x[1] >= 3",
        "x[0] + x[1] == 10",
        "x[0] == 7",
        "x[2] <= 8",
    ]

    def print_mus_result(title, mus_set):
        print(f"\n{title}: MUS contains {len(mus_set)} constraint(s)")
        print("   Conflicting constraints:")
        for c in mus_set:
            for j, orig_c in enumerate(soft_constraints):
                if c is orig_c:
                    print(f"   - c{j}: {constraint_labels[j]}")
                    break
        print("   Verification:", "valid" if is_mus(mus_set, solver="ace", verbose=-1) else "invalid")

    print("\n1. Finding MUS with mus (assumption-based)...")
    mus_assump = mus(soft_constraints, solver="ace", verbose=-1)
    print_mus_result("\tAssumption-based result", mus_assump)

    print("\n2. Finding MUS with mus_naive...")
    mus_slow = mus_naive(soft_constraints, solver="ace", verbose=-1)
    print_mus_result("\tNaive result", mus_slow)
    same = set(id(c) for c in mus_assump) == set(id(c) for c in mus_slow)
    print("\nComparison:")
    print("   Same constraints:" if same else "   Different MUSes (both minimal)")

    print("\n" + "=" * 60)
    print("Explanation:")
    print("  The MUS shows that x[0] cannot be both 5 AND 7.")
    print("  To fix the model, remove or modify one of these constraints.")
    print("=" * 60)


if __name__ == "__main__":
    main()
