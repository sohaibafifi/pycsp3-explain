"""
Tests for MSS (Maximal Satisfiable Subset) and MCS (Minimal Correction Set) algorithms.
"""

import pytest
from pycsp3 import *
from pycsp3_explain.explain.mss import (
    mss,
    mss_naive,
    is_mss,
    mcs,
    mcs_naive,
    mcs_from_mss,
    is_mcs,
)
from pycsp3_explain.solvers.wrapper import is_sat, is_unsat


def constraint_in_list(constraint, constraint_list):
    """Check if constraint is in list using identity comparison."""
    return any(c is constraint for c in constraint_list)


class TestMssBasic:
    """Basic tests for MSS algorithms."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_sat(self):
        """Test MSS when all constraints are satisfiable."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] >= 0
        c1 = x[1] >= 0
        c2 = x[2] >= 0

        soft = [c0, c1, c2]

        # All constraints are SAT, MSS should contain all
        result = mss_naive(soft, solver="ace", verbose=-1)

        assert len(result) == 3
        assert constraint_in_list(c0, result)
        assert constraint_in_list(c1, result)
        assert constraint_in_list(c2, result)

    def test_simple_conflict(self):
        """Test MSS with a simple conflict."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7  # Conflicts with c0

        soft = [c0, c1, c2]

        # MSS should be of size 2 (either {c0, c1} or {c1, c2})
        result = mss_naive(soft, solver="ace", verbose=-1)

        assert len(result) == 2
        # c1 should be in MSS (doesn't conflict with anything)
        assert constraint_in_list(c1, result)
        # Either c0 or c2 should be in MSS (but not both)
        assert constraint_in_list(c0, result) != constraint_in_list(c2, result)

    def test_mss_with_hard_constraints(self):
        """Test MSS with hard constraints."""
        clear()

        x = VarArray(size=2, dom=range(10))

        hard = [x[0] >= 5]  # Hard: x[0] must be at least 5
        c0 = x[0] <= 3  # Conflicts with hard
        c1 = x[1] >= 0  # Independent

        soft = [c0, c1]
        result = mss_naive(soft, hard=hard, solver="ace", verbose=-1)

        # c0 conflicts with hard, so MSS should only contain c1
        assert len(result) == 1
        assert constraint_in_list(c1, result)
        assert not constraint_in_list(c0, result)

    def test_single_unsat_constraint(self):
        """Test MSS when a single constraint is unsatisfiable alone."""
        clear()

        x = Var(dom=range(5))

        c0 = x < 0  # UNSAT with domain [0,4]
        c1 = x >= 0  # SAT

        soft = [c0, c1]
        result = mss_naive(soft, solver="ace", verbose=-1)

        # c0 is UNSAT by itself, MSS should only contain c1
        assert len(result) == 1
        assert constraint_in_list(c1, result)

    def test_three_way_conflict(self):
        """Test MSS with a three-way conflict."""
        clear()

        x = Var(dom=range(10))

        # All pairs conflict
        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        # MSS should be of size 1 (any single constraint)
        result = mss_naive(soft, solver="ace", verbose=-1)

        assert len(result) == 1


class TestMssAssumptionBased:
    """Tests for assumption-based MSS algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_sat(self):
        """Test assumption-based MSS when all constraints are satisfiable."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] >= 0
        c1 = x[1] >= 0
        c2 = x[2] >= 0

        soft = [c0, c1, c2]
        result = mss(soft, solver="ace", verbose=-1)

        assert len(result) == 3

    def test_simple_conflict(self):
        """Test assumption-based MSS with a simple conflict."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7

        soft = [c0, c1, c2]
        result = mss(soft, solver="ace", verbose=-1)

        assert len(result) == 2
        assert constraint_in_list(c1, result)

    def test_mss_with_hard_constraints(self):
        """Test assumption-based MSS with hard constraints."""
        clear()

        x = VarArray(size=2, dom=range(10))

        hard = [x[0] >= 5]
        c0 = x[0] <= 3
        c1 = x[1] >= 0

        soft = [c0, c1]
        result = mss(soft, hard=hard, solver="ace", verbose=-1)

        assert len(result) == 1
        assert constraint_in_list(c1, result)


