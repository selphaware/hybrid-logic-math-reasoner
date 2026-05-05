"""Hypothesis property test for the SLD renderer.

For each generated (KB, goal) pair, run manual_solve with a bounded
first-candidate picker. If solving succeeds:
  - the rendered proof must pass check_proof, and
  - the final line must equal the instantiated query goal.

This is a one-sided test: if solving fails (no match, occurs check,
step limit exceeded), the case passes vacuously.

If this test finds a RenderError or a kernel rejection, that is a
renderer bug. Stop and report to the user — do NOT patch silently.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import Atom, Const, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified
from hlmr.parse.parser import parse_query
from hlmr.solve import RenderError, SLDState, manual_solve

# ---------------------------------------------------------------------------
# Small vocabularies — keep the search space manageable
# ---------------------------------------------------------------------------

_PREDS = ["p", "q", "r"]
_FUNC_NAME = "f"
_CONSTS = ["a", "b", "c"]
_VARS = ["X", "Y"]
_METAS = ["?A", "?B"]
_MAX_STEPS = 20  # prevents infinite loops on recursive KBs


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _clause_term_st() -> st.SearchStrategy:
    """Term for use inside a clause: Const or Var (no Meta), with Func nesting."""
    leaves = st.one_of(
        st.sampled_from([Const(v) for v in _CONSTS]),
        st.sampled_from([Var(n) for n in _VARS]),
    )
    return st.recursive(
        leaves,
        lambda children: st.builds(
            lambda args: Func(_FUNC_NAME, tuple(args)),
            st.lists(children, min_size=1, max_size=1),
        ),
        max_leaves=6,
    )


def _query_term_st() -> st.SearchStrategy:
    """Term for use inside a query goal: Const or Meta (no Var), with Func nesting."""
    leaves = st.one_of(
        st.sampled_from([Const(v) for v in _CONSTS]),
        st.sampled_from([Meta(n) for n in _METAS]),
    )
    return st.recursive(
        leaves,
        lambda children: st.builds(
            lambda args: Func(_FUNC_NAME, tuple(args)),
            st.lists(children, min_size=1, max_size=1),
        ),
        max_leaves=6,
    )


def _atom_st(term_st: st.SearchStrategy) -> st.SearchStrategy:
    return st.builds(
        lambda pred, args: Atom(pred, tuple(args)),
        st.sampled_from(_PREDS),
        st.one_of(
            st.just([]),
            st.lists(term_st, min_size=1, max_size=1),
            st.lists(term_st, min_size=2, max_size=2),
        ),
    )


def _clause_st() -> st.SearchStrategy:
    head = _atom_st(_clause_term_st())
    body = st.lists(_atom_st(_clause_term_st()), min_size=0, max_size=3)
    counter = {"n": 0}

    def make_clause(h: Atom, b: list) -> Clause:
        counter["n"] += 1
        return Clause(f"{h.pred}_{counter['n']}", h, tuple(b))

    return st.builds(make_clause, head, body)


def _kb_st() -> st.SearchStrategy:
    return st.lists(_clause_st(), min_size=1, max_size=5).map(
        lambda cs: KnowledgeBase(tuple(cs))
    )


@st.composite
def _kb_and_goal_st(draw: st.DrawFn) -> tuple[KnowledgeBase, Atom]:
    """Draw a KB, then build a goal whose predicate appears in the KB."""
    kb = draw(_kb_st())
    # Collect predicates present in the KB
    preds = [c.head.pred for c in kb.clauses if isinstance(c.head, Atom)]
    pred = draw(st.sampled_from(preds)) if preds else draw(st.sampled_from(_PREDS))
    # Match the arity of the first clause with this predicate (if any)
    arity = next(
        (len(c.head.args) for c in kb.clauses
         if isinstance(c.head, Atom) and c.head.pred == pred),
        draw(st.integers(min_value=0, max_value=2)),
    )
    args = tuple(draw(_query_term_st()) for _ in range(arity))
    return kb, Atom(pred, args)


# ---------------------------------------------------------------------------
# Bounded picker: always picks first candidate; aborts after max_steps
# ---------------------------------------------------------------------------


def _bounded_first_picker(
    max_steps: int = _MAX_STEPS,
) -> Callable[[list[Clause], SLDState], int | None]:
    steps = {"n": 0}

    def pick(cs: list[Clause], state: SLDState) -> int | None:
        if steps["n"] >= max_steps:
            return None
        steps["n"] += 1
        return 0

    return pick


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(_kb_and_goal_st())
@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
def test_renderer_soundness(kb_and_goal: tuple[KnowledgeBase, Atom]) -> None:
    """If manual_solve succeeds, the rendered proof must be kernel-valid and
    the final line must equal the instantiated query goal."""
    kb, goal = kb_and_goal

    result = manual_solve(kb, goal, _bounded_first_picker())
    if result is None:
        return  # vacuous pass — no clause matched / picker exhausted

    _sat_subst, proof = result
    if proof is None:
        return  # vacuous pass — underdetermined (universal-fact pattern)

    kernel_result = check_proof(proof)
    assert isinstance(kernel_result, Verified), (
        f"Kernel rejected rendered proof: {kernel_result!r}\n"
        f"goal={goal!r}\n"
        f"KB clauses={[str(c) for c in kb.clauses]}"
    )

    assert proof.lines[-1].formula == proof.goal, (
        f"Final line does not match instantiated query goal\n"
        f"  final line: {proof.lines[-1].formula!r}\n"
        f"  proof.goal: {proof.goal!r}"
    )
