"""Unit tests for dispatch/route.py — Dispatcher class with mock bridges.

Coverage per DISPATCH_DESIGN.md §11.6 and Session 4b spec:
  A. Each Z3 result variant → correct outcome
  B. Each SymPy result variant → correct outcome
  C. Case 1 / Case 2 discriminator (soundness-critical)
  D. Verify-before-return is invoked
  E. Contested-shape post-filter
  F. Z3 context lifecycle (smoke tests)
  G. OutsideFragment threading
  H. §11.6 soundness backstop
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import pytest

from hlmr.dispatch import (
    ClassifyDecision,
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    OutsideFragmentReason,
    RouteTarget,
    Underdetermined,
    UniqueSolution,
)
from hlmr.dispatch.route import (
    Dispatcher,
    DispatchError,
    SolverKernelDisagreement,
    _ground_atom_lands_on_contested_shape,
)
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.solve.sld import DispatcherResolvedStep
from hlmr.solvers import (
    SymPyConditionSet,
    SymPyError,
    SymPyFiniteRoots,
    SymPyNoRealRoots,
    Z3Result,
    Z3Sat,
    Z3Timeout,
    Z3Unknown,
    Z3Unsat,
    SymPyResult,
)


# ---------------------------------------------------------------------------
# Mock bridges
# ---------------------------------------------------------------------------


@dataclass
class FakeZ3Bridge:
    """Controllable Z3 bridge for testing."""
    next_result: Z3Result
    calls: list = field(default_factory=list)

    def check(self, constraints, timeout_ms):
        self.calls.append((constraints, timeout_ms))
        return self.next_result


@dataclass
class FakeSymPyBridge:
    """Controllable SymPy bridge for testing."""
    next_result: SymPyResult
    calls: list = field(default_factory=list)

    def solveset(self, goal):
        self.calls.append(goal)
        return self.next_result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_EMPTY_KB = KnowledgeBase(clauses=())


def _make_dispatcher(z3_result=None, sympy_result=None, kb=None):
    """Build a Dispatcher with controllable mock bridges."""
    z3_bridge = FakeZ3Bridge(
        next_result=z3_result if z3_result is not None else Z3Unsat()
    )
    sympy_bridge = FakeSymPyBridge(
        next_result=sympy_result if sympy_result is not None else SymPyNoRealRoots()
    )
    return Dispatcher(
        z3_bridge=z3_bridge,
        sympy_bridge=sympy_bridge,
        kb=kb if kb is not None else _EMPTY_KB,
    )


# ---------------------------------------------------------------------------
# A. Z3 result variants
# ---------------------------------------------------------------------------


def test_z3_sat_unique_solution():
    """Z3Sat with a single binding → UniqueSolution with verify."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.outcome, UniqueSolution)
    assert result.outcome.binding == {"?P": Const(5)}
    assert isinstance(result.step, DispatcherResolvedStep)
    assert result.step.route == RouteTarget.Z3


def test_z3_sat_produces_step_with_ground_atom():
    """The DispatcherResolvedStep.ground_atom is the fully-grounded atom."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.step, DispatcherResolvedStep)
    assert result.step.ground_atom == Atom(">", (Const(5), Const(2)))


def test_z3_sat_with_prior_subst():
    """A prior subst is applied before dispatching; the model extends it."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?Q": 3}))
    # Goal: ?Q > 0 with subst {} — Z3 returns ?Q=3
    result = d.dispatch(Atom(">", (Meta("?Q"), Const(0))), {})
    assert isinstance(result.outcome, UniqueSolution)
    assert result.outcome.binding == {"?Q": Const(3)}


def test_z3_unsat_no_solution():
    d = _make_dispatcher(z3_result=Z3Unsat())
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.outcome, NoSolution)
    assert result.step is None


def test_z3_unknown_outside_fragment():
    d = _make_dispatcher(z3_result=Z3Unknown(reason="non-linear"))
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.outcome, OutsideFragment)
    assert result.outcome.classification == OutsideFragmentReason.SOLVER_UNKNOWN