class TestIsMss:
    """Tests for MSS verification."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_is_mss_valid(self):
        """Test that a valid MSS is recognized."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]
        # {c0} is a valid MSS
        subset = [c0]

        assert is_mss(subset, soft, solver="ace", verbose=-1)

    def test_is_mss_not_maximal(self):
        """Test that a non-maximal subset is rejected."""
        clear()

        x = VarArray(size=2, dom=range(10))
        c0 = x[0] >= 0
        c1 = x[1] >= 0

        soft = [c0, c1]
        # {c0} is SAT but not maximal (can add c1)
        subset = [c0]

        assert is_mss(subset, soft, solver="ace", verbose=-1) is False

    def test_is_mss_unsat(self):
        """Test that an UNSAT subset is rejected."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]
        # {c0, c1} is UNSAT
        subset = [c0, c1]

        assert is_mss(subset, soft, solver="ace", verbose=-1) is False


class TestMcsBasic:
    """Basic tests for MCS algorithms."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_sat_model_empty_mcs(self):
        """Test MCS when model is already SAT."""
        clear()

        x = VarArray(size=2, dom=range(10))

        c0 = x[0] >= 0
        c1 = x[1] >= 0

        soft = [c0, c1]
        result = mcs_naive(soft, solver="ace", verbose=-1)

        # Model is SAT, no correction needed
        assert len(result) == 0

    def test_simple_conflict(self):
        """Test MCS with a simple conflict."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7  # Conflicts with c0

        soft = [c0, c1, c2]
        result = mcs_naive(soft, solver="ace", verbose=-1)

        # MCS should contain exactly one of {c0, c2}
        assert len(result) == 1
        assert constraint_in_list(c0, result) or constraint_in_list(c2, result)

    def test_mcs_from_mss_function(self):
        """Test mcs_from_mss helper function."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7

        soft = [c0, c1, c2]
        mss_result = mss_naive(soft, solver="ace", verbose=-1)
        mcs_result = mcs_from_mss(mss_result, soft)

        # MCS should be complement of MSS
        assert len(mcs_result) == len(soft) - len(mss_result)

        # Check that MSS and MCS are disjoint
        mss_ids = set(id(c) for c in mss_result)
        mcs_ids = set(id(c) for c in mcs_result)
        assert len(mss_ids & mcs_ids) == 0

        # Check that MSS + MCS = soft
        assert len(mss_result) + len(mcs_result) == len(soft)


class TestMcsAssumptionBased:
    """Tests for assumption-based MCS algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_sat_model_empty_mcs(self):
        """Test assumption-based MCS when model is already SAT."""
        clear()

        x = VarArray(size=2, dom=range(10))

        c0 = x[0] >= 0
        c1 = x[1] >= 0

        soft = [c0, c1]
        result = mcs(soft, solver="ace", verbose=-1)

        assert len(result) == 0

    def test_simple_conflict(self):
        """Test assumption-based MCS with a simple conflict."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7

        soft = [c0, c1, c2]
        result = mcs(soft, solver="ace", verbose=-1)

        assert len(result) == 1


class TestIsMcs:
    """Tests for MCS verification."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_is_mcs_valid(self):
        """Test that a valid MCS is recognized."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]
        # {c0} is a valid MCS (removing c0 leaves {c1} which is SAT)
        subset = [c0]

        assert is_mcs(subset, soft, solver="ace", verbose=-1)

    def test_is_mcs_not_minimal(self):
        """Test that a non-minimal correction set is rejected."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x >= 0  # Independent, doesn't affect conflict
        c2 = x == 7

        soft = [c0, c1, c2]
        # {c0, c1} is not minimal - removing just c0 (or c2) suffices
        subset = [c0, c1]

        assert is_mcs(subset, soft, solver="ace", verbose=-1) is False

    def test_is_mcs_complement_unsat(self):
        """Test that MCS with UNSAT complement is rejected."""
        clear()

        x = Var(dom=range(10))
        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]
        # Empty set is not a valid MCS (complement is full set which is UNSAT)
        subset = []

        assert is_mcs(subset, soft, solver="ace", verbose=-1) is False


class TestMssMcsRelationship:
    """Tests for the relationship between MSS and MCS."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_mss_mcs_complement(self):
        """Test that MSS and MCS are complements."""
        clear()

        x = VarArray(size=4, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7
        c3 = x[2] <= 8

        soft = [c0, c1, c2, c3]

        mss_result = mss_naive(soft, solver="ace", verbose=-1)
        mcs_result = mcs_naive(soft, solver="ace", verbose=-1)

        # MSS + MCS should cover all soft constraints
        mss_ids = set(id(c) for c in mss_result)
        mcs_ids = set(id(c) for c in mcs_result)
        soft_ids = set(id(c) for c in soft)

        assert mss_ids | mcs_ids == soft_ids
        assert len(mss_ids & mcs_ids) == 0

    def test_mcs_restores_sat(self):
        """Test that removing MCS from soft makes it SAT."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 3
        c2 = x[0] == 7

        soft = [c0, c1, c2]
        mcs_result = mcs_naive(soft, solver="ace", verbose=-1)

        # Remove MCS constraints
        mcs_ids = set(id(c) for c in mcs_result)
        remaining = [c for c in soft if id(c) not in mcs_ids]

        # Remaining should be SAT
        assert is_sat(remaining, solver="ace", verbose=-1)


class TestEdgeCases:
    """Edge case tests."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_empty_soft_returns_empty(self):
        """Test that empty soft constraints returns empty MSS."""
        result = mss_naive([], solver="ace")
        assert result == []

    def test_all_unsat(self):
        """Test MSS when all constraints are individually UNSAT."""
        clear()

        x = Var(dom=range(5))

        c0 = x < 0  # UNSAT
        c1 = x > 10  # UNSAT

        soft = [c0, c1]
        result = mss_naive(soft, solver="ace", verbose=-1)

        # Both constraints are UNSAT, MSS should be empty
        assert len(result) == 0

    def test_nested_constraints(self):
        """Test MSS with nested constraint lists."""
        clear()

        x = VarArray(size=3, dom=range(10))

        c0 = x[0] == 5
        c1 = x[1] >= 0
        c2 = x[0] == 7

        # Nested list
        soft = [[c0, c1], c2]
        result = mss_naive(soft, solver="ace", verbose=-1)

        # Should find an MSS of size 2
        assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
