from pycsp3 import *
from pycsp3_explain import *


x = VarArray(size=2, dom=range(10))

satisfy( [
    x[0] == 5,
    x[0] == 7,  # conflicts with x[0] == 5
    x[1] >= 3,
])

constraints  = flatten_constraints(posted())
if solve() == UNSAT:
    print("MUS:", mus(constraints))
    print("Optimal MUS:", optimal_mus(constraints, weights=[1, 1, 1]))
    for kind, subset in marco(constraints):
        print(kind, subset)