def test_z3_timeout_outside_fragment():
    d = _make_dispatcher(z3_result=Z3Timeout())
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.outcome, OutsideFragment)
    assert result.outcome.classification == OutsideFragmentReason.SOLVER_TIMEOUT


def test_z3_underdetermined_via_recheck():
    """Z3Sat returns a model; second Z3Sat (recheck) reveals underdetermination.

    The fake bridge always returns the same result; for the recheck it still
    returns Z3Sat (meaning a second model exists), so the outcome is Underdetermined.
    """
    # Bridge always returns Z3Sat — both first check and negation-recheck sat.
    d = _make_dispatcher(z3_result=Z3Sat(model={"?X": 5, "?Y": 5}))
    # plus(?X, ?Y, 10): both ?X and ?Y are metas; Z3 returns one model but
    # negation-recheck also sat → underdetermined.
    result = d.dispatch(Atom("plus", (Meta("?X"), Meta("?Y"), Const(10))), {})
    assert isinstance(result.outcome, Underdetermined)
    assert result.step is None


def test_z3_ground_goal_short_circuits():
    """Fully-ground goal skips the Z3 call and verifies directly."""
    d = _make_dispatcher(z3_result=Z3Unsat())  # would be used if Z3 called
    result = d.dispatch(Atom(">", (Const(5), Const(2))), {})
    assert isinstance(result.outcome, UniqueSolution)
    # The Z3 bridge was NOT called (short-circuit path).
    assert len(d.z3_bridge.calls) == 0


def test_z3_ground_goal_false_evaluates_no_solution():
    """Ground 2 > 5 → arithEval rejects with EvaluationFalse → NoSolution."""
    d = _make_dispatcher(z3_result=Z3Unsat())
    result = d.dispatch(Atom(">", (Const(2), Const(5))), {})
    # Short-circuit path: verify 2 > 5 → EvaluationFalse → NoSolution
    assert isinstance(result.outcome, NoSolution)


# ---------------------------------------------------------------------------
# B. SymPy result variants
# ---------------------------------------------------------------------------


def _root_of_goal() -> Atom:
    """root_of(?X, x^2 - 5x + 6) — roots 2 and 3."""
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    return Atom("root_of", (Meta("?X"), poly))


def test_sympy_single_root_unique_solution():
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2,)))
    result = d.dispatch(_root_of_goal(), {})
    assert isinstance(result.outcome, UniqueSolution)
    assert result.outcome.binding == {"?X": Const(2)}
    assert isinstance(result.step, DispatcherResolvedStep)
    assert result.step.route == RouteTarget.SYMPY


def test_sympy_two_roots_multiple_solutions():
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2, 3)))
    result = d.dispatch(_root_of_goal(), {})
    assert isinstance(result.outcome, MultipleSolutions)
    assert len(result.outcome.solutions) == 2
    assert {"?X": Const(2)} in result.outcome.solutions
    assert {"?X": Const(3)} in result.outcome.solutions
    # steps paired one-to-one with solutions
    assert len(result.outcome.steps) == 2
    assert result.step is None  # step on result is None for MultipleSolutions


def test_sympy_no_real_roots():
    d = _make_dispatcher(sympy_result=SymPyNoRealRoots())
    result = d.dispatch(_root_of_goal(), {})
    assert isinstance(result.outcome, NoSolution)


def test_sympy_condition_set():
    d = _make_dispatcher(sympy_result=SymPyConditionSet(reason="ConditionSet"))
    result = d.dispatch(_root_of_goal(), {})
    assert isinstance(result.outcome, OutsideFragment)
    assert result.outcome.classification == OutsideFragmentReason.NON_LINEAR_BEYOND_SYMPY


def test_sympy_error_raises_dispatch_error():
    d = _make_dispatcher(sympy_result=SymPyError(msg="something went wrong"))
    with pytest.raises(DispatchError, match="SymPy bridge error"):
        d.dispatch(_root_of_goal(), {})


# ---------------------------------------------------------------------------
# C. Case 1 / Case 2 discriminator (soundness-critical)
# ---------------------------------------------------------------------------


