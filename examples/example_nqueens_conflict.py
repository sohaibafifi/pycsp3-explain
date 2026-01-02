#!/usr/bin/env python3
"""
Example: N-Queens with impossible constraints.

This example shows how to use MUS to find conflicts when
adding impossible constraints to a classic N-Queens problem.
"""


from pycsp3 import *
from pycsp3_explain.explain.mus import mus_naive


def find_constraint_index(constraint, constraint_list):
    """Find index of constraint using identity comparison (avoids PyCSP3 __eq__ issues)."""
    for i, c in enumerate(constraint_list):
        if c is constraint:
            return i
    return -1


def main():
    print("=" * 60)
    print("Example: N-Queens with Conflicting Constraints")
    print("=" * 60)

    # Clear any previous model
    clear()

    n = 4  # 4-Queens problem
    print(f"\n1. Setting up {n}-Queens problem...")

    # Variables: q[i] = column of queen in row i
    q = VarArray(size=n, dom=range(n))

    print(f"   Variables: q[0..{n-1}] representing column positions")
    print(f"   Domain: [0, {n-1}]")

    # Standard N-Queens constraints
    print("\n2. Creating constraints...")

    constraints = []
    constraint_names = []

    # All queens in different columns
    c_cols = AllDifferent(q)
    constraints.append(c_cols)
    constraint_names.append("All queens in different columns")
    print(f"   c0: {constraint_names[-1]}")

    # All queens in different diagonals (up)
    c_diag_up = AllDifferent([q[i] + i for i in range(n)])
    constraints.append(c_diag_up)
    constraint_names.append("All queens in different up-diagonals")
    print(f"   c1: {constraint_names[-1]}")

    # All queens in different diagonals (down)
    c_diag_down = AllDifferent([q[i] - i for i in range(n)])
    constraints.append(c_diag_down)
    constraint_names.append("All queens in different down-diagonals")
    print(f"   c2: {constraint_names[-1]}")

    # Now add some impossible constraints
    print("\n3. Adding impossible constraints...")

    # Force queen 0 to column 0
    c_force_0 = q[0] == 0
    constraints.append(c_force_0)
    constraint_names.append("Queen 0 must be in column 0")
    print(f"   c3: {constraint_names[-1]}")

    # Force queen 1 to column 1 (creates diagonal conflict with q[0]=0)
    c_force_1 = q[1] == 1
    constraints.append(c_force_1)
    constraint_names.append("Queen 1 must be in column 1")
    print(f"   c4: {constraint_names[-1]}")

    # Force queen 2 to column 2 (creates more conflicts)
    c_force_2 = q[2] == 2
    constraints.append(c_force_2)
    constraint_names.append("Queen 2 must be in column 2")
    print(f"   c5: {constraint_names[-1]}")

    # Force queen 3 to column 3 (all on main diagonal!)
    c_force_3 = q[3] == 3
    constraints.append(c_force_3)
    constraint_names.append("Queen 3 must be in column 3")
    print(f"   c6: {constraint_names[-1]}")

    # This forces all queens on the main diagonal, violating c2

    print("\n4. Finding MUS...")
    print("\t4.1 Using mus_naive to identify conflicting constraints...")
    mus = mus_naive(constraints, solver="ace", verbose=-1)

    print(f"\n\tResult: Found {len(mus)} conflicting constraint(s)")
    print("   Minimal Unsatisfiable Subset:")
    for c in mus:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx}: {constraint_names[idx]}")



    print("\n\t4.2 using the quickxplain naive to identify preferred conflicting constraints...")
    from pycsp3_explain.explain.mus import quickxplain_naive
    qx_mus = quickxplain_naive(constraints, solver="ace", verbose=-1)
    print(f"\n\t Result: Found {len(qx_mus)} conflicting constraint(s)")
    print("   Preferred Minimal Unsatisfiable Subset:")
    for c in qx_mus:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx}: {constraint_names[idx]}")

    print("\n" + "=" * 60)
    print("Interpretation:")
    print("  The MUS shows that forcing queens to specific positions")
    print("  conflicts with the diagonal constraints.")
    print("")
    print("  When q[i] = i for all i, all queens are on the main diagonal,")
    print("  violating the AllDifferent constraint on down-diagonals.")
    print("=" * 60)



if __name__ == "__main__":
    main()
