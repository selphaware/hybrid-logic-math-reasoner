"""Integration tests for manual_solve in src/hlmr/solve/__init__.py."""
from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import pytest

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import CheckFailure, StructuralError, Verified
from hlmr.solve import RenderError, SLDState, manual_solve

# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------

SOCRATES = Const("socrates")
ALICE = Const("alice")
BOB = Const("bob")
CAROL = Const("carol")
RED = Const("red")
GREEN = Const("green")
BLUE = Const("blue")
ZERO = Const(0)


def _s(n: int) -> Func | Const:
    """Build s^n(0) in Peano arithmetic."""
    t: Func | Const = ZERO
    for _ in range(n):
        t = Func("s", (t,))
    return t


def _seq_picker(indices: list[int]) -> Callable[[list[Clause], SLDState], int | None]:
    """Returns a picker that consumes a fixed sequence of clause indices.

    Returns None (user abort) if the sequence is exhausted before the
    proof completes — this should not happen in a correctly-specified test.
    """
    it = iter(indices)

    def picker(cs: list[Clause], state: SLDState) -> int | None:
        return next(it, None)

    return picker


# ---------------------------------------------------------------------------
# Demo 2: syllogism
# ---------------------------------------------------------------------------
#
# KB:  human(socrates).                    (c1)
#      mortal(X) :- human(X).              (c2)
# Query: mortal(socrates).
#
# Candidate sequences:
#   goal mortal(socrates): only c2 → pick index 0
#   goal human(?X_1):      only c1 → pick index 0
# Picker: [0, 0]


def _demo2_kb() -> tuple[KnowledgeBase, Clause, Clause]:
    c1 = Clause("human_socrates", Atom("human", (SOCRATES,)))
    c2 = Clause(
        "mortal_rule",
        Atom("mortal", (Var("X"),)),
        (Atom("human", (Var("X"),)),),
    )
    return KnowledgeBase(clauses=(c1, c2)), c1, c2


def test_demo2_returns_result() -> None:
    kb, _, _ = _demo2_kb()
    query = Atom("mortal", (SOCRATES,))
    result = manual_solve(kb, query, _seq_picker([0, 0]))
    assert result is not None


def test_demo2_kernel_verified() -> None:
    kb, _, _ = _demo2_kb()
    query = Atom("mortal", (SOCRATES,))
    result = manual_solve(kb, query, _seq_picker([0, 0]))
    assert result is not None
    assert check_proof(result[1]) == Verified()


def test_demo2_final_line_matches_query() -> None:
    kb, _, _ = _demo2_kb()
    query = Atom("mortal", (SOCRATES,))
    result = manual_solve(kb, query, _seq_picker([0, 0]))
    assert result is not None
    assert result[1].lines[-1].formula == query
    assert result[1].goal == query


# ---------------------------------------------------------------------------
# Demo 1: kinship — ancestor(alice, carol) via recursive clause
# ---------------------------------------------------------------------------
#
# KB:  parent(alice, bob).                               (c1)
#      parent(bob,   carol).                             (c2)
#      ancestor(X, Y) :- parent(X, Y).                  (c3)
#      ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).  (c4)
# Query: ancestor(?A, carol).
#
# Candidate sequences:
#   goal ancestor(?A, carol):          [c3, c4] → pick c4 (index 1)
#   goal parent(?X_1, ?Z_1):           [c1, c2] → pick c1 (index 0)
#   goal ancestor(bob, carol):         [c3, c4] → pick c3 (index 0)
#   goal parent(bob, carol):           [c1, c2] → pick c2 (index 1)
# Picker: [1, 0, 0, 1]


def _demo1_kb() -> KnowledgeBase:
    c1 = Clause("parent_ab", Atom("parent", (ALICE, BOB)))
    c2 = Clause("parent_bc", Atom("parent", (BOB, CAROL)))
    c3 = Clause(
        "ancestor_base",
        Atom("ancestor", (Var("X"), Var("Y"))),
        (Atom("parent", (Var("X"), Var("Y"))),),
    )
    c4 = Clause(
        "ancestor_rec",
        Atom("ancestor", (Var("X"), Var("Y"))),
        (
            Atom("parent", (Var("X"), Var("Z"))),
            Atom("ancestor", (Var("Z"), Var("Y"))),
        ),
    )
    return KnowledgeBase(clauses=(c1, c2, c3, c4))


def test_demo1_returns_result() -> None:
    kb = _demo1_kb()
    query = Atom("ancestor", (Meta("?A"), CAROL))
    result = manual_solve(kb, query, _seq_picker([1, 0, 0, 1]))
    assert result is not None


def test_demo1_kernel_verified() -> None:
    kb = _demo1_kb()
    query = Atom("ancestor", (Meta("?A"), CAROL))
    result = manual_solve(kb, query, _seq_picker([1, 0, 0, 1]))
    assert result is not None
    assert check_proof(result[1]) == Verified()


def test_demo1_witness_binding() -> None:
    """Saturated substitution binds ?A to alice."""
    kb = _demo1_kb()
    query = Atom("ancestor", (Meta("?A"), CAROL))
    result = manual_solve(kb, query, _seq_picker([1, 0, 0, 1]))
    assert result is not None
    subst, proof = result
    assert subst.get("?A") == ALICE


def test_demo1_final_line_matches_grounded_query() -> None:
    kb = _demo1_kb()
    query = Atom("ancestor", (Meta("?A"), CAROL))
    result = manual_solve(kb, query, _seq_picker([1, 0, 0, 1]))
    assert result is not None
    expected = Atom("ancestor", (ALICE, CAROL))
    assert result[1].lines[-1].formula == expected
    assert result[1].goal == expected


