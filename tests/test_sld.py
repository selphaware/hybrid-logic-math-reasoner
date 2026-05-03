"""Tests for hlmr.solve.sld (M1 §8.1).

Coverage targets: ≥95% on solve/sld.py.
"""

from __future__ import annotations

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.unify.substitution import Substitution, apply_to_term
from hlmr.solve.sld import (
    FreshNameGen,
    SLDState,
    SLDStep,
    _rename_clause,
    _vars_in_order,
    candidates,
    resolve,
)


# ---------------------------------------------------------------------------
# Test helper — fully resolve a substitution (same as in test_unifier.py)
# ---------------------------------------------------------------------------


def _saturate(s: Substitution, max_iter: int = 30) -> Substitution:
    for _ in range(max_iter):
        s_new = {k: apply_to_term(s, v) for k, v in s.items()}
        if s_new == s:
            return s
        s = s_new
    return s  # pragma: no cover


# ---------------------------------------------------------------------------
# Common fixtures (plain variables, not pytest fixtures)
# ---------------------------------------------------------------------------

P = Atom("P")
Q = Atom("Q")

mortal_rule = Clause(
    "mortal_rule",
    Atom("mortal", (Var("X"),)),
    (Atom("human", (Var("X"),)),),
)
human_fact = Clause("human_fact", Atom("human", (Const("socrates"),)))

parent_ab = Clause("parent_ab", Atom("parent", (Const("alice"), Const("bob"))))
parent_bc = Clause("parent_bc", Atom("parent", (Const("bob"), Const("charlie"))))

gp_rule = Clause(
    "gp_rule",
    Atom("gp", (Var("X"), Var("Z"))),
    (
        Atom("parent", (Var("X"), Var("Y"))),
        Atom("parent", (Var("Y"), Var("Z"))),
    ),
)


# ---------------------------------------------------------------------------
# FreshNameGen
# ---------------------------------------------------------------------------


def test_fresh_first_name_is_one() -> None:
    gen = FreshNameGen()
    assert gen.fresh("X") == "X_1"


def test_fresh_successive_are_distinct() -> None:
    gen = FreshNameGen()
    names = [gen.fresh("X") for _ in range(5)]
    assert len(set(names)) == 5


def test_fresh_successive_increment() -> None:
    gen = FreshNameGen()
    assert gen.fresh("X") == "X_1"
    assert gen.fresh("X") == "X_2"
    assert gen.fresh("Y") == "Y_3"


def test_fresh_two_instances_are_independent() -> None:
    gen1 = FreshNameGen()
    gen2 = FreshNameGen()
    assert gen1.fresh("X") == gen2.fresh("X") == "X_1"
    assert gen1.fresh("X") == "X_2"
    assert gen2.fresh("X") == "X_2"  # gen2's own counter, not shared


# ---------------------------------------------------------------------------
# _vars_in_order
# ---------------------------------------------------------------------------


def test_vars_in_order_head_only() -> None:
    clause = Clause("c", Atom("p", (Var("X"), Var("Y"))))
    assert _vars_in_order(clause) == ["X", "Y"]


def test_vars_in_order_deduplicates() -> None:
    clause = Clause("c", Atom("p", (Var("X"), Var("X"))))
    assert _vars_in_order(clause) == ["X"]


def test_vars_in_order_head_before_body() -> None:
    # X appears in head first, Z appears in body only
    clause = Clause(
        "c",
        Atom("p", (Var("X"), Var("Y"))),
        (Atom("q", (Var("Y"), Var("Z"))),),
    )
    assert _vars_in_order(clause) == ["X", "Y", "Z"]


def test_vars_in_order_no_vars() -> None:
    clause = Clause("c", Atom("p", (Const("a"),)))
    assert _vars_in_order(clause) == []


# ---------------------------------------------------------------------------
# _rename_clause
# ---------------------------------------------------------------------------


def test_rename_var_becomes_meta() -> None:
    clause = Clause("c", Atom("mortal", (Var("X"),)))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("mortal", (Meta("?X_1"),))


