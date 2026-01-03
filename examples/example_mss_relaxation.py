#!/usr/bin/env python3
"""
Example: Finding a Maximal Satisfiable Subset (MSS) and Minimal Correction Set (MCS).

This example demonstrates how to use MSS/MCS algorithms to find:
- MSS: The maximum set of constraints that can be satisfied together
- MCS: The minimum set of constraints that must be removed to restore satisfiability

These are dual concepts: MCS = Soft \\ MSS
"""


from pycsp3 import *
from pycsp3_explain.explain.mss import mss, mss_naive, mcs_naive, is_mss, is_mcs


def main():
    print("=" * 60)
    print("Example: MSS/MCS for Constraint Relaxation")
    print("=" * 60)

    # Clear any previous model
    clear()

    # Create variables
    print("\nCreating variables...")
    x = VarArray(size=3, dom=range(10))
    print(f"   Variables: x[0], x[1], x[2] with domain [0, 9]")

    # Create constraints - some are in conflict
    print("\nCreating constraints...")

    c0 = x[0] == 5
    print(f"   c0: x[0] == 5")

    c1 = x[1] >= 3
    print(f"   c1: x[1] >= 3")

    c2 = x[0] + x[1] == 10
    print(f"   c2: x[0] + x[1] == 10")

    c3 = x[0] == 7
    print(f"   c3: x[0] == 7  (conflicts with c0)")

    c4 = x[2] <= 8
    print(f"   c4: x[2] <= 8")

    soft_constraints = [c0, c1, c2, c3, c4]
    constraint_labels = [
        "x[0] == 5",
        "x[1] >= 3",
        "x[0] + x[1] == 10",
        "x[0] == 7",
        "x[2] <= 8",
    ]

    def label_constraints(constraints):
        """Get labels for a set of constraints."""
        labels = []
        for c in constraints:
            for j, orig_c in enumerate(soft_constraints):
                if c is orig_c:
                    labels.append(f"c{j}: {constraint_labels[j]}")
                    break
        return labels

    # Find MSS (naive)
    print("\n" + "-" * 40)
    print("1. Finding MSS with mss_naive...")
    mss_result = mss_naive(soft_constraints, solver="ace", verbose=-1)

    print(f"\n   MSS contains {len(mss_result)} constraint(s):")
    for label in label_constraints(mss_result):
        print(f"     - {label}")
    print(f"   Verification: {'valid MSS' if is_mss(mss_result, soft_constraints, solver='ace', verbose=-1) else 'invalid'}")

    # Find MSS (assumption-based)
    print("\n2. Finding MSS with mss (assumption-based)...")
    mss_assump = mss(soft_constraints, solver="ace", verbose=-1)

    print(f"\n   MSS contains {len(mss_assump)} constraint(s):")
    for label in label_constraints(mss_assump):
        print(f"     - {label}")

    # Find MCS
    print("\n" + "-" * 40)
    print("3. Finding MCS (constraints to remove)...")
    mcs_result = mcs_naive(soft_constraints, solver="ace", verbose=-1)

    print(f"\n   MCS contains {len(mcs_result)} constraint(s) to remove:")
    for label in label_constraints(mcs_result):
        print(f"     - {label}")
    print(f"   Verification: {'valid MCS' if is_mcs(mcs_result, soft_constraints, solver='ace', verbose=-1) else 'invalid'}")

    # Verify MSS + MCS = all soft constraints
    print("\n" + "-" * 40)
    print("4. Verification: MSS + MCS = All Constraints")
    mss_ids = set(id(c) for c in mss_result)
    mcs_ids = set(id(c) for c in mcs_result)
    soft_ids = set(id(c) for c in soft_constraints)

    print(f"   |MSS| = {len(mss_result)}")
    print(f"   |MCS| = {len(mcs_result)}")
    print(f"   |Soft| = {len(soft_constraints)}")
    print(f"   MSS + MCS = Soft? {mss_ids | mcs_ids == soft_ids}")
    print(f"   MSS and MCS disjoint? {len(mss_ids & mcs_ids) == 0}")

    print("\n" + "=" * 60)
    print("Explanation:")
    print("  - MSS: The largest satisfiable subset of constraints")
    print("  - MCS: The minimum constraints to remove for satisfiability")
    print("  - Removing MCS constraints leaves MSS, which is satisfiable")
    print("=" * 60)


if __name__ == "__main__":
    main()
