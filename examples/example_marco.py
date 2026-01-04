#!/usr/bin/env python3
"""
Example: Enumerating all MUSes and MCSes using MARCO algorithm.

This example demonstrates how to use the MARCO algorithm to find ALL
minimal unsatisfiable subsets (MUSes) and minimal correction sets (MCSes)
of an infeasible constraint model.

MARCO is particularly useful when:
- You need to understand ALL the conflicts in your model
- You want to see different ways to fix the model (via MCSes)
- You're debugging a complex constraint model with multiple issues
"""

from pycsp3 import *
from pycsp3_explain import marco, all_mus, all_mcs, is_mus, is_mcs


def main():
    print("=" * 70)
    print("Example: MARCO Algorithm - Enumerate All MUSes and MCSes")
    print("=" * 70)

    # Clear any previous model
    clear()

    # Create variables
    print("\nCreating variables...")
    x = Var(dom=range(10), id="x")
    y = Var(dom=range(10), id="y")
    print(f"   Variables: x, y with domain [0, 9]")

    # Create constraints that form multiple conflicts
    print("\nCreating constraints...")

    c0 = x == 1
    print(f"   c0: x == 1")

    c1 = x == 2
    print(f"   c1: x == 2")

    c2 = x == 3
    print(f"   c2: x == 3")

    c3 = y >= 5
    print(f"   c3: y >= 5")

    c4 = y <= 3
    print(f"   c4: y <= 3")

    soft_constraints = [c0, c1, c2, c3, c4]
    constraint_names = ["x == 1", "x == 2", "x == 3", "y >= 5", "y <= 3"]

    def constraint_name(c):
        for i, orig in enumerate(soft_constraints):
            if c is orig:
                return f"c{i}: {constraint_names[i]}"
        return str(c)

    print("\nAnalysis:")
    print("   - c0, c1, c2 all assign different values to x (three-way conflict)")
    print("   - c3 and c4 conflict on y (y >= 5 AND y <= 3 is impossible)")
    print("   - Expected MUSes: {c0,c1}, {c0,c2}, {c1,c2}, {c3,c4}")

    # =========================================================================
    # Method 1: Using marco() generator to iterate over results
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 1: Using marco() generator")
    print("-" * 70)

    clear()  # Reset state
    x = Var(dom=range(10), id="x")
    y = Var(dom=range(10), id="y")
    c0 = x == 1
    c1 = x == 2
    c2 = x == 3
    c3 = y >= 5
    c4 = y <= 3
    soft_constraints = [c0, c1, c2, c3, c4]

    mus_count = 0
    mcs_count = 0

    print("\nEnumerating all MUSes and MCSes...")
    for result_type, subset in marco(soft_constraints, solver="ace", verbose=-1):
        if result_type == "MUS":
            mus_count += 1
            print(f"\n   MUS #{mus_count}: {{{', '.join(constraint_name(c) for c in subset)}}}")
        else:
            mcs_count += 1
            print(f"\n   MCS #{mcs_count}: {{{', '.join(constraint_name(c) for c in subset)}}}")

    print(f"\n   Total: {mus_count} MUSes, {mcs_count} MCSes")

    # =========================================================================
    # Method 2: Using all_mus() and all_mcs() convenience functions
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 2: Using all_mus() and all_mcs() convenience functions")
    print("-" * 70)

    clear()  # Reset state
    x = Var(dom=range(10), id="x")
    y = Var(dom=range(10), id="y")
    c0 = x == 1
    c1 = x == 2
    c2 = x == 3
    c3 = y >= 5
    c4 = y <= 3
    soft_constraints = [c0, c1, c2, c3, c4]

    print("\nFinding all MUSes...")
    muses = all_mus(soft_constraints, solver="ace", verbose=-1)
    print(f"   Found {len(muses)} MUSes:")
    for i, mus in enumerate(muses, 1):
        print(f"      MUS #{i}: {{{', '.join(constraint_name(c) for c in mus)}}}")

    print("\nFinding all MCSes...")
    mcses = all_mcs(soft_constraints, solver="ace", verbose=-1)
    print(f"   Found {len(mcses)} MCSes:")
    for i, mcs in enumerate(mcses, 1):
        print(f"      MCS #{i}: {{{', '.join(constraint_name(c) for c in mcs)}}}")

    # =========================================================================
    # Method 3: Using max_mus/max_mcs to limit results
    # =========================================================================
    print("\n" + "-" * 70)
    print("Method 3: Limiting the number of results")
    print("-" * 70)

    clear()  # Reset state
    x = Var(dom=range(10), id="x")
    y = Var(dom=range(10), id="y")
    c0 = x == 1
    c1 = x == 2
    c2 = x == 3
    c3 = y >= 5
    c4 = y <= 3
    soft_constraints = [c0, c1, c2, c3, c4]

    print("\nFinding at most 2 MUSes...")
    limited_muses = all_mus(soft_constraints, max_mus=2, solver="ace", verbose=-1)
    print(f"   Found {len(limited_muses)} MUSes (limited to 2):")
    for i, mus in enumerate(limited_muses, 1):
        print(f"      MUS #{i}: {{{', '.join(constraint_name(c) for c in mus)}}}")

    # =========================================================================
    # Interpretation
    # =========================================================================
    print("\n" + "=" * 70)
    print("Interpretation:")
    print("=" * 70)
    print("""
   MUSes tell you WHY the model is infeasible:
   - Each MUS is a minimal set of constraints that cannot all be true
   - Removing ANY constraint from a MUS makes it satisfiable

   MCSes tell you HOW to fix the model:
   - Each MCS is a minimal set of constraints to REMOVE to make it feasible
   - Different MCSes represent different ways to fix the model

   In this example:
   - MUSes show the conflicts: x can't be 1,2,3 at once; y can't be >=5 and <=3
   - MCSes show fixes: remove certain combinations to make the model feasible
""")
    print("=" * 70)


if __name__ == "__main__":
    main()
