"""
Tests for MUS (Minimal Unsatisfiable Subset) algorithms.
"""

import pytest
import sys
import os


from pycsp3 import *
from pycsp3_explain.explain.mus import mus, mus_naive, quickxplain_naive, is_mus
from pycsp3_explain.solvers.wrapper import is_sat, is_unsat


def constraint_in_list(constraint, constraint_list):
    """Check if constraint is in list using identity comparison."""
    return any(c is constraint for c in constraint_list)


class TestMusBasic:
    """Basic tests for MUS algorithms."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_unsat(self):
        """Test MUS on a simple unsatisfiable model."""
        clear()

        # Create variables
        x = VarArray(size=3, dom=range(10))

        # Create constraints - c0 and c2 conflict
        c0 = x[0] == 5       # x[0] must be 5
        c1 = x[1] >= 3       # x[1] at least 3 (independent)
        c2 = x[0] == 7       # x[0] must be 7 (conflicts with c0)

        soft = [c0, c1, c2]

        # Find MUS
        mus = mus_naive(soft, solver="ace", verbose=-1)

        # MUS should contain exactly c0 and c2 (the conflicting constraints)
        assert len(mus) == 2
        assert constraint_in_list(c0, mus)
        assert constraint_in_list(c2, mus)
        assert not constraint_in_list(c1, mus)  # c1 is independent, not in MUS

    def test_mus_with_hard_constraints(self):
        """Test MUS with hard constraints."""
        clear()

        x = VarArray(size=2, dom=range(10))

        hard = [x[0] >= 0]  # Always true, just for testing
        c0 = x[0] + x[1] == 5
        c1 = x[0] + x[1] == 10  # Conflicts with c0

        soft = [c0, c1]
        mus = mus_naive(soft, hard=hard, solver="ace", verbose=-1)

        assert len(mus) == 2
        assert constraint_in_list(c0, mus)
        assert constraint_in_list(c1, mus)

    def test_single_constraint_unsat(self):
        """Test MUS when a single constraint is unsatisfiable."""
        clear()

        x = Var(dom=range(5))

        # x must be both less than 0 AND in range [0,4] - impossible
        c0 = x < 0  # This alone is UNSAT with domain [0,4]

        soft = [c0]

        mus = mus_naive(soft, solver="ace", verbose=-1)

        assert len(mus) == 1
        assert constraint_in_list(c0, mus)

    def test_three_way_conflict(self):
        """Test MUS with a three-way conflict."""
        clear()

        x = Var(dom=range(10))

        # These three constraints together are UNSAT
        # There are multiple possible MUSes:
        # - {c0, c1}: x>=5 and x<=3 conflict
        # - {c1, c2}: x<=3 and x==4 conflict
        c0 = x >= 5
        c1 = x <= 3
        c2 = x == 4

        soft = [c0, c1, c2]

        mus = mus_naive(soft, solver="ace", verbose=-1)

        # MUS should be of size 2 (any valid MUS)
        assert len(mus) == 2
        # Should contain c1 (which conflicts with both c0 and c2)
        assert constraint_in_list(c1, mus)


class TestQuickXplain:
    """Tests for QuickXplain algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_quickxplain_simple(self):
        """Test QuickXplain on a simple conflict."""
        clear()

        x = VarArray(size=2, dom=range(10))

        c0 = x[0] == 5
        c1 = x[0] == 7  # Conflicts with c0

        soft = [c0, c1]
        mus = quickxplain_naive(soft, solver="ace", verbose=-1)

        assert len(mus) == 2
        assert constraint_in_list(c0, mus)
        assert constraint_in_list(c1, mus)

    def test_quickxplain_preference(self):
        """Test that QuickXplain respects constraint ordering."""
        clear()

        x = Var(dom=range(10))

        # Multiple possible MUSes, QuickXplain should prefer earlier constraints
        c0 = x == 1  # Preferred
        c1 = x == 2
        c2 = x == 3

        # All pairs conflict, but {c0, c1} should be preferred
        soft = [c0, c1, c2]
        mus = quickxplain_naive(soft, solver="ace", verbose=-1)

        # Should get a MUS of size 2
        assert len(mus) == 2
        # Should prefer c0 (first constraint)
        assert constraint_in_list(c0, mus)


