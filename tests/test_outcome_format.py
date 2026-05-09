"""Tests for repl/outcome_format.py — user-friendly DispatchOutcome formatters."""

from __future__ import annotations

from fractions import Fraction

from hlmr.dispatch import (
    InfinitelyManySolutions,
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    OutsideFragmentReason,
    Underdetermined,
    UniqueSolution,
)
from hlmr.dispatch import ClassifyDecision, RouteTarget
from hlmr.ir.formula import Const, Func
from hlmr.repl.outcome_format import (
    format_classify_decision,
    format_outcome,
    format_substitution,
)
from hlmr.solve.sld import DispatcherResolvedStep


# ---------------------------------------------------------------------------
# format_substitution
# ---------------------------------------------------------------------------


def test_format_subst_empty():
    assert format_substitution({}) == "{}"


def test_format_subst_single_int():
    assert format_substitution({"?P": Const(5)}) == "{?P = 5}"


def test_format_subst_two_bindings():
    result = format_substitution({"?X": Const(2), "?Y": Const(8)})
    assert result == "{?X = 2, ?Y = 8}"


def test_format_subst_fraction():
    result = format_substitution({"?X": Const(Fraction(3, 2))})
    assert "3/2" in result or "Fraction" not in result


def test_format_subst_sorted():
    result = format_substitution({"?Z": Const(1), "?A": Const(2)})
    assert result.index("?A") < result.index("?Z")


# ---------------------------------------------------------------------------
# format_outcome — UniqueSolution
# ---------------------------------------------------------------------------


def test_format_unique_solution_with_binding():
    outcome = UniqueSolution(binding={"?P": Const(5)})
    s = format_outcome(outcome)
    assert "UniqueSolution" in s
    assert "?P" in s
    assert "5" in s


def test_format_unique_solution_empty_binding():
    outcome = UniqueSolution(binding={})
    s = format_outcome(outcome)
    assert "UniqueSolution" in s


# ---------------------------------------------------------------------------
# format_outcome — MultipleSolutions
# ---------------------------------------------------------------------------


def test_format_multiple_solutions():
    sol1 = {"?X": Const(2)}
    sol2 = {"?X": Const(3)}
    # Need steps — use minimal DispatcherResolvedStep stubs.
    from hlmr.ir.formula import Atom, Equals
    from hlmr.ir.formula import Func, Var
    ground = Equals(Const(0), Const(0))
    step1 = DispatcherResolvedStep(
        goal_resolved=ground,
        ground_atom=ground,
        route=RouteTarget.SYMPY,
        binding_added=sol1,
        solver_summary="test",
    )
    step2 = DispatcherResolvedStep(
        goal_resolved=ground,
        ground_atom=ground,
        route=RouteTarget.SYMPY,
        binding_added=sol2,
        solver_summary="test",
    )
    outcome = MultipleSolutions(
        solutions=(sol1, sol2),
        steps=(step1, step2),
    )
    s = format_outcome(outcome)
    assert "MultipleSolutions" in s
    assert "n=2" in s
    assert "[0]" in s
    assert "[1]" in s


# ---------------------------------------------------------------------------
# format_outcome — NoSolution
# ---------------------------------------------------------------------------


def test_format_no_solution():
    s = format_outcome(NoSolution())
    assert "NoSolution" in s


# ---------------------------------------------------------------------------
# format_outcome — Underdetermined
# ---------------------------------------------------------------------------


def test_format_underdetermined():
    outcome = Underdetermined(
        partial_binding={"?X": Const(5)},
        unbound=("?Y", "?Z"),
    )
    s = format_outcome(outcome)
    assert "Underdetermined" in s
    assert "?Y" in s
    assert "?Z" in s


def test_format_underdetermined_no_unbound():
    outcome = Underdetermined(partial_binding={"?X": Const(5)}, unbound=())
    s = format_outcome(outcome)
    assert "Underdetermined" in s


# ---------------------------------------------------------------------------
# format_outcome — OutsideFragment
# ---------------------------------------------------------------------------


def test_format_outside_fragment_transcendental():
    outcome = OutsideFragment(
        classification=OutsideFragmentReason.TRANSCENDENTAL,
        reason="exponent contains a variable",
    )
    s = format_outcome(outcome)
    assert "OutsideFragment" in s
    assert "transcendental" in s


def test_format_outside_fragment_contested():
    outcome = OutsideFragment(
        classification=OutsideFragmentReason.CONTESTED_CONVENTION,
        reason="0^0 is contested",
    )
    s = format_outcome(outcome)
    assert "contested_convention" in s


def test_format_outside_fragment_solver_timeout():
    outcome = OutsideFragment(
        classification=OutsideFragmentReason.SOLVER_TIMEOUT,
        reason="Z3 timed out",
    )
    s = format_outcome(outcome)
    assert "solver_timeout" in s


# ---------------------------------------------------------------------------
# format_outcome — InfinitelyManySolutions
# ---------------------------------------------------------------------------


def test_format_infinitely_many_solutions():
    outcome = InfinitelyManySolutions(
        example={"?X": Const(5)},
        free_metas=("?Y",),
    )
    s = format_outcome(outcome)
    assert "InfinitelyManySolutions" in s
    assert "?Y" in s


# ---------------------------------------------------------------------------
# format_classify_decision
# ---------------------------------------------------------------------------


def test_format_classify_decision_kb():
    d = ClassifyDecision(target=RouteTarget.KB)
    s = format_classify_decision(d)
    assert "kb" in s


def test_format_classify_decision_z3():
    d = ClassifyDecision(target=RouteTarget.Z3)
    s = format_classify_decision(d)
    assert "z3" in s


def test_format_classify_decision_rejected_with_reason():
    d = ClassifyDecision(
        target=RouteTarget.REJECTED,
        reason=OutsideFragmentReason.TRANSCENDENTAL,
    )
    s = format_classify_decision(d)
    assert "rejected" in s
    assert "transcendental" in s