def test_rename_same_var_same_meta() -> None:
    # Var("X") appears twice — must get the same Meta name
    clause = Clause("c", Atom("parent", (Var("X"), Var("X"))))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("parent", (Meta("?X_1"), Meta("?X_1")))


def test_rename_different_vars_get_different_metas() -> None:
    clause = Clause("c", Atom("parent", (Var("X"), Var("Y"))))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("parent", (Meta("?X_1"), Meta("?Y_2")))


def test_rename_var_in_head_and_body_same_meta() -> None:
    # Var("X") in head and body — same Meta
    gen = FreshNameGen()
    renamed = _rename_clause(mortal_rule, gen)
    assert renamed.head == Atom("mortal", (Meta("?X_1"),))
    assert renamed.body == (Atom("human", (Meta("?X_1"),)),)


def test_rename_empty_body() -> None:
    clause = Clause("fact", Atom("human", (Var("X"),)))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("human", (Meta("?X_1"),))
    assert renamed.body == ()


def test_rename_all_consts_returns_same_object() -> None:
    # No Vars — same object returned
    gen = FreshNameGen()
    renamed = _rename_clause(human_fact, gen)
    assert renamed is human_fact


def test_rename_clause_name_preserved() -> None:
    gen = FreshNameGen()
    renamed = _rename_clause(mortal_rule, gen)
    assert renamed.name == mortal_rule.name


def test_rename_var_inside_func() -> None:
    # Var nested inside Func arg
    clause = Clause("c", Atom("p", (Func("f", (Var("X"),)),)))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("p", (Func("f", (Meta("?X_1"),)),))


def test_rename_equals_head() -> None:
    # Clause with Equals as head
    clause = Clause("eq", Equals(Var("X"), Var("Y")))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Equals(Meta("?X_1"), Meta("?Y_2"))


def test_rename_mixed_vars_and_consts() -> None:
    # Atom with both Var and Const args
    clause = Clause("c", Atom("p", (Var("X"), Const("a"))))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("p", (Meta("?X_1"), Const("a")))


def test_rename_func_with_const_args_unchanged_object() -> None:
    # Func("f", Const("a")) has no Vars; when mixed with a Var in the same atom,
    # _rename_term hits the `new_args == args` branch and returns the same Func.
    f_const = Func("f", (Const("a"),))
    clause = Clause("c", Atom("p", (Var("X"), f_const)))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.head == Atom("p", (Meta("?X_1"), Func("f", (Const("a"),))))
    assert renamed.head.args[1] is f_const  # same object — optimization branch hit


def test_rename_equals_body_with_consts_unchanged_object() -> None:
    # Equals(Const, Const) in body; head has a Var so we don't early-return.
    # _rename_atom hits `new_lhs is lhs and new_rhs is rhs` → returns same Equals.
    eq_body = Equals(Const("a"), Const("b"))
    clause = Clause("c", Atom("p", (Var("X"),)), (eq_body,))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.body[0] is eq_body


def test_rename_body_atom_without_vars_is_same_object() -> None:
    # Head has a Var; a body atom has only Const — body atom returned unchanged
    body_const = Atom("q", (Const("a"),))
    clause = Clause("c", Atom("p", (Var("X"),)), (body_const,))
    gen = FreshNameGen()
    renamed = _rename_clause(clause, gen)
    assert renamed.body[0] is body_const


def test_rename_multi_body_all_renamed() -> None:
    gen = FreshNameGen()
    renamed = _rename_clause(gp_rule, gen)
    # vars_in_order for gp_rule: head=gp(X,Z) → [X,Z]; body: parent(X,Y) → Y new; parent(Y,Z) → both seen
    # → [X, Z, Y] → ?X_1, ?Z_2, ?Y_3
    assert renamed.head == Atom("gp", (Meta("?X_1"), Meta("?Z_2")))
    assert renamed.body == (
        Atom("parent", (Meta("?X_1"), Meta("?Y_3"))),
        Atom("parent", (Meta("?Y_3"), Meta("?Z_2"))),
    )


# ---------------------------------------------------------------------------
# Renaming-apart: same clause used twice → disjoint Meta names
# ---------------------------------------------------------------------------


