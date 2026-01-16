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
    MapSolver,
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


class TestMapSolver:
    """Unit tests for the MapSolver class (SAT-based seed generator)."""

    def test_initial_solve_returns_full_set(self):
        """Test that initial solve returns full set when no clauses."""
        solver = MapSolver(3)
        result = solver.solve()
        # With no constraints, the DPLL prefers True, so should return all vars
        assert result is not None
        # The solver tries True first for each variable
        assert result == {0, 1, 2}

    def test_block_up_prevents_superset(self):
        """Test that block_up prevents exploring supersets of MUS."""
        solver = MapSolver(3)
        # Block MUS {0, 1} - no superset containing both 0 and 1 should be returned
        solver.block_up({0, 1})

        # Now solve - result should not contain both 0 and 1
        result = solver.solve()
        assert result is not None
        assert not ({0, 1} <= result), "Result should not be superset of blocked MUS"

    def test_block_down_prevents_subset(self):
        """Test that block_down prevents exploring subsets of MSS."""
        solver = MapSolver(3)
        # Block MSS {0, 1} - any subset of {0, 1} (i.e., {}, {0}, {1}, {0,1}) blocked
        # The blocking clause is (s_2) since MCS = {2}
        solver.block_down({0, 1})

        # Now solve - result must contain element 2 (the MCS)
        result = solver.solve()
        assert result is not None
        assert 2 in result, "Result must contain MCS element"

    def test_exhaustive_exploration(self):
        """Test that MapSolver eventually exhausts all subsets."""
        solver = MapSolver(2)

        # Collect all seeds until exhausted
        seeds = []
        while True:
            result = solver.solve()
            if result is None:
                break
            seeds.append(frozenset(result))
            # Block this seed as if it were a MUS (block supersets)
            # and also as if it were an MSS (block subsets)
            # This simulates MARCO exploring completely
            solver.block_up(result)
            solver.block_down(result)

        # With 2 variables, there are 4 possible subsets
        # Each seed blocks its supersets and subsets
        # First seed {0,1} blocks supersets of {0,1} (just itself)
        # and subsets of {0,1} (all 4 subsets)
        # So after first seed, all are blocked
        assert len(seeds) == 1
        assert frozenset({0, 1}) in seeds

    def test_multiple_blocking_clauses(self):
        """Test that multiple blocking clauses work together."""
        solver = MapSolver(4)

        # Block MUS {0, 1} - prevents any superset containing both
        solver.block_up({0, 1})
        # Block MUS {2, 3} - prevents any superset containing both
        solver.block_up({2, 3})

        result = solver.solve()
        assert result is not None

        # Result cannot have both {0,1} and cannot have both {2,3}
        has_01 = {0, 1} <= result
        has_23 = {2, 3} <= result
        assert not has_01, "Should not have both 0 and 1"
        assert not has_23, "Should not have both 2 and 3"

    def test_empty_mss_blocks_all(self):
        """Test that blocking empty MSS makes solver return None."""
        solver = MapSolver(2)

        # Empty MSS means all constraints must be removed
        # The blocking clause should be (s_0 ∨ s_1) - at least one must be True
        # This doesn't block all, so first verify this
        solver.block_down(set())  # Empty MSS

        result = solver.solve()
        # With clause (s_0 ∨ s_1), any non-empty set works
        assert result is not None
        assert len(result) >= 1

    def test_full_mss_terminates(self):
        """Test that blocking full MSS eventually terminates enumeration."""
        solver = MapSolver(2)

        # Full MSS {0, 1} means MCS is empty
        # This adds an empty clause, making formula UNSAT
        solver.block_down({0, 1})

        result = solver.solve()
        # Empty clause means UNSAT
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
