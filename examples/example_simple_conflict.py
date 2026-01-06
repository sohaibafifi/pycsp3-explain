#!/usr/bin/env python3
"""
Example: Finding a simple constraint conflict using MUS.

This example demonstrates how to compare mus (assumption-based) and
mus_naive to find the minimal set of conflicting constraints in an
infeasible model.
"""


from pycsp3 import *
from pycsp3_explain.explain.mus import mus, mus_naive, is_mus, optimal_mus, ocus
from pycsp3_explain.explain.marco import marco


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
    weights = [10, 5, 5, 1, 5]

    def print_mus_result(title, mus_set, weights=None):
        print(f"\n{title}: MUS contains {len(mus_set)} constraint(s)")
        print("   Conflicting constraints:")
        total_weight = 0
        for c in mus_set:
            for j, orig_c in enumerate(soft_constraints):
                if c is orig_c:
                    line = f"   - c{j}: {constraint_labels[j]}"
                    if weights is not None:
                        line += f" [w={weights[j]}]"
                        total_weight += weights[j]
                    print(line)
                    break
        if weights is not None:
            print(f"   Total weight: {total_weight}")
        print("   Verification:", "valid" if is_mus(mus_set, solver="ace", verbose=-1) else "invalid")

    def format_subset(subset):
        parts = []
        for c in subset:
            for j, orig_c in enumerate(soft_constraints):
                if c is orig_c:
                    parts.append(f"c{j}: {constraint_labels[j]}")
                    break
        return ", ".join(parts)

    print("\n1. Finding MUS with mus (assumption-based)...")
    mus_assump = mus(soft_constraints, solver="ace", verbose=-1)
    print_mus_result("\tAssumption-based result", mus_assump)

    print("\n2. Finding MUS with mus_naive...")
    mus_slow = mus_naive(soft_constraints, solver="ace", verbose=-1)
    print_mus_result("\tNaive result", mus_slow)
    same = set(id(c) for c in mus_assump) == set(id(c) for c in mus_slow)
    print("\nComparison:")
    print("   Same constraints:" if same else "   Different MUSes (both minimal)")

    print("\n3. Finding Optimal MUS with weights...")
    optimal = optimal_mus(soft_constraints, weights=weights, solver="ace", verbose=-1)
    print_mus_result("\tOptimal MUS (weighted)", optimal, weights=weights)

    print("\n4. Finding OCUS with a required constraint (must include c2)...")
    def require_c2(select):
        return [select[2] == 1]

    def require_c2_pred(indices):
        return 2 in indices

    ocus_result = ocus(
        soft_constraints,
        weights=weights,
        solver="ace",
        verbose=-1,
        subset_constraints=require_c2,
        subset_predicate=require_c2_pred,
    )
    print_mus_result("\tOCUS (must include c2)", ocus_result, weights=weights)

    print("\n5. Enumerating all MUSes and MCSes with MARCO...")
    mus_count = 0
    mcs_count = 0
    for result_type, subset in marco(soft_constraints, solver="ace", verbose=-1):
        if result_type == "MUS":
            mus_count += 1
            print(f"   MUS #{mus_count}: {{{format_subset(subset)}}}")
        else:
            mcs_count += 1
            print(f"   MCS #{mcs_count}: {{{format_subset(subset)}}}")
    print(f"   Total: {mus_count} MUSes, {mcs_count} MCSes")

    print("\n" + "=" * 60)
    print("Explanation:")
    print("  The MUS shows that x[0] cannot be both 5 AND 7.")
    print("  Optimal MUS uses weights to rank which conflicts to examine first.")
    print("  OCUS allows extra conditions on explanations.")
    print("  MARCO enumerates all MUSes and MCSes for deeper analysis.")
    print("  To fix the model, remove or modify one of these constraints.")
    print("=" * 60)


if __name__ == "__main__":
    main()