def test_rename_apart_same_clause_two_uses() -> None:
    gen = FreshNameGen()
    r1 = _rename_clause(mortal_rule, gen)   # X → ?X_1
    r2 = _rename_clause(mortal_rule, gen)   # X → ?X_2 (counter continues)
    assert r1.head == Atom("mortal", (Meta("?X_1"),))
    assert r2.head == Atom("mortal", (Meta("?X_2"),))
    # Meta names are disjoint
    metas1 = {a.name for a in r1.head.args if isinstance(a, Meta)}
    metas2 = {a.name for a in r2.head.args if isinstance(a, Meta)}
    assert metas1.isdisjoint(metas2)


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------


def test_candidates_empty_goals_returns_empty() -> None:
    kb = KnowledgeBase((human_fact,))
    state = SLDState(goals=(), subst={}, history=())
    assert candidates(state, kb) == []


def test_candidates_returns_matching_clauses() -> None:
    kb = KnowledgeBase((mortal_rule, human_fact))
    state = SLDState(goals=(Atom("human", (Meta("?X"),)),), subst={}, history=())
    result = candidates(state, kb)
    assert result == [human_fact]


def test_candidates_preserves_kb_order() -> None:
    c1 = Clause("h1", Atom("human", (Const("alice"),)))
    c2 = Clause("h2", Atom("human", (Const("bob"),)))
    kb = KnowledgeBase((c1, c2))
    state = SLDState(goals=(Atom("human", (Meta("?X"),)),), subst={}, history=())
    assert candidates(state, kb) == [c1, c2]


# ---------------------------------------------------------------------------
# resolve — basic cases
# ---------------------------------------------------------------------------


def test_resolve_empty_goals_returns_none() -> None:
    gen = FreshNameGen()
    state = SLDState(goals=(), subst={}, history=())
    assert resolve(state, human_fact, gen) is None


def test_resolve_failed_unification_returns_none() -> None:
    gen = FreshNameGen()
    state = SLDState(
        goals=(Atom("mortal", (Meta("?X"),)),),
        subst={},
        history=(),
    )
    # human_fact head is human(socrates) — doesn't match mortal(?)
    assert resolve(state, human_fact, gen) is None


def test_resolve_against_fact_goals_decrease() -> None:
    gen = FreshNameGen()
    state = SLDState(
        goals=(Atom("human", (Meta("?X"),)),),
        subst={},
        history=(),
    )
    s1 = resolve(state, human_fact, gen)
    assert s1 is not None
    assert s1.goals == ()
    assert len(s1.history) == 1
    assert s1.subst == {"?X": Const("socrates")}


def test_resolve_against_rule_goals_replaced_with_body() -> None:
    # Resolving mortal(?X) against mortal_rule puts human(?X_1) as new goal
    gen = FreshNameGen()
    state = SLDState(
        goals=(Atom("mortal", (Meta("?X"),)),),
        subst={},
        history=(),
    )
    s1 = resolve(state, mortal_rule, gen)
    assert s1 is not None
    assert len(s1.goals) == 1
    assert s1.goals[0] == Atom("human", (Meta("?X_1"),))


def test_resolve_left_to_right_goal_order() -> None:
    # Goals (g1, g2, g3); clause body (b1, b2) → new goals (b1, b2, g2, g3)
    g1 = Atom("human", (Meta("?X"),))
    g2 = Atom("mortal", (Meta("?Y"),))
    g3 = Atom("P")
    b1 = Atom("q", (Const("a"),))
    b2 = Atom("r", (Const("b"),))
    clause = Clause("c", g1, (b1, b2))  # head matches g1 exactly (ground)
    gen = FreshNameGen()
    state = SLDState(goals=(g1, g2, g3), subst={}, history=())
    s1 = resolve(state, clause, gen)
    assert s1 is not None
    assert s1.goals == (b1, b2, g2, g3)