# ---------------------------------------------------------------------------
# Demo 4: Peano even — even(s(s(s(s(0)))))
# ---------------------------------------------------------------------------
#
# KB:  even(0).                             (c1)
#      even(s(s(N))) :- even(N).            (c2)
# Query: even(s(s(s(s(0))))).
#
# Candidate sequences (both c1 and c2 match "even" at every step):
#   goal even(s(s(s(s(0))))): [c1, c2] → pick c2 (index 1)
#   goal even(s(s(0))):        [c1, c2] → pick c2 (index 1)
#   goal even(0):              [c1, c2] → pick c1 (index 0)
# Picker: [1, 1, 0]


def _demo4_kb() -> KnowledgeBase:
    c1 = Clause("even_zero", Atom("even", (ZERO,)))
    c2 = Clause(
        "even_step",
        Atom("even", (Func("s", (Func("s", (Var("N"),)),)),)),
        (Atom("even", (Var("N"),)),),
    )
    return KnowledgeBase(clauses=(c1, c2))


def test_demo4_kernel_verified() -> None:
    kb = _demo4_kb()
    query = Atom("even", (_s(4),))
    result = manual_solve(kb, query, _seq_picker([1, 1, 0]))
    assert result is not None
    assert check_proof(result[1]) == Verified()


def test_demo4_final_line_matches_query() -> None:
    kb = _demo4_kb()
    query = Atom("even", (_s(4),))
    result = manual_solve(kb, query, _seq_picker([1, 1, 0]))
    assert result is not None
    assert result[1].lines[-1].formula == query


# ---------------------------------------------------------------------------
# Demo 3: finite puzzle — chain(red, green, blue)
# ---------------------------------------------------------------------------
#
# KB:  left_of(red, green).                                  (c1)
#      left_of(green, blue).                                 (c2)
#      adjacent(X, Y) :- left_of(X, Y).                     (c3)
#      chain(X, Y, Z) :- adjacent(X, Y), adjacent(Y, Z).    (c4)
# Query: chain(red, green, blue).
#
# Candidate sequences:
#   goal chain(red,green,blue):    [c4]     → index 0
#   goal adjacent(red, green):     [c3]     → index 0
#   goal left_of(red, green):      [c1, c2] → pick c1 (index 0)
#   goal adjacent(green, blue):    [c3]     → index 0
#   goal left_of(green, blue):     [c1, c2] → pick c2 (index 1)
# Picker: [0, 0, 0, 0, 1]


def _demo3_kb() -> KnowledgeBase:
    c1 = Clause("lof_rg", Atom("left_of", (RED, GREEN)))
    c2 = Clause("lof_gb", Atom("left_of", (GREEN, BLUE)))
    c3 = Clause(
        "adjacent_rule",
        Atom("adjacent", (Var("X"), Var("Y"))),
        (Atom("left_of", (Var("X"), Var("Y"))),),
    )
    c4 = Clause(
        "chain_rule",
        Atom("chain", (Var("X"), Var("Y"), Var("Z"))),
        (
            Atom("adjacent", (Var("X"), Var("Y"))),
            Atom("adjacent", (Var("Y"), Var("Z"))),
        ),
    )
    return KnowledgeBase(clauses=(c1, c2, c3, c4))


def test_demo3_kernel_verified() -> None:
    kb = _demo3_kb()
    query = Atom("chain", (RED, GREEN, BLUE))
    result = manual_solve(kb, query, _seq_picker([0, 0, 0, 0, 1]))
    assert result is not None
    assert check_proof(result[1]) == Verified()


def test_demo3_final_line_matches_query() -> None:
    kb = _demo3_kb()
    query = Atom("chain", (RED, GREEN, BLUE))
    result = manual_solve(kb, query, _seq_picker([0, 0, 0, 0, 1]))
    assert result is not None
    assert result[1].lines[-1].formula == query


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_user_abort_returns_none() -> None:
    """Picker returns None (user abort) on the first candidate set."""
    kb, _, c2 = _demo2_kb()
    query = Atom("mortal", (SOCRATES,))
    picker: Callable[[list[Clause], SLDState], int | None] = lambda cs, s: None
    assert manual_solve(kb, query, picker) is None


def test_no_candidates_returns_none() -> None:
    """KB has no clause matching the query predicate."""
    kb = KnowledgeBase(clauses=())
    query = Atom("unknown_pred", (ALICE,))
    assert manual_solve(kb, query, lambda cs, s: 0) is None


def test_nonapplicable_clause_returns_none() -> None:
    """Picker chooses a clause whose head does not unify with the goal.

    In Demo 1's KB, picking c1 (parent(alice,bob)) for the final goal
    parent(bob,carol) causes unification to fail → resolve returns None
    → manual_solve returns None.
    """
    kb = _demo1_kb()
    query = Atom("ancestor", (Meta("?A"), CAROL))
    # Steps 1–3 correct; step 4 deliberately wrong: pick c1 instead of c2.
    result = manual_solve(kb, query, _seq_picker([1, 0, 0, 0]))
    assert result is None


def test_renderer_rejection_raises_render_error() -> None:
    """If check_proof rejects the rendered proof, RenderError surfaces.

    This tests the defense-in-depth path in manual_solve.
    Under normal operation the renderer produces valid proofs; this
    simulates a hypothetical renderer bug by patching check_proof.
    """
    kb, c1, _ = _demo2_kb()
    query = Atom("mortal", (SOCRATES,))
    fake_failure = CheckFailure(1, StructuralError("injected"))
    # Patch check_proof in the hlmr.solve namespace (where manual_solve
    # imported it at module load time).
    with patch("hlmr.solve.check_proof", return_value=fake_failure):
        with pytest.raises(RenderError, match="kernel"):
            manual_solve(kb, query, _seq_picker([0, 0]))