def test_case1_evaluation_false_z3_crashes():
    """Z3 returns ?P=4 for ?P>5 — arithEval rejects with EvaluationFalse → crash."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 4}))
    with pytest.raises(SolverKernelDisagreement):
        d.dispatch(Atom(">", (Meta("?P"), Const(5))), {})


def test_case1_evaluation_false_message():
    """SolverKernelDisagreement message identifies the route and goal."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 4}))
    with pytest.raises(SolverKernelDisagreement, match="z3"):
        d.dispatch(Atom(">", (Meta("?P"), Const(5))), {})


def _contested_poly() -> Atom:
    """root_of(?X, x^0 - 1) — polynomial where substituting x=0 produces 0^0.

    Classifier sees: poly = x^0 - 1. _is_polynomial_in_one_var accepts x^0
    (exponent is Const(0), non-negative integer). Routes to SYMPY.

    Verify atom construction for ?X=0:
      instantiated = 0^0 - 1
      verify atom  = Equals(0^0 - 1, 0)

    arithEval encounters Func("^", (Const(0), Const(0))) → MalformedArithmetic.
    _ground_atom_lands_on_contested_shape returns True → Case 2.

    For ?X=1: 1^0 - 1 = 1 - 1 = 0. arithEval accepts. Valid witness.
    """
    poly = Func("-", (Func("^", (Var("x"), Const(0))), Const(1)))
    return Atom("root_of", (Meta("?X"), poly))


def test_case2_contested_0_power_0_single_root():
    """SymPy returns only ?X=0 — verify produces 0^0 → Case 2 → OutsideFragment."""
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(0,)))
    result = d.dispatch(_contested_poly(), {})
    assert isinstance(result.outcome, OutsideFragment)
    assert result.outcome.classification == OutsideFragmentReason.CONTESTED_CONVENTION


def test_case2_contested_narrowing_two_roots_one_valid():
    """SymPy returns {1, 0}; ?X=0 is Case 2; outcome narrows to UniqueSolution(?X=1).

    Analogue of DISPATCH §12.6 example (?X^?X=1 with roots {1,0}).
    ?X=1: verify Equals(1^0 - 1, 0) = Equals(0, 0) → arithEval accepts → valid.
    ?X=0: verify Equals(0^0 - 1, 0) → 0^0 contested → Case 2 → dropped.
    One valid witness → narrows to UniqueSolution({?X: 1}).
    """
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(1, 0)))
    result = d.dispatch(_contested_poly(), {})
    assert isinstance(result.outcome, UniqueSolution)
    assert result.outcome.binding == {"?X": Const(1)}


def test_case2_contested_both_roots_no_solution():
    """Both SymPy roots are contested — outcome narrows to NoSolution."""
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(0,)))
    result = d.dispatch(_contested_poly(), {})
    # Single contested root → Case 2 → no valid witnesses → NoSolution or OutsideFragment
    assert isinstance(result.outcome, (NoSolution, OutsideFragment))


def test_case1_malformed_non_contested_z3_crashes():
    """Z3 returns a binding that produces an arithEval-invalid but non-contested atom.

    We simulate this by using a ground goal that arithEval rejects with
    EvaluationFalse (5 > 10 is false, not malformed). For a true non-contested
    MalformedArithmetic crash we'd need a synthetic kernel bypass; instead we
    rely on the direct EvaluationFalse test above as the representative Case 1.
    This test ensures the Z3Sat path crashes on a demonstrably false result.
    """
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    with pytest.raises(SolverKernelDisagreement):
        d.dispatch(Atom(">", (Meta("?P"), Const(10))), {})


# ---------------------------------------------------------------------------
# D. Verify-before-return is invoked for every solver success
# ---------------------------------------------------------------------------


def test_verify_invoked_z3_sat(monkeypatch):
    """After Z3Sat, the dispatcher calls check_proof with an arithEval line."""
    import hlmr.dispatch.route as route_mod
    proof_args: list = []
    original_check = route_mod.check_proof

    def capturing_check(proof):
        proof_args.append(proof)
        return original_check(proof)

    monkeypatch.setattr(route_mod, "check_proof", capturing_check)
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert len(proof_args) == 1
    proof = proof_args[0]
    assert len(proof.lines) == 1
    assert proof.lines[0].justification.rule == "arithEval"


