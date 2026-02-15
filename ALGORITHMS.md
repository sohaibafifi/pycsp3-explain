# Algorithms in PyCSP3-Explain

This document describes the algorithmic foundations of the package in scientific terms.
It focuses on problem definitions, optimization criteria, guarantees, and complexity tradeoffs.

## 1. Problem Setting

Let:
- `H` be a set of hard constraints.
- `S = {c1, ..., cn}` be a set of soft constraints.

We study subsets `X ⊆ S` under the satisfiability of `H ∪ X`.

### 1.1 Core objects

- **MUS (Minimal Unsatisfiable Subset)**:
  `M ⊆ S` such that `H ∪ M` is UNSAT, and for every `c in M`, `H ∪ (M \ {c})` is SAT.
- **MSS (Maximal Satisfiable Subset)**:
  `M ⊆ S` such that `H ∪ M` is SAT, and for every `c in S \ M`, `H ∪ (M ∪ {c})` is UNSAT.
- **MCS (Minimal Correction Set)**:
  `C ⊆ S` such that `H ∪ (S \ C)` is SAT, and no strict subset of `C` has this property.
  Equivalent relation: `MCS = S \ MSS`.

### 1.2 Weighted variants

Given weights `w: S -> R`:
- **Optimal MUS** minimizes `sum_{c in M} w(c)` over all MUSes.
- **Optimal MSS** maximizes `sum_{c in M} w(c)` over all satisfiable subsets (with maximality induced by objective + tie-breaks).
- **Optimal MCS** minimizes removed weight via complement of optimal MSS.

In this repository:
- Weighted MSS/MCS require **non-negative** weights.
- Weighted MUS/OCUS accept general linear weights.

## 2. Algorithm Inventory

| Function | Target Problem | Family | Guarantee |
|---|---|---|---|
| `mus_naive` | MUS | Deletion-based | Complete, returns MUS |
| `mus` | MUS | Assumption/core-guided deletion | Complete, returns MUS |
| `quickxplain` | Preferred MUS | QuickXplain divide-and-conquer | Complete for preferred MUS semantics |
| `quickxplain_incremental` | Preferred MUS | QuickXplain + reusable assumption session | Same result class as `quickxplain` |
| `all_mus_naive` | MUS enumeration | Multi-start naive search | Finds valid MUSes; not complete by proof |
| `optimal_mus` | Minimum-weight MUS | Iterative hitting set (IHS/OCUS style) | Complete, optimal by objective |
| `optimal_mus_naive` | Minimum-weight MUS | Exhaustive subset enumeration | Complete, optimal; exponential |
| `ocus` | Constrained optimal MUS | IHS with subset constraints | Complete under constraints |
| `ocus_naive` | Constrained optimal MUS | Exhaustive constrained enumeration | Complete under constraints; exponential |
| `mss_naive` | MSS | Greedy growing | Returns an MSS (not weight-optimal) |
| `mss` | MSS | Assumption/core-guided growing | Returns an MSS |
| `mss_opt` | Weighted MSS | Exact CP optimization | Optimal for objective with tie-break |
| `mss_heuristic` | Weighted MSS | Greedy weighted grow | Approximate |
| `mcs_naive` | MCS | Complement of naive MSS | Returns an MCS |
| `mcs` | MCS | Complement of assumption-based MSS | Returns an MCS |
| `mcs_opt` | Weighted MCS | Complement of exact weighted MSS | Optimal for induced objective |
| `mcs_heuristic` | Weighted MCS | Complement of greedy weighted MSS | Approximate |
| `marco` | MUS/MCS enumeration | MARCO + map solver | Complete MUS/MCS enumeration |
| `marco_naive` | MUS/MCS enumeration | Naive exploration | Baseline, slower |
| `all_mus`, `all_mcs` | Enumeration wrappers | MARCO wrappers | Complete via `marco` |

## 3. MUS Algorithms

### 3.1 `mus_naive`: deletion-based shrinking

Principle:
1. Start from an UNSAT set (typically all soft constraints).
2. For each constraint, temporarily remove it.
3. Keep it removed if UNSAT persists; otherwise restore it.

This produces a subset-minimal UNSAT set (a MUS).  
Worst-case complexity is high: up to `O(n)` SAT/UNSAT oracle calls for one shrink pass, each NP-hard.

### 3.2 `mus`: assumption/core-guided shrinking

Uses indicator variables `a_i` and guarded constraints `(a_i -> c_i)`.  
UNSAT cores over assumptions localize conflicting constraints and reduce unnecessary oracle calls.

The method is still oracle-based but typically more efficient than pure naive deletion when core extraction is available.

### 3.3 `quickxplain`: preferred MUS extraction

