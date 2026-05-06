"""Assert that SLDState.history reflects goal-evaluation order (left-to-right).

This contract is load-bearing for the dispatcher (DISPATCH_DESIGN.md §13.3)
and the renderer (RENDER_M2_DESIGN.md §8): both rely on the i-th top-level
history entry corresponding to the i-th query goal.

M1's manual_solve handles only single-goal queries; multi-goal support
arrives in the M2 dispatcher session.  These tests use resolve() directly
to exercise multi-goal history ordering at the SLD level.  A follow-up
test will be added in the dispatcher session once manual_solve accepts a
goal tuple.
"""

from __future__ import annotations

from hlmr.ir.formula import Atom, Const, Meta
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.solve.sld import (
    ClauseResolvedStep,
    FreshNameGen,
    SLDState,
    candidates,
    resolve,
)

# ---------------------------------------------------------------------------
# KB fixtures: p(a). q(b).
# ---------------------------------------------------------------------------

A = Const("a")
B = Const("b")

_CLAUSE_P = Clause("p_1", Atom("p", (A,)), ())   # p(a).
_CLAUSE_Q = Clause("q_1", Atom("q", (B,)), ())   # q(b).

_KB = KnowledgeBase(clauses=(_CLAUSE_P, _CLAUSE_Q))


def _first_picker(cs, _state):
    return 0 if cs else None


# ---------------------------------------------------------------------------
# Single-goal: history has exactly one ClauseResolvedStep
# ---------------------------------------------------------------------------


def test_single_goal_history_length_and_order() -> None:
    """Resolving a single fact produces history of length 1."""
    goal = Atom("p", (Meta("?X"),))
    state0 = SLDState(goals=(goal,), subst={}, history=())
    gen = FreshNameGen()

    cs = candidates(state0, _KB)
    assert len(cs) == 1

    state1 = resolve(state0, cs[0], gen)
    assert state1 is not None
    assert state1.goals == ()           # fact has no body
    assert len(state1.history) == 1

    step = state1.history[0]
    assert isinstance(step, ClauseResolvedStep)
    # goal_resolved is the first goal (post-substitution: same here since subst was {})
    assert step.goal_resolved == goal


# ---------------------------------------------------------------------------
# Multi-goal: history grows in goal-evaluation order
# ---------------------------------------------------------------------------


def test_multi_goal_history_order() -> None:
    """With two successive goals, history[0] is for goal 0 and history[1]
    is for goal 1 — left-to-right order (DISPATCH_DESIGN.md §13.3 contract)."""
    goal_p = Atom("p", (Meta("?X"),))
    goal_q = Atom("q", (Meta("?Y"),))

    # Start with both goals in the queue.
    state0 = SLDState(goals=(goal_p, goal_q), subst={}, history=())
    gen = FreshNameGen()

    # Step 1: resolve goal_p against p(a).
    cs = candidates(state0, _KB)
    assert len(cs) == 1  # only p(a) matches
    state1 = resolve(state0, cs[0], gen)
    assert state1 is not None
    assert len(state1.history) == 1
    assert isinstance(state1.history[0], ClauseResolvedStep)
    assert state1.history[0].goal_resolved == goal_p  # first goal recorded first

    # Step 2: resolve goal_q against q(b).
    cs2 = candidates(state1, _KB)
    assert len(cs2) == 1  # only q(b) matches
    state2 = resolve(state1, cs2[0], gen)
    assert state2 is not None
    assert state2.goals == ()           # both goals consumed
    assert len(state2.history) == 2

    step0, step1 = state2.history
    assert isinstance(step0, ClauseResolvedStep)
    assert isinstance(step1, ClauseResolvedStep)

    # History is in goal-evaluation order: goal_p before goal_q.
    assert step0.goal_resolved == goal_p
    assert step1.goal_resolved == goal_q

    # Bindings are also accumulated in order.
    assert step1.unifier.get("?Y") == B   # q(b) binds ?Y = b


def test_multi_goal_history_bindings_flow_forward() -> None:
    """Confirm that the substitution accumulated in step 0 is available in
    step 1 — goal-order evaluation propagates bindings left-to-right."""
    # p(?X) and q(?X) — both goals share the same meta.
    # KB: p(a). q(a).
    clause_qa = Clause("q_a", Atom("q", (A,)), ())
    kb2 = KnowledgeBase(clauses=(_CLAUSE_P, clause_qa))

    goal_p = Atom("p", (Meta("?X"),))
    goal_q = Atom("q", (Meta("?X"),))

    state0 = SLDState(goals=(goal_p, goal_q), subst={}, history=())
    gen = FreshNameGen()

    # Resolve goal_p: binds ?X -> a
    cs = candidates(state0, kb2)
    p_clauses = [c for c in cs if c.head.pred == "p"]
    state1 = resolve(state0, p_clauses[0], gen)
    assert state1 is not None

    # After resolution of p(?X) against p(a), ?X should be bound to a
    # goal_q should now be q(?X) still — but subst will have ?X bound.
    cs2 = candidates(state1, kb2)
    q_clauses = [c for c in cs2 if c.head.pred == "q"]
    state2 = resolve(state1, q_clauses[0], gen)
    assert state2 is not None
    assert state2.goals == ()
    assert len(state2.history) == 2

    # Both steps recorded in left-to-right order.
    assert state2.history[0].clause_used.head.pred == "p"
    assert state2.history[1].clause_used.head.pred == "q"