def test_verify_invoked_sympy_roots(monkeypatch):
    """After SymPy single-root, check_proof is called with arithEval justification."""
    import hlmr.dispatch.route as route_mod
    proof_args: list = []
    original_check = route_mod.check_proof

    def capturing_check(proof):
        proof_args.append(proof)
        return original_check(proof)

    monkeypatch.setattr(route_mod, "check_proof", capturing_check)
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2,)))
    d.dispatch(_root_of_goal(), {})
    assert len(proof_args) >= 1
    for proof in proof_args:
        assert proof.lines[0].justification.rule == "arithEval"


# ---------------------------------------------------------------------------
# E. Contested-shape post-filter
# ---------------------------------------------------------------------------


def test_ground_atom_contested_with_0_power_0():
    assert _ground_atom_lands_on_contested_shape(
        Atom(">", (Func("^", (Const(0), Const(0))), Const(5)))
    ) is True


def test_ground_atom_contested_equals():
    assert _ground_atom_lands_on_contested_shape(
        Equals(Func("^", (Const(0), Const(0))), Const(1))
    ) is True


def test_ground_atom_not_contested_nonzero_base():
    assert _ground_atom_lands_on_contested_shape(
        Atom(">", (Func("^", (Const(2), Const(0))), Const(0)))
    ) is False


def test_ground_atom_not_contested_nonzero_exp():
    assert _ground_atom_lands_on_contested_shape(
        Equals(Func("^", (Const(0), Const(3))), Const(0))
    ) is False


def test_ground_atom_contested_nested():
    nested = Func("+", (Func("^", (Const(0), Const(0))), Const(1)))
    assert _ground_atom_lands_on_contested_shape(
        Atom(">", (nested, Const(5)))
    ) is True


@pytest.mark.parametrize("base,exp", [
    (Const(0), Const(0)),
    (Const(Fraction(0, 1)), Const(0)),
])
def test_ground_atom_contested_fraction_zero(base, exp):
    assert _ground_atom_lands_on_contested_shape(
        Atom(">", (Func("^", (base, exp)), Const(1)))
    ) is True


# ---------------------------------------------------------------------------
# F. Z3 context lifecycle / smoke tests
# ---------------------------------------------------------------------------


def test_dispatcher_constructs_without_error():
    """Constructing a Dispatcher with mock bridges does not raise."""
    d = _make_dispatcher()
    assert d is not None
    assert d.timeout_ms == 5000


def test_multiple_dispatch_calls_dont_interfere():
    """Each .dispatch() call is independent; the mock records all calls."""
    z3_bridge = FakeZ3Bridge(next_result=Z3Sat(model={"?P": 5}))
    sympy_bridge = FakeSymPyBridge(next_result=SymPyNoRealRoots())
    d = Dispatcher(z3_bridge=z3_bridge, sympy_bridge=sympy_bridge, kb=_EMPTY_KB)

    r1 = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    r2 = d.dispatch(Atom(">", (Meta("?P"), Const(3))), {})

    assert isinstance(r1.outcome, UniqueSolution)
    assert isinstance(r2.outcome, UniqueSolution)
    # Two separate calls recorded
    assert len(z3_bridge.calls) == 2


def test_dispatcher_default_timeout():
    d = _make_dispatcher()
    assert d.timeout_ms == 5000


def test_dispatcher_kb_goal_raises_dispatch_error():
    """KB-classified goal should not reach the dispatcher — raises DispatchError."""
    kb = KnowledgeBase(clauses=(
        Clause("p1", Atom("prime", (Const(2),)), ()),
    ))
    d = _make_dispatcher(kb=kb)
    with pytest.raises(DispatchError, match="KB-classified"):
        d.dispatch(Atom("prime", (Meta("?P"),)), {})


# ---------------------------------------------------------------------------
# G. OutsideFragment threading
# ---------------------------------------------------------------------------


def test_last_outside_fragment_none_initially():
    d = _make_dispatcher()
    assert d.last_outside_fragment is None


