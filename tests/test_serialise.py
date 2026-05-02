"""JSON round-trip tests for all IR types (prd_milestone_0.md §6.6, §9.1)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Formula,
    Func,
    Iff,
    Implies,
    Not,
    Or,
    Var,
)
from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.ir.serialise import SCHEMA_VERSION, from_json, to_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def roundtrip(proof: Proof) -> Proof:
    return from_json(to_json(proof))


def simple_proof(*lines: ProofLine, goal: Formula | None = None) -> Proof:
    return Proof(lines=tuple(lines), goal=goal)


# ---------------------------------------------------------------------------
# Basic round-trip for every formula shape
# ---------------------------------------------------------------------------


def test_roundtrip_atom_ground() -> None:
    p = simple_proof(ProofLine(1, Atom("P"), Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_atom_with_args() -> None:
    f = Atom("parent", (Const("alice"), Var("x")))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_equals() -> None:
    f = Equals(Var("x"), Const(0))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_not() -> None:
    f = Not(Atom("P"))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_and() -> None:
    f = And(Atom("P"), Atom("Q"))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_or() -> None:
    f = Or(Atom("P"), Atom("Q"))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_implies() -> None:
    f = Implies(Atom("P"), Atom("Q"))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_iff() -> None:
    f = Iff(Atom("P"), Atom("Q"))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_bot() -> None:
    p = simple_proof(ProofLine(1, Bot(), Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_forall() -> None:
    f = ForAll("x", Atom("P", (Var("x"),)))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_exists() -> None:
    f = Exists("x", Atom("P", (Var("x"),)))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_func_term() -> None:
    f = Atom("P", (Func("f", (Var("x"), Const(1))),))
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p


# ---------------------------------------------------------------------------
# Justification round-trips
# ---------------------------------------------------------------------------


def test_roundtrip_premise() -> None:
    p = simple_proof(ProofLine(1, Atom("P"), Premise(), 0))
    assert roundtrip(p) == p


def test_roundtrip_assumption() -> None:
    p = simple_proof(
        ProofLine(1, Atom("P"), Assumption(), 1),
    )
    assert roundtrip(p) == p


def test_roundtrip_ruleapp_no_extra() -> None:
    p = simple_proof(
        ProofLine(1, Atom("P"), Premise(), 0),
        ProofLine(2, Atom("Q"), Premise(), 0),
        ProofLine(3, And(Atom("P"), Atom("Q")), RuleApp("andI", (1, 2)), 0),
    )
    assert roundtrip(p) == p


def test_roundtrip_ruleapp_with_box_refs() -> None:
    p = simple_proof(
        ProofLine(1, Atom("P"), Assumption(), 1),
        ProofLine(2, Atom("P"), RuleApp("reit", (1,)), 1),
        ProofLine(3, Implies(Atom("P"), Atom("P")), RuleApp("impI", box_refs=((1, 2),)), 0),
    )
    assert roundtrip(p) == p


def test_roundtrip_ruleapp_extra_eigenvar() -> None:
    f = ForAll("x", Atom("P", (Var("x"),)))
    p = simple_proof(
        ProofLine(1, Atom("P", (Var("a"),)), Assumption(), 1),
        ProofLine(2, f, RuleApp("forallI", box_refs=((1, 1),), extra={"eigenvar": "a"}), 0),
    )
    assert roundtrip(p) == p


def test_roundtrip_ruleapp_extra_term() -> None:
    f_all = ForAll("x", Atom("P", (Var("x"),)))
    f_inst = Atom("P", (Const(7),))
    p = simple_proof(
        ProofLine(1, f_all, Premise(), 0),
        ProofLine(2, f_inst, RuleApp("forallE", (1,), extra={"term": Const(7)}), 0),
    )
    assert roundtrip(p) == p


def test_roundtrip_ruleapp_extra_formula() -> None:
    eq = Equals(Var("x"), Const(0))
    template = Atom("P", (Var("t"),))
    px = Atom("P", (Var("x"),))
    p0 = Atom("P", (Const(0),))
    p = simple_proof(
        ProofLine(1, eq, Premise(), 0),
        ProofLine(2, px, Premise(), 0),
        ProofLine(3, p0, RuleApp("eqSubst", (1, 2), extra={"var": "t", "template": template}), 0),
    )
    assert roundtrip(p) == p


def test_roundtrip_goal_set() -> None:
    goal = Implies(Atom("P"), Atom("P"))
    p = simple_proof(
        ProofLine(1, Atom("P"), Assumption(), 1),
        ProofLine(2, Atom("P"), RuleApp("reit", (1,)), 1),
        ProofLine(3, goal, RuleApp("impI", box_refs=((1, 2),)), 0),
        goal=goal,
    )
    assert roundtrip(p) == p


# ---------------------------------------------------------------------------
# Schema version enforcement
# ---------------------------------------------------------------------------


def test_wrong_schema_version_rejected() -> None:
    import json

    good = json.loads(to_json(simple_proof(ProofLine(1, Bot(), Premise(), 0))))
    good["schema_version"] = 999
    with pytest.raises(ValueError, match="Unsupported schema version"):
        from_json(json.dumps(good))


def test_missing_schema_version_rejected() -> None:
    import json

    good = json.loads(to_json(simple_proof(ProofLine(1, Bot(), Premise(), 0))))
    del good["schema_version"]
    with pytest.raises(ValueError, match="Unsupported schema version"):
        from_json(json.dumps(good))


# ---------------------------------------------------------------------------
# Hypothesis: random formula round-trips
# ---------------------------------------------------------------------------

var_names = st.sampled_from(["x", "y", "z"])
const_vals = st.integers(min_value=0, max_value=5)


@st.composite
def terms(draw: st.DrawFn, max_depth: int = 2) -> ...:
    if max_depth == 0:
        return draw(st.one_of(var_names.map(Var), const_vals.map(Const)))
    return draw(st.one_of(
        var_names.map(Var),
        const_vals.map(Const),
        st.builds(Func, name=st.just("f"), args=st.tuples(terms(max_depth=max_depth - 1))),
    ))


@st.composite
def formulas(draw: st.DrawFn, max_depth: int = 2) -> ...:
    if max_depth == 0:
        return Atom(draw(st.sampled_from(["P", "Q"])), (draw(terms()),))
    return draw(st.one_of(
        st.builds(Atom, pred=st.sampled_from(["P", "Q"]), args=st.tuples(terms())),
        st.builds(Not, body=formulas(max_depth=max_depth - 1)),
        st.builds(And, left=formulas(max_depth=max_depth - 1), right=formulas(max_depth=max_depth - 1)),
        st.builds(ForAll, var=var_names, body=formulas(max_depth=max_depth - 1)),
        st.just(Bot()),
    ))


@given(f=formulas())
@settings(max_examples=300)
def test_formula_roundtrip(f: Formula) -> None:
    p = simple_proof(ProofLine(1, f, Premise(), 0))
    assert roundtrip(p) == p
