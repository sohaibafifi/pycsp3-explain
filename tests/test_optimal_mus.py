"""
Tests for optimal MUS algorithms (smus, optimal_mus, ocus).
"""

import pytest
from pycsp3 import *
from pycsp3_explain.explain.mus import (
    optimal_mus,
    optimal_mus_naive,
    smus,
    ocus,
    ocus_naive,
    is_mus,
    OCUSException,
)
from pycsp3_explain.solvers.wrapper import is_unsat


def constraint_in_list(constraint, constraint_list):
    """Check if constraint is in list using identity comparison."""
    return any(c is constraint for c in constraint_list)


class TestSmus:
    """Tests for smallest MUS (SMUS) algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_conflict(self):
        """Test SMUS on a simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        result = smus(soft, solver="ace", verbose=-1)

        # Both constraints are needed for the MUS
        assert len(result) == 2
        assert is_mus(result, solver="ace", verbose=-1)

    def test_finds_smallest(self):
        """Test that SMUS finds the smallest MUS."""
        clear()

        x = Var(dom=range(10))

        # c0 and c3 conflict (both equal to different values)
        # c1 and c2 don't add to the conflict
        c0 = x == 5       # Conflicts with c3
        c1 = x >= 0       # No conflict (always true)
        c2 = x <= 9       # No conflict (always true)
        c3 = x == 7       # Conflicts with c0

        soft = [c0, c1, c2, c3]

        result = smus(soft, solver="ace", verbose=-1)

        # Smallest MUS should be {c0, c3}
        assert len(result) == 2
        assert constraint_in_list(c0, result)
        assert constraint_in_list(c3, result)

    def test_single_constraint_mus(self):
        """Test SMUS when single constraint is UNSAT."""
        clear()

        x = Var(dom=range(5))

        c0 = x < 0  # UNSAT by itself
        c1 = x >= 0  # SAT

        soft = [c0, c1]

        result = smus(soft, solver="ace", verbose=-1)

        # Smallest MUS is just {c0}
        assert len(result) == 1
        assert constraint_in_list(c0, result)


class TestOptimalMus:
    """Tests for weighted optimal MUS."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_weighted_simple(self):
        """Test optimal_mus with weights."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2

        soft = [c0, c1]
        # Both constraints are in all MUSes, weights don't change result
        weights = [1, 10]

        result = optimal_mus(soft, weights=weights, solver="ace", verbose=-1)

        assert len(result) == 2
        assert is_mus(result, solver="ace", verbose=-1)

    def test_weighted_prefers_lower_weight(self):
        """Test that optimal_mus prefers lower weight constraints."""
        clear()

        x = Var(dom=range(10))

        # Multiple MUSes possible: {c0,c1}, {c0,c2}, {c1,c2}
        c0 = x == 1  # weight 1
        c1 = x == 2  # weight 10
        c2 = x == 3  # weight 100

        soft = [c0, c1, c2]
        weights = [1, 10, 100]

        result = optimal_mus(soft, weights=weights, solver="ace", verbose=-1)

        # Should find MUS with lowest weight: {c0, c1} (weight 11)
        assert len(result) == 2
        assert constraint_in_list(c0, result)
        assert constraint_in_list(c1, result)

    def test_equal_weights_same_as_smus(self):
        """Test that equal weights gives same result as SMUS."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7
        c2 = x >= 0

        soft = [c0, c1, c2]

        smus_result = smus(soft, solver="ace", verbose=-1)
        optimal_result = optimal_mus(soft, weights=[1, 1, 1], solver="ace", verbose=-1)

        # Should find same size MUS
        assert len(smus_result) == len(optimal_result)


class TestOcusNaive:
    """Tests for OCUS naive implementation."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_conflict(self):
        """Test ocus_naive on simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        result = ocus_naive(soft, solver="ace", verbose=-1)

        assert len(result) == 2
        assert is_mus(result, solver="ace", verbose=-1)

    def test_with_weights(self):
        """Test ocus_naive with weights."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]
        weights = [1, 10, 100]

        result = ocus_naive(soft, weights=weights, solver="ace", verbose=-1)

        # Should find MUS with lowest weight
        assert len(result) == 2
        assert is_mus(result, solver="ace", verbose=-1)


class TestOcus:
    """Tests for OCUS with subset constraints."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_subset_constraint(self):
        """Test ocus honors a required constraint index."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x >= 0

        soft = [c0, c1, c2]

        def subset_constraints(select):
            return [select[2] == 1]

        def subset_predicate(indices):
            return 2 in indices

        result = ocus(
            soft,
            solver="ace",
            verbose=-1,
            subset_constraints=subset_constraints,
            subset_predicate=subset_predicate,
        )

        result_indices = {i for i, c in enumerate(soft) if constraint_in_list(c, result)}

        assert len(result) == 3
        assert subset_predicate(result_indices)
        assert is_unsat(result, solver="ace", verbose=-1)


class TestMssOpt:
    """Tests for weighted MSS optimization."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_weighted_mss(self):
        """Test mss_opt with weights."""
        clear()
        from pycsp3_explain.explain.mss import mss_opt, is_mss

        x = Var(dom=range(10))

        c0 = x == 1      # Conflicts with c1 and c2
        c1 = x == 2      # Conflicts with c0 and c2
        c2 = x == 3      # Conflicts with c0 and c1

        soft = [c0, c1, c2]
        weights = [100, 10, 1]  # c0 has highest weight

        result = mss_opt(soft, weights=weights, solver="ace", verbose=-1)

        # Result should be a valid MSS (exactly one constraint since all conflict)
        assert len(result) == 1
        assert is_mss(result, soft, solver="ace", verbose=-1)


class TestMcsOpt:
    """Tests for weighted MCS optimization."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_weighted_mcs(self):
        """Test mcs_opt with weights."""
        clear()
        from pycsp3_explain.explain.mss import mcs_opt, is_mcs

        x = Var(dom=range(10))

        c0 = x == 1      # Conflicts with c1 and c2
        c1 = x == 2      # Conflicts with c0 and c2
        c2 = x == 3      # Conflicts with c0 and c1

        soft = [c0, c1, c2]
        weights = [100, 10, 1]  # c0 has highest weight

        result = mcs_opt(soft, weights=weights, solver="ace", verbose=-1)

        # MCS should be complement of MSS (exactly 2 constraints since MSS has 1)
        assert len(result) == 2
        assert is_mcs(result, soft, solver="ace", verbose=-1)


class TestEdgeCases:
    """Edge cases for optimal MUS algorithms."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_empty_soft_raises(self):
        """Test that empty soft raises error."""
        with pytest.raises(ValueError):
            smus([], solver="ace")

    def test_sat_model_raises(self):
        """Test that SAT model raises assertion error."""
        clear()

        x = Var(dom=range(10))
        c0 = x >= 0

        with pytest.raises(AssertionError):
            smus([c0], solver="ace")

    def test_weights_length_mismatch(self):
        """Test that mismatched weights length raises error."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        with pytest.raises(ValueError):
            optimal_mus([c0, c1], weights=[1], solver="ace")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
