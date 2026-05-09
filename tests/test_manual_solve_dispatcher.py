"""Integration tests for manual_solve with the M2 dispatcher.

Tests M2 mode (dispatcher provided) while preserving M1 mode parity.
Updated in Session 5b: the renderer now handles DispatcherResolvedStep and
multi-goal queries, so tests previously expecting proof=None now assert
kernel-verified proofs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import pytest

from hlmr.dispatch.route import Dispatcher, SolverKernelDisagreement
from hlmr.dispatch import (
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    OutsideFragmentReason,
    Underdetermined,
    UniqueSolution,
)
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.solve import manual_solve
from hlmr.solve.sld import ClauseResolvedStep, DispatcherResolvedStep
from hlmr.solvers import (
    SymPyFiniteRoots,
    SymPyNoRealRoots,
    Z3Result,
    Z3Sat,
    Z3Unsat,
    SymPyResult,
)


# ---------------------------------------------------------------------------
# Mock bridges (same pattern as test_dispatch_route.py)
# ---------------------------------------------------------------------------


@dataclass
class FakeZ3Bridge:
    next_result: Z3Result
    calls: list = field(default_factory=list)

    def check(self, constraints, timeout_ms):
        self.calls.append((constraints, timeout_ms))
        return self.next_result


@dataclass
class FakeSymPyBridge:
    next_result: SymPyResult
    calls: list = field(default_factory=list)

    def solveset(self, goal):
        self.calls.append(goal)
        return self.next_result


# ---------------------------------------------------------------------------
# KB fixtures
# ---------------------------------------------------------------------------

_FACT_P_A = Clause("p_a", Atom("p", (Const("a"),)), ())
_FACT_Q_B = Clause("q_b", Atom("q", (Const("b"),)), ())
_FACT_P_5 = Clause("p_5", Atom("p", (Const(5),)), ())

_KB_PQ = KnowledgeBase(clauses=(_FACT_P_A, _FACT_Q_B))
_KB_P5 = KnowledgeBase(clauses=(_FACT_P_5,))
_EMPTY_KB = KnowledgeBase(clauses=())


def _first_picker(cs, _state):
    return 0 if cs else None


def _make_dispatcher(z3_result=None, sympy_result=None, kb=None):
    z3b = FakeZ3Bridge(next_result=z3_result or Z3Unsat())
    spb = FakeSymPyBridge(next_result=sympy_result or SymPyNoRealRoots())
    return Dispatcher(
        z3_bridge=z3b,
        sympy_bridge=spb,
        kb=kb if kb is not None else _EMPTY_KB,
    )


# ---------------------------------------------------------------------------
# A. M1 mode parity (dispatcher=None)
# ---------------------------------------------------------------------------


def test_m1_parity_single_goal_kb():
    """M1 mode unchanged: single goal, KB fact, returns verified proof."""
    result = manual_solve(_KB_PQ, Atom("p", (Meta("?X"),)), _first_picker)
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert sat.get("?X") == Const("a")


def test_m1_parity_no_match_returns_none():
    """M1 mode: no matching clause → None."""
    result = manual_solve(_KB_PQ, Atom("r", (Meta("?X"),)), _first_picker)
    assert result is None


def test_m1_parity_picker_abort():
    """M1 mode: picker returns None → None."""
    result = manual_solve(_KB_PQ, Atom("p", (Meta("?X"),)), lambda cs, s: None)
    assert result is None


def test_m1_parity_multi_goal_tuple_renders():
    """M1 mode with tuple goals: renderer now handles multi-goal (Session 5b).
    Returns (sat, kernel-verified proof) with andI chain at the end."""
    result = manual_solve(
        _KB_PQ,
        (Atom("p", (Meta("?X"),)), Atom("q", (Meta("?Y"),))),
        _first_picker,
        dispatcher=None,
    )
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    assert sat.get("?X") == Const("a")
    assert sat.get("?Y") == Const("b")


# ---------------------------------------------------------------------------
# B. M2 mode, KB-only single goal — still renders
# ---------------------------------------------------------------------------


def test_m2_mode_kb_goal_renders():
    """KB-only single goal in M2 mode still produces a verified proof."""
    d = _make_dispatcher(kb=_KB_P5)
    result = manual_solve(_KB_P5, Atom("p", (Meta("?X"),)), _first_picker, dispatcher=d)
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert sat.get("?X") == Const(5)


# ---------------------------------------------------------------------------
# C. M2 mode, KB-only multi-goal
# ---------------------------------------------------------------------------


def test_m2_mode_kb_multi_goal_sld_state():
    """?- p(?X), q(?Y) with KB p(a). q(b). — both KB-routed, no solver calls.
    Renderer now handles multi-goal (Session 5b): returns kernel-verified proof."""
    d = _make_dispatcher(kb=_KB_PQ)
    result = manual_solve(
        _KB_PQ,
        (Atom("p", (Meta("?X"),)), Atom("q", (Meta("?Y"),))),
        _first_picker,
        dispatcher=d,
    )
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    assert sat.get("?X") == Const("a")
    assert sat.get("?Y") == Const("b")
    # No solver calls
    assert len(d.z3_bridge.calls) == 0
    assert len(d.sympy_bridge.calls) == 0


# ---------------------------------------------------------------------------
# D. M2 mode, mixed-goal query (KB + dispatcher)
# ---------------------------------------------------------------------------


def test_m2_mode_mixed_goal_sld_history():
    """?- p(?X), ?X > 0. KB: p(5). Z3 returns sat trivially (5>0 ground).

    After resolution, history has:
      [0] ClauseResolvedStep (for p(?X))
      [1] DispatcherResolvedStep (for 5 > 0)
    Renderer now handles DispatcherResolvedStep (Session 5b): returns
    kernel-verified proof with KB premise + arithEval + andI chain.
    """
    d = _make_dispatcher(
        z3_result=Z3Sat(model={}),  # ground goal → short-circuit, no Z3 call
        kb=_KB_P5,
    )
    result = manual_solve(
        _KB_P5,
        (Atom("p", (Meta("?X"),)), Atom(">", (Meta("?X"), Const(0)))),
        _first_picker,
        dispatcher=d,
    )
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    assert sat.get("?X") == Const(5)


def test_m2_mode_mixed_goal_history_types():
    """Substitution reflects both steps (KB binding + arithmetic verify).
    Renderer produces a kernel-verified proof (Session 5b)."""
    d = _make_dispatcher(kb=_KB_P5)
    result = manual_solve(
        _KB_P5,
        (Atom("p", (Meta("?X"),)), Atom(">", (Meta("?X"), Const(0)))),
        _first_picker,
        dispatcher=d,
    )
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    # ?X was bound by KB step and used by arithmetic step
    assert sat.get("?X") == Const(5)


# ---------------------------------------------------------------------------
# E. M2 mode, OutsideFragment threading
# ---------------------------------------------------------------------------


def test_m2_outside_fragment_returns_none():
    """Transcendental goal → classifier rejects → manual_solve returns None."""
    poly = Func("^", (Const(2), Var("x")))  # 2^x — transcendental
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher()
    result = manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
    assert result is None


def test_m2_outside_fragment_last_outside_fragment_set():
    """After OutsideFragment, dispatcher.last_outside_fragment is set."""
    poly = Func("^", (Const(2), Var("x")))
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher()
    manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL


# ---------------------------------------------------------------------------
# F. M2 mode, Case 2 narrowing (contested-convention witness dropped)
# ---------------------------------------------------------------------------


def test_m2_case2_narrowing_subst():
    """?- root_of(?X, x^0 - 1). SymPy returns {1, 0}.

    ?X=0 produces verify atom Equals(0^0-1, 0) → MalformedArithmetic on 0^0
    (contested) → Case 2 → dropped. Outcome narrows to UniqueSolution(?X=1).
    Renderer now handles DispatcherResolvedStep (Session 5b): returns
    kernel-verified proof with arithEval for the verify atom.
    """
    poly = Func("-", (Func("^", (Var("x"), Const(0))), Const(1)))
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(1, 0)))
    result = manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    assert sat.get("?X") == Const(1)


# ---------------------------------------------------------------------------
# G. M2 mode, MultipleSolutions + solver_picker
# ---------------------------------------------------------------------------


def test_m2_multiple_solutions_solver_picker_called():
    """SymPy returns two roots {2, 3}; solver_picker is called with the solutions."""
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    goal = Atom("root_of", (Meta("?X"), poly))

    picked: list[tuple] = []

    def capturing_picker(solutions: tuple) -> int:
        picked.append(solutions)
        return 0  # always pick first

    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2, 3)))
    result = manual_solve(
        _EMPTY_KB, goal, _first_picker, dispatcher=d, solver_picker=capturing_picker
    )
    assert result is not None
    # solver_picker was called with the two solutions
    assert len(picked) == 1
    solutions = picked[0]
    assert len(solutions) == 2


def test_m2_multiple_solutions_picker_picks_first():
    """solver_picker picks index 0 → binding is the first solution.
    Renderer now produces a kernel-verified proof (Session 5b)."""
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2, 3)))
    result = manual_solve(
        _EMPTY_KB, goal, _first_picker,
        dispatcher=d,
        solver_picker=lambda sols: 0,
    )
    assert result is not None
    sat, proof = result
    assert proof is not None
    assert isinstance(check_proof(proof), Verified)
    # First solution from SymPyFiniteRoots(roots=(2,3)) is ?X=2
    assert sat.get("?X") == Const(2)


def test_m2_multiple_solutions_no_picker_returns_none():
    """MultipleSolutions with solver_picker=None → manual_solve returns None."""
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    goal = Atom("root_of", (Meta("?X"), poly))
    d = _make_dispatcher(sympy_result=SymPyFiniteRoots(roots=(2, 3)))
    result = manual_solve(
        _EMPTY_KB, goal, _first_picker, dispatcher=d, solver_picker=None
    )
    assert result is None


# ---------------------------------------------------------------------------
# H. M2 mode, NoSolution from dispatcher
# ---------------------------------------------------------------------------


def test_m2_no_solution_returns_none():
    """Dispatcher returns NoSolution for an unsatisfiable constraint."""
    d = _make_dispatcher(z3_result=Z3Unsat())
    result = manual_solve(
        _EMPTY_KB,
        Atom(">", (Meta("?P"), Const(2))),
        _first_picker,
        dispatcher=d,
    )
    assert result is None
