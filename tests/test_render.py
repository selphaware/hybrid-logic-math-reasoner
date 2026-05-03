"""Tests for src/hlmr/solve/render.py.

Structure:
  1. Helper functions shared by tests.
  2. _saturate unit tests.
  3. _extract_var_map unit tests.
  4. _build_premise_formula unit tests.
  5. _build_step_tree unit tests.
  6. Per-demo end-to-end tests (all four M1 demos).
  7. Adversarial end-to-end tests.
  8. RenderError tests.
  9. Property tests (Hypothesis).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import (
    And,
    Atom,
    Const,
    Equals,
    ForAll,
    Func,
    Implies,
    Meta,
    Var,
)
from hlmr.ir.justification import Premise, RuleApp
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.solve.render import (
    RenderError,
    _build_premise_formula,
    _build_step_tree,
    _extract_var_map,
    _formula_has_meta,
    _peel_forall,
    _saturate,
    _term_has_meta,
    render,
)
from hlmr.solve.sld import FreshNameGen, SLDState, SLDStep, _vars_in_order, resolve
from hlmr.unify.substitution import Substitution, apply_to_formula, apply_to_term

# ---------------------------------------------------------------------------
# Shorthand constants used across tests
# ---------------------------------------------------------------------------

SOCRATES = Const("socrates")
ALICE = Const("alice")
BOB = Const("bob")
CAROL = Const("carol")
RED = Const("red")
GREEN = Const("green")
BLUE = Const("blue")
ZERO = Const(0)


def _s(*args: int) -> Func:
    """Build Peano successor term: _s(n) gives s^n(0)."""
    t: Func | Const = ZERO
    for _ in range(args[0] if args else 0):
        t = Func("s", (t,))
    return t  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rule-alphabet helper
# ---------------------------------------------------------------------------


def _rule_names(proof: Proof) -> set[str]:
    return {
        line.justification.rule
        for line in proof.lines
        if isinstance(line.justification, RuleApp)
    }


# ---------------------------------------------------------------------------
# §1 — _saturate
# ---------------------------------------------------------------------------


def test_saturate_empty() -> None:
    assert _saturate({}) == {}


def test_saturate_already_ground() -> None:
    s: Substitution = {"?X": ALICE, "?Y": BOB}
    assert _saturate(s) == s


def test_saturate_one_hop() -> None:
    s: Substitution = {"?A": Meta("?X"), "?X": ALICE}
    sat = _saturate(s)
    assert sat["?A"] == ALICE
    assert sat["?X"] == ALICE


def test_saturate_two_hop_chain() -> None:
    s: Substitution = {"?A": Meta("?B"), "?B": Meta("?C"), "?C": ALICE}
    sat = _saturate(s)
    assert sat["?A"] == ALICE
    assert sat["?B"] == ALICE
    assert sat["?C"] == ALICE


def test_saturate_idempotent_ground() -> None:
    s: Substitution = {"?X": ALICE, "?Y": BOB}
    assert _saturate(_saturate(s)) == _saturate(s)


def test_saturate_idempotent_chain() -> None:
    s: Substitution = {"?A": Meta("?B"), "?B": ALICE}
    sat = _saturate(s)
    assert _saturate(sat) == sat


# ---------------------------------------------------------------------------
# §2 — _extract_var_map
# ---------------------------------------------------------------------------


def test_extract_var_map_simple_atom() -> None:
    c = Clause("p", Atom("p", (Var("X"), Var("Y"))))
    renamed = Clause("p", Atom("p", (Meta("?X_1"), Meta("?Y_1"))))
    m = _extract_var_map(c, renamed)
    assert m == {"X": "?X_1", "Y": "?Y_1"}


def test_extract_var_map_shared_var() -> None:
    # mortal(X) :- human(X)  — same X in head and body
    c = Clause(
        "mortal",
        Atom("mortal", (Var("X"),)),
        (Atom("human", (Var("X"),)),),
    )
    renamed = Clause(
        "mortal",
        Atom("mortal", (Meta("?X_1"),)),
        (Atom("human", (Meta("?X_1"),)),),
    )
    m = _extract_var_map(c, renamed)
    assert m == {"X": "?X_1"}


def test_extract_var_map_nested_func() -> None:
    # even(s(s(N))) head with nested Func
    c = Clause("even_rule", Atom("even", (Func("s", (Func("s", (Var("N"),)),)),)))
    renamed = Clause(
        "even_rule",
        Atom("even", (Func("s", (Func("s", (Meta("?N_1"),)),)),)),
    )
    m = _extract_var_map(c, renamed)
    assert m == {"N": "?N_1"}


def test_extract_var_map_equals_head() -> None:
    c = Clause("eq", Equals(Var("X"), Var("Y")))
    renamed = Clause("eq", Equals(Meta("?X_1"), Meta("?Y_1")))
    m = _extract_var_map(c, renamed)
    assert m == {"X": "?X_1", "Y": "?Y_1"}


def test_extract_var_map_raises_on_mismatch() -> None:
    c = Clause("p", Atom("p", (Var("X"),)))
    bad_renamed = Clause("p", Atom("p", (Const("oops"),)))
    with pytest.raises(RenderError):
        _extract_var_map(c, bad_renamed)


# ---------------------------------------------------------------------------
# §3 — _build_premise_formula
# ---------------------------------------------------------------------------


def test_premise_ground_fact() -> None:
    c = Clause("h", Atom("human", (SOCRATES,)))
    f = _build_premise_formula(c)
    assert f == Atom("human", (SOCRATES,))


def test_premise_fact_with_one_var() -> None:
    c = Clause("pxx", Atom("parent", (Var("X"), Var("X"))))
    f = _build_premise_formula(c)
    assert f == ForAll("X", Atom("parent", (Var("X"), Var("X"))))


def test_premise_single_body_rule() -> None:
    # mortal(X) :- human(X)
    c = Clause(
        "mortal",
        Atom("mortal", (Var("X"),)),
        (Atom("human", (Var("X"),)),),
    )
    f = _build_premise_formula(c)
    assert f == ForAll(
        "X",
        Implies(Atom("human", (Var("X"),)), Atom("mortal", (Var("X"),))),
    )


def test_premise_multi_body_rule_left_assoc() -> None:
    # chain(X, Y, Z) :- adjacent(X, Y), adjacent(Y, Z)
    c = Clause(
        "chain",
        Atom("chain", (Var("X"), Var("Y"), Var("Z"))),
        (
            Atom("adjacent", (Var("X"), Var("Y"))),
            Atom("adjacent", (Var("Y"), Var("Z"))),
        ),
    )
    f = _build_premise_formula(c)
    assert f == ForAll(
        "X",
        ForAll(
            "Y",
            ForAll(
                "Z",
                Implies(
                    And(
                        Atom("adjacent", (Var("X"), Var("Y"))),
                        Atom("adjacent", (Var("Y"), Var("Z"))),
                    ),
                    Atom("chain", (Var("X"), Var("Y"), Var("Z"))),
                ),
            ),
        ),
    )


def test_premise_var_only_in_body() -> None:
    # q :- p(X)
    c = Clause("q", Atom("q", ()), (Atom("p", (Var("X"),)),))
    f = _build_premise_formula(c)
    assert f == ForAll(
        "X", Implies(Atom("p", (Var("X"),)), Atom("q", ()))
    )


# ---------------------------------------------------------------------------
# §4 — _build_step_tree
# ---------------------------------------------------------------------------


def test_step_tree_single_fact() -> None:
    # One step, fact clause (no body).
    step = SLDStep(
        goal_resolved=Atom("p", ()),
        clause_used=Clause("p", Atom("p", ())),
        clause_renamed=Clause("p", Atom("p", ())),
        unifier={},
    )
    children = _build_step_tree((step,))
    assert children == [[]]


def test_step_tree_linear_chain() -> None:
    # Demo 4 shape: root (body=1) → child (body=1) → leaf (body=0)
    c2 = Clause("c2", Atom("p", ()), (Atom("q", ()),))
    step0 = SLDStep(Atom("p", ()), c2, c2, {})
    step1 = SLDStep(Atom("q", ()), c2, c2, {})
    step2 = SLDStep(Atom("q", ()), Clause("fact", Atom("q", ())), Clause("fact", Atom("q", ())), {})
    children = _build_step_tree((step0, step1, step2))
    assert children == [[1], [2], []]


def test_step_tree_binary_root() -> None:
    # Root has 2 children; first child is a leaf; second child has 1 leaf.
    c_root = Clause("r", Atom("r", ()), (Atom("a", ()), Atom("b", ())))
    c_leaf = Clause("leaf", Atom("x", ()))
    c_single = Clause("s", Atom("b", ()), (Atom("c", ()),))
    step0 = SLDStep(Atom("r", ()), c_root, c_root, {})
    step1 = SLDStep(Atom("a", ()), c_leaf, c_leaf, {})
    step2 = SLDStep(Atom("b", ()), c_single, c_single, {})
    step3 = SLDStep(Atom("c", ()), c_leaf, c_leaf, {})
    children = _build_step_tree((step0, step1, step2, step3))
    assert children == [[1, 2], [], [3], []]


def test_step_tree_raises_on_incomplete_history() -> None:
    # Root expects 1 child but no step follows.
    c = Clause("r", Atom("r", ()), (Atom("q", ()),))
    step0 = SLDStep(Atom("r", ()), c, c, {})
    with pytest.raises(RenderError, match="unresolved"):
        _build_step_tree((step0,))


# ---------------------------------------------------------------------------
# §5 — _peel_forall
# ---------------------------------------------------------------------------


def test_peel_forall_basic() -> None:
    f = ForAll("X", Atom("p", (Var("X"),)))
    result = _peel_forall(f, ALICE)
    assert result == Atom("p", (ALICE,))


def test_peel_forall_raises_on_non_forall() -> None:
    with pytest.raises(RenderError):
        _peel_forall(Atom("p", ()), ALICE)


# ---------------------------------------------------------------------------
# §6 — Demo end-to-end tests
# ---------------------------------------------------------------------------


def _demo2_proof() -> tuple[Proof, Atom]:
    """Demo 2: syllogism. mortal(socrates)."""
    c1 = Clause("human_socrates", Atom("human", (SOCRATES,)))
    c2 = Clause(
        "mortal_rule",
        Atom("mortal", (Var("X"),)),
        (Atom("human", (Var("X"),)),),
    )
    kb = KnowledgeBase(clauses=(c1, c2))
    query = Atom("mortal", (SOCRATES,))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s1 = resolve(state, c2, gen)
    assert s1 is not None
    s2 = resolve(s1, c1, gen)
    assert s2 is not None
    return render(s2, kb, query), query


def test_demo2_line_count() -> None:
    proof, _ = _demo2_proof()
    assert len(proof.lines) == 4


def test_demo2_kernel_verified() -> None:
    proof, _ = _demo2_proof()
    assert check_proof(proof) == Verified()


def test_demo2_final_line() -> None:
    proof, query = _demo2_proof()
    assert proof.lines[-1].formula == query
    assert proof.goal == query


def test_demo2_no_meta() -> None:
    proof, _ = _demo2_proof()
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_demo2_rule_alphabet() -> None:
    proof, _ = _demo2_proof()
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


def test_demo2_premise_count() -> None:
    proof, _ = _demo2_proof()
    premise_lines = [l for l in proof.lines if isinstance(l.justification, Premise)]
    assert len(premise_lines) == 2


def _demo1_proof() -> tuple[Proof, Atom]:
    """Demo 1: kinship. ancestor(alice, carol) via recursive clause."""
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
    kb = KnowledgeBase(clauses=(c1, c2, c3, c4))
    query = Atom("ancestor", (Meta("?A"), CAROL))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c4, gen)
    assert s is not None
    s = resolve(s, c1, gen)
    assert s is not None
    s = resolve(s, c3, gen)
    assert s is not None
    s = resolve(s, c2, gen)
    assert s is not None
    return render(s, kb, query), Atom("ancestor", (ALICE, CAROL))


def test_demo1_line_count() -> None:
    proof, _ = _demo1_proof()
    assert len(proof.lines) == 12


def test_demo1_kernel_verified() -> None:
    proof, _ = _demo1_proof()
    assert check_proof(proof) == Verified()


def test_demo1_final_line() -> None:
    proof, expected = _demo1_proof()
    assert proof.lines[-1].formula == expected
    assert proof.goal == expected


def test_demo1_no_meta() -> None:
    proof, _ = _demo1_proof()
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_demo1_rule_alphabet() -> None:
    proof, _ = _demo1_proof()
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


def test_demo1_premise_count() -> None:
    proof, _ = _demo1_proof()
    premise_lines = [l for l in proof.lines if isinstance(l.justification, Premise)]
    assert len(premise_lines) == 4


def _demo4_proof() -> tuple[Proof, Atom]:
    """Demo 4: even(s(s(s(s(0)))))."""
    c1 = Clause("even_zero", Atom("even", (ZERO,)))
    c2 = Clause(
        "even_step",
        Atom("even", (Func("s", (Func("s", (Var("N"),)),)),)),
        (Atom("even", (Var("N"),)),),
    )
    kb = KnowledgeBase(clauses=(c1, c2))
    query = Atom("even", (_s(4),))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c2, gen)
    assert s is not None
    s = resolve(s, c2, gen)
    assert s is not None
    s = resolve(s, c1, gen)
    assert s is not None
    return render(s, kb, query), query


def test_demo4_line_count() -> None:
    proof, _ = _demo4_proof()
    assert len(proof.lines) == 6


def test_demo4_kernel_verified() -> None:
    proof, _ = _demo4_proof()
    assert check_proof(proof) == Verified()


def test_demo4_final_line() -> None:
    proof, expected = _demo4_proof()
    assert proof.lines[-1].formula == expected
    assert proof.goal == expected


def test_demo4_no_meta() -> None:
    proof, _ = _demo4_proof()
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_demo4_rule_alphabet() -> None:
    proof, _ = _demo4_proof()
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


def test_demo4_same_clause_twice_distinct_forallE() -> None:
    proof, _ = _demo4_proof()
    # c2 used twice → two distinct forallE "term" values at different lines
    forall_e_terms = [
        line.justification.extra["term"]
        for line in proof.lines
        if isinstance(line.justification, RuleApp)
        and line.justification.rule == "forallE"
    ]
    assert len(forall_e_terms) == 2  # one per use of c2
    assert len(set(str(t) for t in forall_e_terms)) == 2  # distinct terms


def _demo3_proof() -> tuple[Proof, Atom]:
    """Demo 3: chain(red, green, blue)."""
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
    kb = KnowledgeBase(clauses=(c1, c2, c3, c4))
    query = Atom("chain", (RED, GREEN, BLUE))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c4, gen)
    assert s is not None
    s = resolve(s, c3, gen)
    assert s is not None
    s = resolve(s, c1, gen)
    assert s is not None
    s = resolve(s, c3, gen)
    assert s is not None
    s = resolve(s, c2, gen)
    assert s is not None
    return render(s, kb, query), query


def test_demo3_line_count() -> None:
    proof, _ = _demo3_proof()
    assert len(proof.lines) == 15


def test_demo3_kernel_verified() -> None:
    proof, _ = _demo3_proof()
    assert check_proof(proof) == Verified()


def test_demo3_final_line() -> None:
    proof, expected = _demo3_proof()
    assert proof.lines[-1].formula == expected
    assert proof.goal == expected


def test_demo3_no_meta() -> None:
    proof, _ = _demo3_proof()
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_demo3_rule_alphabet() -> None:
    proof, _ = _demo3_proof()
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


# ---------------------------------------------------------------------------
# §7 — Adversarial end-to-end tests
# ---------------------------------------------------------------------------


def test_fact_with_var_parent_xx() -> None:
    """Fact with one variable: parent(X, X). forallE grounds both positions."""
    c = Clause("pxx", Atom("parent", (Var("X"), Var("X"))))
    kb = KnowledgeBase(clauses=(c,))
    query = Atom("parent", (Meta("?A"), ALICE))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c, gen)
    assert s is not None
    proof = render(s, kb, query)
    assert check_proof(proof) == Verified()
    expected = Atom("parent", (ALICE, ALICE))
    assert proof.lines[-1].formula == expected
    assert proof.goal == expected
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_var_only_in_body() -> None:
    """q :- p(X). X appears only in body."""
    c_q = Clause("q_rule", Atom("q", ()), (Atom("p", (Var("X"),)),))
    c_p = Clause("p_alice", Atom("p", (ALICE,)))
    kb = KnowledgeBase(clauses=(c_q, c_p))
    query = Atom("q", ())
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c_q, gen)
    assert s is not None
    s = resolve(s, c_p, gen)
    assert s is not None
    proof = render(s, kb, query)
    assert check_proof(proof) == Verified()
    assert proof.lines[-1].formula == Atom("q", ())
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)


def test_shared_var_in_body_r_pX_qX() -> None:
    """r(X) :- p(X), q(X). Both body atoms share the same variable."""
    c_r = Clause(
        "r_rule",
        Atom("r", (Var("X"),)),
        (Atom("p", (Var("X"),)), Atom("q", (Var("X"),))),
    )
    c_p = Clause("p_alice", Atom("p", (ALICE,)))
    c_q = Clause("q_alice", Atom("q", (ALICE,)))
    kb = KnowledgeBase(clauses=(c_r, c_p, c_q))
    query = Atom("r", (ALICE,))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c_r, gen)
    assert s is not None
    s = resolve(s, c_p, gen)
    assert s is not None
    s = resolve(s, c_q, gen)
    assert s is not None
    proof = render(s, kb, query)
    assert check_proof(proof) == Verified()
    assert proof.lines[-1].formula == Atom("r", (ALICE,))
    assert not any(_formula_has_meta(line.formula) for line in proof.lines)
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


def test_triple_recursion_even_6() -> None:
    """Same clause used three times: even(s(s(s(s(s(s(0)))))))."""
    c1 = Clause("even_zero", Atom("even", (ZERO,)))
    c2 = Clause(
        "even_step",
        Atom("even", (Func("s", (Func("s", (Var("N"),)),)),)),
        (Atom("even", (Var("N"),)),),
    )
    kb = KnowledgeBase(clauses=(c1, c2))
    query = Atom("even", (_s(6),))
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    for _ in range(3):
        state = resolve(state, c2, gen)  # type: ignore[assignment]
        assert state is not None
    state = resolve(state, c1, gen)  # type: ignore[assignment]
    assert state is not None
    proof = render(state, kb, query)
    assert check_proof(proof) == Verified()
    assert proof.lines[-1].formula == query
    # 4 unique clause uses (c2×3, c1×1) but 2 premises.
    premise_lines = [l for l in proof.lines if isinstance(l.justification, Premise)]
    assert len(premise_lines) == 2
    # 2 premises + 3 forallE + 3 impE = 8 lines.
    assert len(proof.lines) == 8


def test_equals_atom_in_clause_head() -> None:
    """Equals as a clause head (no eqRefl/eqSubst used)."""
    c = Clause("eq_zero", Equals(ZERO, ZERO))
    kb = KnowledgeBase(clauses=(c,))
    query = Equals(ZERO, ZERO)
    gen = FreshNameGen()
    state = SLDState(goals=(query,), subst={}, history=())
    s = resolve(state, c, gen)
    assert s is not None
    proof = render(s, kb, query)
    assert check_proof(proof) == Verified()
    assert proof.lines[-1].formula == Equals(ZERO, ZERO)
    # Renderer must NOT use eqRefl or eqSubst
    assert "eqRefl" not in _rule_names(proof)
    assert "eqSubst" not in _rule_names(proof)


def test_premise_correspondence() -> None:
    """Every Premise line formula corresponds to a clause in the KB."""
    proof, _ = _demo1_proof()
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
    expected_premises = {
        _build_premise_formula(c1),
        _build_premise_formula(c2),
        _build_premise_formula(c3),
        _build_premise_formula(c4),
    }
    actual_premises = {
        line.formula
        for line in proof.lines
        if isinstance(line.justification, Premise)
    }
    assert actual_premises == expected_premises


# ---------------------------------------------------------------------------
# §8 — RenderError cases
# ---------------------------------------------------------------------------


def test_render_error_nonempty_goals() -> None:
    """render must raise if state.goals is non-empty."""
    c = Clause("p", Atom("p", ()))
    kb = KnowledgeBase(clauses=(c,))
    state = SLDState(goals=(Atom("p", ()),), subst={}, history=())
    with pytest.raises(RenderError, match="goal"):
        render(state, kb, Atom("p", ()))


def test_render_error_empty_history() -> None:
    """render must raise if history is empty (goals also empty — impossible state)."""
    c = Clause("p", Atom("p", ()))
    kb = KnowledgeBase(clauses=(c,))
    state = SLDState(goals=(), subst={}, history=())
    with pytest.raises(RenderError, match="history"):
        render(state, kb, Atom("p", ()))


def test_render_error_unsaturated_meta() -> None:
    """Unsaturated substitution: ?Q -> ?X_1 but ?X_1 has no ground binding."""
    c_human = Clause("human", Atom("human", (Var("X"),)))
    c_human_renamed = Clause("human", Atom("human", (Meta("?X_1"),)))
    step = SLDStep(
        goal_resolved=Atom("human", (Meta("?Q"),)),
        clause_used=c_human,
        clause_renamed=c_human_renamed,
        unifier={"?Q": Meta("?X_1")},
    )
    # ?X_1 is not bound — will not saturate to a ground term
    state = SLDState(goals=(), subst={"?Q": Meta("?X_1")}, history=(step,))
    kb = KnowledgeBase(clauses=(c_human,))
    with pytest.raises(RenderError, match="unsaturated"):
        render(state, kb, Atom("human", (Meta("?Q"),)))


# ---------------------------------------------------------------------------
# §9 — Property tests (Hypothesis)
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.text(min_size=2, alphabet="?ABCDEFGHIJKLMNOPQRST"),
        min_size=0,
        max_size=6,
        unique=True,
    )
)
def test_saturate_idempotent_hypothesis(names: list[str]) -> None:
    """_saturate is idempotent: applying it twice gives the same result."""
    if not names:
        return
    # Build a chain: names[0] -> names[1] -> ... -> Const("a")
    s: Substitution = {}
    for i, name in enumerate(names[:-1]):
        s[name] = Meta(names[i + 1])
    s[names[-1]] = Const("a")
    sat1 = _saturate(s)
    sat2 = _saturate(sat1)
    assert sat1 == sat2


@given(st.sampled_from(["demo1", "demo2", "demo3", "demo4"]))
def test_all_demos_kernel_verified(demo: str) -> None:
    """All four demos produce kernel-verified proofs."""
    proof, _ = {
        "demo1": _demo1_proof,
        "demo2": _demo2_proof,
        "demo3": _demo3_proof,
        "demo4": _demo4_proof,
    }[demo]()
    assert check_proof(proof) == Verified()


@given(st.sampled_from(["demo1", "demo2", "demo3", "demo4"]))
def test_all_demos_no_meta(demo: str) -> None:
    """Rendered proofs contain no Meta terms."""
    proof, _ = {
        "demo1": _demo1_proof,
        "demo2": _demo2_proof,
        "demo3": _demo3_proof,
        "demo4": _demo4_proof,
    }[demo]()
    for line in proof.lines:
        assert not _formula_has_meta(line.formula), (
            f"Meta found at line {line.number}: {line.formula!r}"
        )


@given(st.sampled_from(["demo1", "demo2", "demo3", "demo4"]))
def test_all_demos_rule_alphabet(demo: str) -> None:
    """Rendered proofs use only {forallE, impE, andI} as rule names."""
    proof, _ = {
        "demo1": _demo1_proof,
        "demo2": _demo2_proof,
        "demo3": _demo3_proof,
        "demo4": _demo4_proof,
    }[demo]()
    assert _rule_names(proof) <= {"forallE", "impE", "andI"}


@given(st.sampled_from(["demo1", "demo2", "demo3", "demo4"]))
def test_all_demos_final_line_matches_goal(demo: str) -> None:
    """Final proof line equals the grounded query."""
    proof, expected = {
        "demo1": _demo1_proof,
        "demo2": _demo2_proof,
        "demo3": _demo3_proof,
        "demo4": _demo4_proof,
    }[demo]()
    assert proof.lines[-1].formula == expected
    assert proof.goal == expected


@given(st.sampled_from(["demo1", "demo2", "demo3", "demo4"]))
def test_all_demos_depth_zero(demo: str) -> None:
    """All proof lines are at depth 0 (no boxes in rendered output)."""
    proof, _ = {
        "demo1": _demo1_proof,
        "demo2": _demo2_proof,
        "demo3": _demo3_proof,
        "demo4": _demo4_proof,
    }[demo]()
    for line in proof.lines:
        assert line.box_depth == 0
