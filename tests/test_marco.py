"""
Tests for MARCO algorithm (MUS/MCS enumeration).
"""

import pytest
from pycsp3 import *
from pycsp3_explain.explain.marco import (
    marco,
    marco_naive,
    all_mus,
    all_mcs,
)
from pycsp3_explain.explain.mus import is_mus
from pycsp3_explain.explain.mss import is_mcs


def constraint_in_list(constraint, constraint_list):
    """Check if constraint is in list using identity comparison."""
    return any(c is constraint for c in constraint_list)


class TestMarcoBasic:
    """Basic tests for MARCO algorithm."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_conflict_enumerate(self):
        """Test MARCO on a simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7  # Conflicts with c0

        soft = [c0, c1]

        results = list(marco(soft, solver="ace", verbose=-1))

        # Should find exactly one MUS (both constraints)
        muses = [s for t, s in results if t == "MUS"]
        mcses = [s for t, s in results if t == "MCS"]

        assert len(muses) == 1
        assert len(muses[0]) == 2

        # Should find two MCSes (removing either c0 or c1)
        assert len(mcses) == 2
        for mcs in mcses:
            assert len(mcs) == 1

    def test_three_way_conflict(self):
        """Test MARCO with multiple MUSes."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        results = list(marco(soft, solver="ace", verbose=-1))

        muses = [s for t, s in results if t == "MUS"]
        mcses = [s for t, s in results if t == "MCS"]

        # All pairs conflict, so 3 MUSes
        assert len(muses) == 3
        for mus_result in muses:
            assert len(mus_result) == 2

        # 3 MCSes (removing any one constraint)
        assert len(mcses) == 3
        for mcs_result in mcses:
            assert len(mcs_result) == 2  # Need to remove 2 to leave just 1

    def test_mus_only(self):
        """Test MARCO returning only MUSes."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        results = list(marco(soft, return_mus=True, return_mcs=False, solver="ace", verbose=-1))

        assert all(t == "MUS" for t, s in results)
        assert len(results) == 1

    def test_mcs_only(self):
        """Test MARCO returning only MCSes."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        results = list(marco(soft, return_mus=False, return_mcs=True, solver="ace", verbose=-1))

        assert all(t == "MCS" for t, s in results)
        assert len(results) == 2


class TestAllMus:
    """Tests for all_mus convenience function."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_all_mus_simple(self):
        """Test all_mus on a simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        muses = all_mus(soft, solver="ace", verbose=-1)

        assert len(muses) == 1
        assert len(muses[0]) == 2

    def test_all_mus_with_limit(self):
        """Test all_mus with max_mus limit."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        muses = all_mus(soft, max_mus=2, solver="ace", verbose=-1)

        assert len(muses) <= 2
        assert len(muses) >= 1


class TestAllMcs:
    """Tests for all_mcs convenience function."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_all_mcs_simple(self):
        """Test all_mcs on a simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        mcses = all_mcs(soft, solver="ace", verbose=-1)

        assert len(mcses) == 2
        for mcs in mcses:
            assert len(mcs) == 1

    def test_all_mcs_with_limit(self):
        """Test all_mcs with max_mcs limit."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        mcses = all_mcs(soft, max_mcs=2, solver="ace", verbose=-1)

        assert len(mcses) <= 2
        assert len(mcses) >= 1


class TestMarcoNaive:
    """Tests for naive MARCO implementation."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_simple_conflict(self):
        """Test marco_naive on a simple conflict."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 5
        c1 = x == 7

        soft = [c0, c1]

        results = list(marco_naive(soft, solver="ace", verbose=-1))

        muses = [s for t, s in results if t == "MUS"]
        mcses = [s for t, s in results if t == "MCS"]

        assert len(muses) == 1
        assert len(mcses) == 2


class TestMarcoWithHard:
    """Tests for MARCO with hard constraints."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_hard_constraint_conflict(self):
        """Test MARCO when soft conflicts with hard."""
        clear()

        x = VarArray(size=2, dom=range(10))

        hard = [x[0] >= 5]  # x[0] must be at least 5
        c0 = x[0] <= 3      # Conflicts with hard
        c1 = x[1] >= 0      # Independent

        soft = [c0, c1]

        results = list(marco(soft, hard=hard, solver="ace", verbose=-1))

        muses = [s for t, s in results if t == "MUS"]

        # c0 alone is UNSAT with hard, so should be a MUS
        assert len(muses) >= 1
        # At least one MUS should contain only c0
        sizes = [len(m) for m in muses]
        assert 1 in sizes


class TestMarcoValidation:
    """Tests to validate MARCO results."""

    def setup_method(self):
        """Clear PyCSP3 state before each test."""
        clear()

    def test_all_muses_valid(self):
        """Test that all discovered MUSes are valid."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        for result_type, subset in marco(soft, solver="ace", verbose=-1):
            if result_type == "MUS":
                assert is_mus(subset, solver="ace", verbose=-1), \
                    f"Invalid MUS: {subset}"

    def test_all_mcses_valid(self):
        """Test that all discovered MCSes are valid."""
        clear()

        x = Var(dom=range(10))

        c0 = x == 1
        c1 = x == 2
        c2 = x == 3

        soft = [c0, c1, c2]

        for result_type, subset in marco(soft, solver="ace", verbose=-1):
            if result_type == "MCS":
                assert is_mcs(subset, soft, solver="ace", verbose=-1), \
                    f"Invalid MCS: {subset}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
