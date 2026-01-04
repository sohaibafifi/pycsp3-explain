"""
Utilities for explanation techniques in PyCSP3.

This module provides helper functions for:
- Flattening constraint lists
- Creating subset models
- Tracking constraint-to-index mappings
"""

from typing import List, Any, Optional, Tuple, Dict
import sys
import os

_ASSUMP_COUNTER = 0


def _next_assump_name(prefix: str) -> str:
    global _ASSUMP_COUNTER
    _ASSUMP_COUNTER += 1
    return f"{prefix}_{_ASSUMP_COUNTER}"


def _normalize_constraint(constraint: Any) -> Any:
    try:
        from pycsp3.classes.auxiliary.enums import TypeCtrArg
        from pycsp3.classes.entities import ECtr
        from pycsp3.classes.main.constraints import Constraint, ConstraintIntension
    except Exception:
        return constraint

    if isinstance(constraint, ConstraintIntension):
        return constraint.arguments[TypeCtrArg.FUNCTION].content
    if isinstance(constraint, Constraint):
        return ECtr(constraint)
    return constraint


def flatten_constraints(constraints: List[Any]) -> List[Any]:
    """
    Flatten a nested list of constraints into a single list.

    :param constraints: List of constraints (possibly nested)
    :return: Flat list of constraints
    """
    result = []
    for c in constraints:
        if isinstance(c, list):
            result.extend(flatten_constraints(c))
        elif c is not None:
            result.append(_normalize_constraint(c))
    return result


def get_constraint_variables(constraint) -> List:
    """
    Extract variables involved in a constraint.

    :param constraint: A PyCSP3 constraint
    :return: List of variables in the constraint
    """
    from pycsp3.classes.main.variables import Variable
    from pycsp3.tools.utilities import flatten

    variables = []

    def extract_vars(obj):
        if isinstance(obj, Variable):
            variables.append(obj)
        elif hasattr(obj, 'arguments'):
            # Constraint with arguments
            for arg in obj.arguments.values():
                if hasattr(arg, 'content'):
                    extract_vars(arg.content)
                else:
                    extract_vars(arg)
        elif hasattr(obj, 'constraint'):
            extract_vars(obj.constraint)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                extract_vars(item)

    extract_vars(constraint)
    return list(set(variables))


class ConstraintTracker:
    """
    Track constraints and their relationships for explanation algorithms.

    This class maintains a mapping between constraints and their indices,
    which is useful for tracking which constraints are in a MUS/MCS.
    """

    def __init__(self, soft: List[Any], hard: Optional[List[Any]] = None):
        """
        Initialize the constraint tracker.

        :param soft: List of soft constraints (candidates for MUS/MCS)
        :param hard: List of hard constraints (must always hold)
        """
        self.soft = flatten_constraints(soft)
        self.hard = flatten_constraints(hard) if hard else []

        # Create index mappings
        self._soft_to_idx: Dict[int, int] = {}
        self._idx_to_soft: Dict[int, Any] = {}

        for i, c in enumerate(self.soft):
            self._soft_to_idx[id(c)] = i
            self._idx_to_soft[i] = c

    def get_index(self, constraint) -> Optional[int]:
        """Get the index of a soft constraint."""
        return self._soft_to_idx.get(id(constraint))

    def get_constraint(self, index: int) -> Optional[Any]:
        """Get a soft constraint by its index."""
        return self._idx_to_soft.get(index)

    def get_subset(self, indices: List[int]) -> List[Any]:
        """Get a subset of soft constraints by their indices."""
        return [self._idx_to_soft[i] for i in indices if i in self._idx_to_soft]

    def get_complement(self, indices: List[int]) -> List[Any]:
        """Get the complement of a subset (all soft constraints not in indices)."""
        index_set = set(indices)
        return [c for i, c in self._idx_to_soft.items() if i not in index_set]

    @property
    def num_soft(self) -> int:
        """Number of soft constraints."""
        return len(self.soft)

    @property
    def all_indices(self) -> List[int]:
        """All soft constraint indices."""
        return list(range(self.num_soft))


def make_assump_model(
    soft: List[Any],
    hard: Optional[List[Any]] = None,
    name_prefix: str = "assump"
) -> Tuple[List[Any], List[Any], List[Any], List[Any]]:
    """
    Build assumption indicators and implication constraints for soft constraints.

    Returns (soft, hard, assumptions, guard_constraints) where guard constraints
    are of the form a -> c for each soft constraint c.
    """
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if not soft:
        raise ValueError("soft constraints cannot be empty")

    from pycsp3 import VarArray, imply

    assumptions = VarArray(size=len(soft), dom=range(2), id=_next_assump_name(name_prefix))
    guard_constraints = [imply(a, c) for a, c in zip(assumptions, soft)]
    return soft, hard, list(assumptions), guard_constraints


def order_by_num_variables(constraints: List[Any], descending: bool = True) -> List[Any]:
    """
    Order constraints by the number of variables they contain.

    :param constraints: List of constraints
    :param descending: If True, constraints with more variables come first
    :return: Ordered list of constraints
    """
    def count_vars(c):
        try:
            return len(get_constraint_variables(c))
        except:
            return 0

    return sorted(constraints, key=count_vars, reverse=descending)


def explain_unsat(
    algorithm: Any = "mus",
    soft: Optional[List[Any]] = None,
    hard: Optional[List[Any]] = None,
    check: bool = True,
    **kwargs
) -> Any:
    """
    Run an explanation algorithm on an UNSAT model.

    If soft is None, constraints are pulled from the current model via posted().
    The algorithm can be a string key or a callable.
    """
    from pycsp3 import posted
    from pycsp3_explain.solvers.wrapper import is_unsat

    soft = posted() if soft is None else soft
    soft = flatten_constraints(soft)
    hard = flatten_constraints(hard) if hard else []

    if check:
        solver = kwargs.get("solver", "ace")
        verbose = kwargs.get("verbose", -1)
        if not is_unsat(soft, hard, solver=solver, verbose=verbose):
            raise ValueError("explain_unsat: model must be UNSAT")

    if isinstance(algorithm, str):
        key = algorithm.lower()
        from pycsp3_explain.explain.mus import (
            mus,
            mus_naive,
            quickxplain_naive,
            optimal_mus,
            optimal_mus_naive,
            smus,
            ocus_naive,
            all_mus_naive,
        )
        from pycsp3_explain.explain.mss import (
            mss,
            mss_naive,
            mss_opt,
            mcs,
            mcs_naive,
            mcs_opt,
        )
        from pycsp3_explain.explain.marco import (
            marco,
            marco_naive,
            all_mus,
            all_mcs,
        )

        algo_map = {
            "mus": mus,
            "mus_naive": mus_naive,
            "quickxplain": quickxplain_naive,
            "quickxplain_naive": quickxplain_naive,
            "optimal_mus": optimal_mus,
            "optimal_mus_naive": optimal_mus_naive,
            "smus": smus,
            "ocus_naive": ocus_naive,
            "all_mus_naive": all_mus_naive,
            "mss": mss,
            "mss_naive": mss_naive,
            "mss_opt": mss_opt,
            "mcs": mcs,
            "mcs_naive": mcs_naive,
            "mcs_opt": mcs_opt,
            "marco": marco,
            "marco_naive": marco_naive,
            "all_mus": all_mus,
            "all_mcs": all_mcs,
        }

        if key not in algo_map:
            options = ", ".join(sorted(algo_map.keys()))
            raise ValueError(f"Unknown algorithm '{algorithm}'. Expected one of: {options}")
        algorithm = algo_map[key]

    return algorithm(soft, hard, **kwargs)
