#!/usr/bin/env python3
"""
Example: N-Queens with impossible constraints.

This example shows how to use MUS to find conflicts when
adding impossible constraints to a classic N-Queens problem.
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
    print("Example: N-Queens with Conflicting Constraints")
    print("=" * 60)

    # Clear any previous model
    clear()

    n = 4  # 4-Queens problem
    print(f"\nSetting up {n}-Queens problem...")

    # Variables: q[i] = column of queen in row i
    q = VarArray(size=n, dom=range(n))

    print(f"   Variables: q[0..{n-1}] representing column positions")
    print(f"   Domain: [0, {n-1}]")

    # Standard N-Queens constraints
    print("\nCreating constraints...")

    constraints = []
    constraint_names = []
    weights = []

    # All queens in different columns
    c_cols = AllDifferent(q)
    constraints.append(c_cols)
    constraint_names.append("All queens in different columns")
    weights.append(50)
    print(f"   c0: {constraint_names[-1]}")

    # All queens in different diagonals (up)
    c_diag_up = AllDifferent([q[i] + i for i in range(n)])
    constraints.append(c_diag_up)
    constraint_names.append("All queens in different up-diagonals")
    weights.append(50)
    print(f"   c1: {constraint_names[-1]}")

    # All queens in different diagonals (down)
    c_diag_down = AllDifferent([q[i] - i for i in range(n)])
    constraints.append(c_diag_down)
    constraint_names.append("All queens in different down-diagonals")
    weights.append(50)
    print(f"   c2: {constraint_names[-1]}")

    # Now add some impossible constraints
    print("\nAdding impossible constraints...")

    # Force queen 0 to column 0
    c_force_0 = q[0] == 0
    constraints.append(c_force_0)
    constraint_names.append("Queen 0 must be in column 0")
    weights.append(5)
    print(f"   c3: {constraint_names[-1]}")

    # Force queen 1 to column 1 (creates diagonal conflict with q[0]=0)
    c_force_1 = q[1] == 1
    constraints.append(c_force_1)
    constraint_names.append("Queen 1 must be in column 1")
    weights.append(1)
    print(f"   c4: {constraint_names[-1]}")

    # Force queen 2 to column 2 (creates more conflicts)
    c_force_2 = q[2] == 2
    constraints.append(c_force_2)
    constraint_names.append("Queen 2 must be in column 2")
    weights.append(2)
    print(f"   c5: {constraint_names[-1]}")

    # Force queen 3 to column 3 (all on main diagonal!)
    c_force_3 = q[3] == 3
    constraints.append(c_force_3)
    constraint_names.append("Queen 3 must be in column 3")
    weights.append(3)
    print(f"   c6: {constraint_names[-1]}")

    # This forces all queens on the main diagonal, violating c2

    print("\nFinding MUS...")
    print("\t1 Using mus (assumption-based) to identify conflicting constraints...")
    mus_fast = mus(constraints, solver="ace", verbose=-1)

    print(f"\n\tResult: Found {len(mus_fast)} conflicting constraint(s)")
    print("   Minimal Unsatisfiable Subset:")
    for c in mus_fast:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx}: {constraint_names[idx]}")

    print("\n\t2 Using mus_naive to identify conflicting constraints...")
    mus_slow = mus_naive(constraints, solver="ace", verbose=-1)

    print(f"\n\tResult: Found {len(mus_slow)} conflicting constraint(s)")
    print("   Minimal Unsatisfiable Subset:")
    for c in mus_slow:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx}: {constraint_names[idx]}")

    same = set(id(c) for c in mus_fast) == set(id(c) for c in mus_slow)
    print("\nComparison:")
    print("\t   Same constraints:" if same else "\t   Different MUSes (both minimal)")

    print("\n\t3 using the quickxplain naive to identify preferred conflicting constraints...")
    qx_mus = quickxplain_naive(constraints, solver="ace", verbose=-1)
    print(f"\n\t Result: Found {len(qx_mus)} conflicting constraint(s)")
    print("   Preferred Minimal Unsatisfiable Subset:")
    for c in qx_mus:
        idx = find_constraint_index(c, constraints)
        print(f"   - c{idx}: {constraint_names[idx]}")

    print("\n\t4 using optimal_mus to prioritize low-weight conflicts...")
    optimal = optimal_mus(constraints, weights=weights, solver="ace", verbose=-1)
    total_weight = 0
    print("   Optimal MUS (minimum total weight):")
    for c in optimal:
        idx = find_constraint_index(c, constraints)
        weight = weights[idx]
        total_weight += weight
        print(f"   - c{idx}: {constraint_names[idx]} [w={weight}]")
    print(f"   Total weight: {total_weight}")

    print("\n\t5 using MARCO to enumerate all MUSes and MCSes...")
    def format_subset(subset):
        parts = []
        for c in subset:
            idx = find_constraint_index(c, constraints)
            if idx >= 0:
                parts.append(f"c{idx}: {constraint_names[idx]}")
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
    print("  The MUS shows that forcing queens to specific positions")
    print("  conflicts with the diagonal constraints.")
    print("  Optimal MUS uses weights to highlight the most likely bad constraints.")
    print("  MARCO enumerates all MUSes and MCSes to explore alternatives.")
    print("")
    print("  When q[i] = i for all i, all queens are on the main diagonal,")
    print("  violating the AllDifferent constraint on down-diagonals.")
    print("=" * 60)



if __name__ == "__main__":
    main()