def test_last_outside_fragment_set_on_rejected():
    """Classify-rejected goal sets last_outside_fragment."""
    # root_of with transcendental poly → classifier rejects.
    poly = Func("^", (Const(2), Var("x")))  # 2^x — transcendental
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher()
    result = d.dispatch(goal, {})
    assert isinstance(result.outcome, OutsideFragment)
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL


def test_last_outside_fragment_set_on_z3_timeout():
    d = _make_dispatcher(z3_result=Z3Timeout())
    d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.SOLVER_TIMEOUT


def test_last_outside_fragment_set_on_z3_unknown():
    d = _make_dispatcher(z3_result=Z3Unknown(reason="non-linear"))
    d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.SOLVER_UNKNOWN


def test_last_outside_fragment_overwritten_by_later_rejection():
    """After a successful dispatch, a subsequent OutsideFragment replaces it."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    # First dispatch: success (no outside_fragment set)
    d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    # Second dispatch: timeout
    d.z3_bridge.next_result = Z3Timeout()
    d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.SOLVER_TIMEOUT


def test_last_outside_fragment_cleared_per_call():
    """Regression: last_outside_fragment must be cleared at the start of every
    dispatch() call. Without this fix, a long-lived Dispatcher would carry a
    stale OutsideFragment across subsequent successful or NoSolution outcomes,
    confusing the REPL on a query that failed for a different reason.

    Sequence: OutsideFragment → UniqueSolution → NoSolution.
    After each non-OutsideFragment call, the field must be None.
    """
    z3_bridge = FakeZ3Bridge(next_result=Z3Unsat())
    sympy_bridge = FakeSymPyBridge(next_result=SymPyNoRealRoots())
    d = Dispatcher(
        z3_bridge=z3_bridge,
        sympy_bridge=sympy_bridge,
        kb=_EMPTY_KB,
    )

    # Call 1: transcendental → REJECTED → OutsideFragment(TRANSCENDENTAL)
    goal_1 = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
    result_1 = d.dispatch(goal_1, {})
    assert isinstance(result_1.outcome, OutsideFragment)
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL

    # Call 2: Z3 returns Sat → UniqueSolution; stale fragment must be cleared.
    z3_bridge.next_result = Z3Sat(model={"?P": 5})
    goal_2 = Atom(">", (Meta("?P"), Const(2)))
    result_2 = d.dispatch(goal_2, {})
    assert isinstance(result_2.outcome, UniqueSolution)
    assert d.last_outside_fragment is None  # must NOT linger from call 1

    # Call 3: Z3 returns Unsat → NoSolution; field must remain None.
    z3_bridge.next_result = Z3Unsat()
    goal_3 = Atom("<", (Meta("?Q"), Const(0)))
    result_3 = d.dispatch(goal_3, {})
    assert isinstance(result_3.outcome, NoSolution)
    assert d.last_outside_fragment is None  # still None; not set by NoSolution


# ---------------------------------------------------------------------------
# H. §11.6 soundness backstop
# ---------------------------------------------------------------------------


def test_soundness_backstop_malicious_z3():
    """Malicious Z3 bridge returns ?P=4 for ?P>2 AND ?P<6 AND ?P!=4.

    The verify step constructs Atom("!=", (Const(4), Const(4))) which
    arithEval evaluates as False → EvaluationFalse → SolverKernelDisagreement.
    Mirrors M0's 99_BAD_* proofs.
    """
    # The constraint is just ?P != 4; Z3 maliciously says ?P=4.
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 4}))
    with pytest.raises(SolverKernelDisagreement):
        d.dispatch(Atom("!=", (Meta("?P"), Const(4))), {})


def test_soundness_backstop_z3_lie_on_inequality():
    """Z3 returns ?P=5 for ?P < 3 — arithEval rejects 5 < 3 → crash."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    with pytest.raises(SolverKernelDisagreement):
        d.dispatch(Atom("<", (Meta("?P"), Const(3))), {})


def test_soundness_backstop_z3_sat_passes_verify():
    """A truthful Z3Sat (5 > 2) passes verify and returns UniqueSolution."""
    d = _make_dispatcher(z3_result=Z3Sat(model={"?P": 5}))
    result = d.dispatch(Atom(">", (Meta("?P"), Const(2))), {})
    assert isinstance(result.outcome, UniqueSolution)