def test_resolve_threads_substitution() -> None:
    # state.subst already has ?Y → Const("bob"); resolving adds ?X → Const("alice")
    gen = FreshNameGen()
    state = SLDState(
        goals=(Atom("parent", (Meta("?X"), Const("bob"))),),
        subst={"?Y": Const("bob")},
        history=(),
    )
    # Fact: parent(alice, bob)
    clause = Clause("f", Atom("parent", (Const("alice"), Const("bob"))))
    s1 = resolve(state, clause, gen)
    assert s1 is not None
    assert s1.subst["?Y"] == Const("bob")   # preserved from prior state
    assert s1.subst["?X"] == Const("alice")  # new binding


def test_resolve_records_correct_step_fields() -> None:
    gen = FreshNameGen()
    state = SLDState(
        goals=(Atom("human", (Meta("?X"),)),),
        subst={},
        history=(),
    )
    s1 = resolve(state, human_fact, gen)
    assert s1 is not None
    step = s1.history[0]
    assert step.clause_used is human_fact
    assert step.goal_resolved == Atom("human", (Meta("?X"),))
    assert step.unifier == {"?X": Const("socrates")}


# ---------------------------------------------------------------------------
# resolve — multi-step integration traces
# ---------------------------------------------------------------------------


def test_resolve_mortal_socrates_trace() -> None:
    """mortal(?Who) resolves in two steps: mortal_rule → human_fact."""
    gen = FreshNameGen()
    who = Meta("?Who")
    s0 = SLDState(
        goals=(Atom("mortal", (who,)),),
        subst={},
        history=(),
    )

    # Step 1: resolve mortal(?Who) against mortal_rule
    # Renamed: mortal(?X_1) :- human(?X_1)
    s1 = resolve(s0, mortal_rule, gen)
    assert s1 is not None
    assert s1.goals == (Atom("human", (Meta("?X_1"),)),)
    assert s1.subst == {"?Who": Meta("?X_1")}

    # Step 2: resolve human(?X_1) against human_fact (no vars, unchanged)
    s2 = resolve(s1, human_fact, gen)
    assert s2 is not None
    assert s2.goals == ()
    assert len(s2.history) == 2

    # ?Who → socrates after chain saturation
    sat = _saturate(s2.subst)
    assert apply_to_term(sat, Meta("?Who")) == Const("socrates")


def test_resolve_gp_renaming_apart_prevents_capture() -> None:
    """grandparent(alice, charlie) via gp_rule + parent facts.

    Demonstrates that variable renaming produces unique Metas (?X_1,
    ?Z_2, ?Y_3) that don't shadow the query or each other.
    """
    gen = FreshNameGen()
    kb = KnowledgeBase((gp_rule, parent_ab, parent_bc))

    # Query: gp(alice, charlie) — ground, no Metas needed
    s0 = SLDState(
        goals=(Atom("gp", (Const("alice"), Const("charlie"))),),
        subst={},
        history=(),
    )

    # Step 1: resolve gp(alice, charlie) against gp_rule
    # Renamed (vars_in_order [X, Z, Y]): gp(?X_1, ?Z_2) :- parent(?X_1, ?Y_3), parent(?Y_3, ?Z_2)
    s1 = resolve(s0, gp_rule, gen)
    assert s1 is not None
    assert len(s1.goals) == 2
    assert s1.goals[0] == Atom("parent", (Meta("?X_1"), Meta("?Y_3")))
    assert s1.goals[1] == Atom("parent", (Meta("?Y_3"), Meta("?Z_2")))
    assert s1.subst["?X_1"] == Const("alice")
    assert s1.subst["?Z_2"] == Const("charlie")

    # Step 2: resolve parent(?X_1, ?Y_3) against parent_ab (alice, bob)
    s2 = resolve(s1, parent_ab, gen)
    assert s2 is not None
    assert len(s2.goals) == 1
    assert s2.subst["?Y_3"] == Const("bob")

    # Step 3: resolve parent(?Y_3, ?Z_2) against parent_bc (bob, charlie)
    s3 = resolve(s2, parent_bc, gen)
    assert s3 is not None
    assert s3.goals == ()

    # Final substitution is ground — already resolved without needing saturation
    sat = _saturate(s3.subst)
    assert sat.get("?X_1") == Const("alice")
    assert sat.get("?Y_3") == Const("bob")
    assert sat.get("?Z_2") == Const("charlie")
