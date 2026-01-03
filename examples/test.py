from pycsp3 import *
from pycsp3_explain import mus, mus_naive, is_mus

# Define an infeasible model
clear()
x = VarArray(size=3, dom=range(10))

constraints = [
    x[0] + x[1] == 5,
    x[1] + x[2] == 3,
    x[0] + x[2] == 10,
    x[0] == x[1],
    x[1] == x[2],
]

# Find a minimal unsatisfiable subset (assumption-based with ACE)
minimal_conflict = mus(soft=constraints, solver="ace")
print("MUS (assumption-based):", minimal_conflict)
print("Valid:", is_mus(minimal_conflict, solver="ace"))

# Naive MUS (works with any solver, but slower)
minimal_conflict_naive = mus_naive(soft=constraints, solver="ace")
print("MUS (naive):", minimal_conflict_naive)