QuickXplain (Junker, 2004) recursively partitions constraints:
- It computes a conflict relative to preference order.
- Divide-and-conquer search identifies a minimal conflict while preserving preference semantics.

This is not a global weight optimizer; it is a **preference-ordered MUS extractor**.

### 3.4 `quickxplain_incremental`

Same recursive QuickXplain logic, but with a reusable assumption session:
- hard + guard constraints are posted once,
- each recursive oracle call only updates assumption fixings.

This improves model reuse structure. PyCSP3 still recompiles each solve call.

## 4. Optimal MUS / OCUS Algorithms

### 4.1 `optimal_mus`: iterative hitting set optimization

Implements the OCUS/IHS pattern:
1. Maintain a collection of correction subsets.
2. Solve a weighted hitting set over collected corrections.
3. Test candidate: if UNSAT, shrink to MUS and return; if SAT, grow to MSS and add new correction subset.

This yields a minimum-weight MUS under the chosen objective.

### 4.2 `optimal_mus_naive`

Exhaustively enumerates subsets:
1. Filter UNSAT subsets.
2. Keep only subset-minimal UNSAT subsets.
3. Select minimum-weight MUS.

Complete and exact, but exponential in `|S|`.

### 4.3 `ocus`: constrained optimal MUS

Extends optimal MUS with subset admissibility:
- `subset_predicate`: semantic predicate over selected indices.
- `subset_constraints`: CP-level constraints over selection variables.

Search is restricted to admissible subsets; objective optimization is done within this feasible region.

### 4.4 `ocus_naive`

Exhaustive constrained counterpart of `ocus`.
Complete but exponential.

## 5. MSS and MCS Algorithms

### 5.1 `mss_naive`: greedy satisfiable grow

Start from empty subset and attempt adding constraints one by one.
Keep additions that preserve SAT.  
Returns an MSS (maximal by inclusion), but not necessarily optimal for weighted objectives.

### 5.2 `mss`: assumption/core-guided grow

Uses assumption session and cores:
- test candidate additions under assumptions,
- exploit core information to exclude conflicting additions early.

Returns an MSS; it is designed for efficiency of maximal construction, not weight optimality.

### 5.3 `mss_opt`: exact weighted optimization

Selection model with binary variables `x_i`:
- Feasibility: `x_i -> c_i` and all hard constraints.
- Objective: maximize weighted kept constraints, with deterministic cardinality tie-break.

Current behavior:
- Requires `w_i >= 0`.
- Solves one optimization model; if solver outcome is indeterminate, can fallback to heuristic.

### 5.4 `mss_heuristic`

Greedy weighted construction (descending priority by weight/features), maintaining SAT at each step.
Fast baseline, not guaranteed optimal.

### 5.5 MCS derivation and weighted variants

By dual complement relation:
- `mcs_from_mss(M) = S \ M`.
- `mcs`, `mcs_naive`, `mcs_opt`, `mcs_heuristic` are defined via corresponding MSS procedures.

For weighted optimization, `mcs_opt` inherits exactness from `mss_opt`.

## 6. Enumeration Algorithms

### 6.1 `marco`

Implements MARCO-style complete enumeration of MUSes and MCSes:
- Uses a map-space search over subsets.
- Blocks discovered regions with clauses to avoid revisiting equivalent areas.
- Alternates between SAT-side and UNSAT-side discoveries.

Complete for MUS/MCS enumeration under terminating map-search exploration.

### 6.2 `marco_naive`

Simpler baseline enumeration strategy without the full map-solver efficiency.
Useful as reference behavior; typically slower.

## 7. Verification Predicates

- `is_mus`, `is_mss`, `is_mcs` validate returned subsets against formal definitions.
- They are not optimization algorithms, but they are important for empirical and regression validation.

## 8. Complexity and Practical Tradeoffs

- Most decision calls are NP-complete SAT/UNSAT checks.
- Exact optimization/enumeration methods are exponential in worst case.
- Heuristic variants trade optimality/completeness for runtime.
- Core extraction and assumption reuse reduce practical overhead, especially on structured instances.

## 9. Canonical References

- U. Junker (2004), [*QuickXplain: Preferred Explanations and Relaxations for Over-Constrained Problems*](https://cdn.aaai.org/AAAI/2004/AAAI04-027.pdf).
- M. H. Liffiton, A. Previti, A. Malik, J. Marques-Silva (2016), [*Fast, Flexible MUS Enumeration*](https://doi.org/10.1007/s10601-015-9183-0).
- E. Gamba, B. Bogaerts, T. Guns (2023), [*Efficiently Explaining CSPs with Unsatisfiable Subset Optimization*](https://doi.org/10.1613/jair.1.14260).
- R. Reiter (1987), [*A Theory of Diagnosis from First Principles*](https://doi.org/10.1016/0004-3702(87)90062-2) (hitting-set duality roots).
