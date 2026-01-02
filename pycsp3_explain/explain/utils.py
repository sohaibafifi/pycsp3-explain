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
            result.append(c)
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
