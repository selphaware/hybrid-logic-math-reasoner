"""Tests for Clause, KnowledgeBase, and _head_key (M1 §5.2)."""

from __future__ import annotations

from hlmr.ir.formula import Atom, Const, Equals, Var
from hlmr.ir.kb import Clause, KnowledgeBase, _head_key

# ---------------------------------------------------------------------------
# _head_key
# ---------------------------------------------------------------------------


def test_head_key_atom() -> None:
    assert _head_key(Atom("parent", (Var("X"), Var("Y")))) == "parent"


def test_head_key_atom_nullary() -> None:
    assert _head_key(Atom("human")) == "human"


def test_head_key_equals() -> None:
    assert _head_key(Equals(Var("X"), Const("alice"))) == "="


# ---------------------------------------------------------------------------
# Clause construction
# ---------------------------------------------------------------------------


def test_clause_fact_empty_body() -> None:
    c = Clause("human_1", Atom("human", (Const("socrates"),)))
    assert c.name == "human_1"
    assert c.head == Atom("human", (Const("socrates"),))
    assert c.body == ()


def test_clause_rule_single_body() -> None:
    head = Atom("mortal", (Var("X"),))
    body_lit = Atom("human", (Var("X"),))
    c = Clause("mortal_1", head, (body_lit,))
    assert c.head == head
    assert c.body == (body_lit,)


def test_clause_rule_multi_body() -> None:
    head = Atom("ancestor", (Var("X"), Var("Z")))
    b1 = Atom("parent", (Var("X"), Var("Y")))
    b2 = Atom("ancestor", (Var("Y"), Var("Z")))
    c = Clause("ancestor_2", head, (b1, b2))
    assert len(c.body) == 2
    assert c.body[0] == b1
    assert c.body[1] == b2


def test_clause_frozen() -> None:
    import dataclasses
    c = Clause("human_1", Atom("human", (Const("socrates"),)))
    assert dataclasses.is_dataclass(c)
    try:
        c.name = "other"  # type: ignore[misc]
        assert False, "expected FrozenInstanceError"
    except dataclasses.FrozenInstanceError:
        pass


def test_clause_equality_structural() -> None:
    head = Atom("human", (Const("socrates"),))
    assert Clause("human_1", head) == Clause("human_1", head)
    assert Clause("human_1", head) != Clause("human_2", head)


def test_clause_equals_head() -> None:
    # Clause whose head is an Equals literal (used in equality reasoning)
    head = Equals(Var("X"), Var("X"))
    c = Clause("eq_refl", head)
    assert c.head == head
    assert c.body == ()


# ---------------------------------------------------------------------------
# KnowledgeBase construction
# ---------------------------------------------------------------------------


def test_kb_empty() -> None:
    kb = KnowledgeBase(())
    assert kb.clauses == ()


def test_kb_multiple_clauses() -> None:
    c1 = Clause("human_1", Atom("human", (Const("socrates"),)))
    c2 = Clause("mortal_1", Atom("mortal", (Var("X"),)), (Atom("human", (Var("X"),)),))
    kb = KnowledgeBase((c1, c2))
    assert len(kb.clauses) == 2


def test_kb_frozen() -> None:
    import dataclasses
    kb = KnowledgeBase(())
    assert dataclasses.is_dataclass(kb)
    try:
        kb.clauses = ()  # type: ignore[misc]
        assert False, "expected FrozenInstanceError"
    except dataclasses.FrozenInstanceError:
        pass


# ---------------------------------------------------------------------------
# KnowledgeBase.matching — Atom goals
# ---------------------------------------------------------------------------


def test_matching_finds_matching_clauses() -> None:
    c_human = Clause("human_1", Atom("human", (Const("socrates"),)))
    c_mortal = Clause(
        "mortal_1", Atom("mortal", (Var("X"),)), (Atom("human", (Var("X"),)),)
    )
    kb = KnowledgeBase((c_human, c_mortal))
    result = kb.matching(Atom("human", (Var("?Who"),)))
    assert result == (c_human,)


def test_matching_returns_empty_when_no_match() -> None:
    c = Clause("human_1", Atom("human", (Const("socrates"),)))
    kb = KnowledgeBase((c,))
    assert kb.matching(Atom("mortal", (Var("?X"),))) == ()


def test_matching_returns_multiple_clauses_with_same_pred() -> None:
    c1 = Clause("ancestor_1", Atom("ancestor", (Var("X"), Var("Y"))),
                (Atom("parent", (Var("X"), Var("Y"))),))
    c2 = Clause(
        "ancestor_2",
        Atom("ancestor", (Var("X"), Var("Z"))),
        (Atom("parent", (Var("X"), Var("Y"))), Atom("ancestor", (Var("Y"), Var("Z")))),
    )
    c_other = Clause("human_1", Atom("human", (Const("socrates"),)))
    kb = KnowledgeBase((c1, c2, c_other))
    result = kb.matching(Atom("ancestor", (Var("?X"), Var("?Y"))))
    assert result == (c1, c2)


def test_matching_preserves_clause_order() -> None:
    clauses = tuple(
        Clause(f"p_{i}", Atom("p", (Const(i),))) for i in range(5)
    )
    kb = KnowledgeBase(clauses)
    result = kb.matching(Atom("p", (Var("?X"),)))
    assert result == clauses


# ---------------------------------------------------------------------------
# KnowledgeBase.matching — duplicate clause names accepted
# ---------------------------------------------------------------------------


def test_matching_duplicate_names_both_returned() -> None:
    # Duplicate names are allowed at the IR level; both clauses appear.
    c1 = Clause("human_clause", Atom("human", (Const("socrates"),)))
    c2 = Clause("human_clause", Atom("human", (Const("plato"),)))
    kb = KnowledgeBase((c1, c2))
    result = kb.matching(Atom("human", (Var("?X"),)))
    assert result == (c1, c2)


# ---------------------------------------------------------------------------
# KnowledgeBase.matching — Equals goals
# ---------------------------------------------------------------------------


def test_matching_equals_goal_matches_equals_head() -> None:
    eq_clause = Clause("eq_refl", Equals(Var("X"), Var("X")))
    atom_clause = Clause("human_1", Atom("human", (Const("socrates"),)))
    kb = KnowledgeBase((eq_clause, atom_clause))
    result = kb.matching(Equals(Var("?X"), Var("?X")))
    assert result == (eq_clause,)


def test_matching_equals_goal_does_not_match_atom_head() -> None:
    atom_clause = Clause("human_1", Atom("human", (Const("socrates"),)))
    kb = KnowledgeBase((atom_clause,))
    assert kb.matching(Equals(Var("?X"), Var("?Y"))) == ()


def test_matching_atom_goal_does_not_match_equals_head() -> None:
    eq_clause = Clause("eq_refl", Equals(Var("X"), Var("X")))
    kb = KnowledgeBase((eq_clause,))
    assert kb.matching(Atom("human", (Var("?X"),))) == ()