class TestMusAssumptionBased:
    """Tests for assumption-based MUS algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_unsat(self):
        """Test assumption-based MUS on a simple unsatisfiable model."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7

        soft = [c0, c1, c2]
        mus_set = mus(soft, solver="ace", verbose=-1)

        assert len(mus_set) == 2
        assert constraint_in_list(c0, mus_set)
        assert constraint_in_list(c2, mus_set)
        assert not constraint_in_list(c1, mus_set)

    def test_mus_with_hard_constraints(self):
        """Test assumption-based MUS with hard constraints."""
        clear()

        x = VarArray(size=2, dom=range(10))

        hard = [x[0] >= 0]
        c0 = x[0] + x[1] == 5
        c1 = x[0] + x[1] == 10

        soft = [c0, c1]
        mus_set = mus(soft, hard=hard, solver="ace", verbose=-1)

        assert len(mus_set) == 2
        assert constraint_in_list(c0, mus_set)
        assert constraint_in_list(c1, mus_set)


class TestIsMus:
    """Tests for MUS verification."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_is_mus_valid(self):
        """Test that a valid MUS is recognized."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        subset = [c0, c1]
        assert is_mus(subset, solver="ace", verbose=-1)

    def test_is_mus_not_minimal(self):
        """Test that a non-minimal subset is rejected."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7
        c2 = x >= 0  # Redundant, doesn't contribute to conflict

        # {c0, c1, c2} is UNSAT but not minimal
        subset = [c0, c1, c2]

        # This should NOT be a MUS because c2 can be removed
        # Actually this depends on implementation - c2 doesn't affect the conflict
        # Let's check if it's recognized as not minimal
        result = is_mus(subset, solver="ace", verbose=-1)
        # If c2 is truly redundant, removing it still gives UNSAT
        # so this should return False
        assert result is False

    def test_is_mus_sat(self):
        """Test that a SAT subset is rejected."""
        clear()

        x = Var(dom=range(10))
        c0 = x >= 5
        c1 = x <= 8

        subset = [c0, c1]  # SAT (x can be 5,6,7,8)
        assert is_mus(subset, solver="ace", verbose=-1) is False


class TestEdgeCases:
    """Edge case tests."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_empty_soft_raises(self):
        """Test that empty soft constraints raises error."""
        with pytest.raises(ValueError):
            mus_naive([], solver="ace")

    def test_sat_model_raises(self):
        """Test that SAT model raises assertion error."""
        clear()

        x = Var(dom=range(10))
        c0 = x >= 0  # Always SAT with domain [0,9]

        with pytest.raises(AssertionError):
            mus_naive([c0], solver="ace")

    def test_nested_constraints(self):
        """Test MUS with nested constraint lists."""
        clear()

        x = VarArray(size=2, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 0
        c2 = x[0] == 7

        # Nested list
        soft = [[c0, c1], c2]
        mus = mus_naive(soft, solver="ace", verbose=-1)

        # Should find {c0, c2}
        assert len(mus) == 2


class TestSolverWrapper:
    """Tests for the solver wrapper functions."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_is_sat_simple(self):
        """Test is_sat with a simple SAT model."""
        clear()

        x = Var(dom=range(10))
        c0 = x >= 5
        c1 = x <= 8

        assert is_sat([c0, c1], solver="ace", verbose=-1)

    def test_is_unsat_simple(self):
        """Test is_unsat with a simple UNSAT model."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        assert is_unsat([c0, c1], solver="ace", verbose=-1)

    def test_is_sat_with_hard(self):
        """Test is_sat with hard constraints."""
        clear()

        x = Var(dom=range(10))
        hard = [x >= 0]
        soft = [x <= 5]

        assert is_sat(soft, hard=hard, solver="ace", verbose=-1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
