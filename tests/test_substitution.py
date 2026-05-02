"""Tests for free_vars, subst, and capture-avoidance (prd_milestone_0.md §6.3)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import (
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Func,
    Implies,
    Not,
    Var,
    And,
    Or,
    Iff,
    free_vars,
    free_vars_term,
    subst,
    subst_term,
)

# ---------------------------------------------------------------------------
# free_vars_term
# ---------------------------------------------------------------------------


def test_free_vars_var() -> None:
    assert free_vars_term(Var("x")) == frozenset({"x"})


def test_free_vars_const() -> None:
    assert free_vars_term(Const(7)) == frozenset()


def test_free_vars_func() -> None:
    assert free_vars_term(Func("f", (Var("x"), Var("y")))) == frozenset({"x", "y"})


def test_free_vars_func_nested() -> None:
    inner = Func("g", (Var("z"),))
    outer = Func("f", (inner,))
    assert free_vars_term(outer) == frozenset({"z"})


# ---------------------------------------------------------------------------
# free_vars (formula)
# ---------------------------------------------------------------------------


def test_free_vars_atom_ground() -> None:
    assert free_vars(Atom("P", (Const("a"),))) == frozenset()


def test_free_vars_atom_with_var() -> None:
    assert free_vars(Atom("P", (Var("x"),))) == frozenset({"x"})


def test_free_vars_not() -> None:
    assert free_vars(Not(Atom("P", (Var("x"),)))) == frozenset({"x"})


def test_free_vars_and() -> None:
    f = And(Atom("P", (Var("x"),)), Atom("Q", (Var("y"),)))
    assert free_vars(f) == frozenset({"x", "y"})


def test_free_vars_bot() -> None:
    assert free_vars(Bot()) == frozenset()


def test_free_vars_forall_binds() -> None:
    # forall x. P(x) — x is bound
    f = ForAll("x", Atom("P", (Var("x"),)))
    assert free_vars(f) == frozenset()


def test_free_vars_forall_partial() -> None:
    # forall x. P(x, y) — x bound, y free
    f = ForAll("x", Atom("P", (Var("x"), Var("y"))))
    assert free_vars(f) == frozenset({"y"})


def test_free_vars_exists_binds() -> None:
    f = Exists("x", Atom("P", (Var("x"),)))
    assert free_vars(f) == frozenset()


def test_free_vars_equals() -> None:
    assert free_vars(Equals(Var("x"), Const(0))) == frozenset({"x"})


# ---------------------------------------------------------------------------
# subst_term
# ---------------------------------------------------------------------------


def test_subst_term_var_match() -> None:
    assert subst_term(Var("x"), "x", Const(7)) == Const(7)


def test_subst_term_var_no_match() -> None:
    assert subst_term(Var("y"), "x", Const(7)) == Var("y")


def test_subst_term_const() -> None:
    assert subst_term(Const(5), "x", Const(7)) == Const(5)


def test_subst_term_func() -> None:
    t = Func("f", (Var("x"), Var("y")))
    result = subst_term(t, "x", Const(7))
    assert result == Func("f", (Const(7), Var("y")))


# ---------------------------------------------------------------------------
# subst (formula) — basic cases from §6.3
# ---------------------------------------------------------------------------


def test_subst_atom() -> None:
    # subst(P(x), "x", Const(7)) == P(Const(7))
    f = Atom("P", (Var("x"),))
    assert subst(f, "x", Const(7)) == Atom("P", (Const(7),))


def test_subst_bound_var_shielded() -> None:
    # subst(forall x. P(x), "x", t) == forall x. P(x)
    f = ForAll("x", Atom("P", (Var("x"),)))
    result = subst(f, "x", Const(99))
    assert result == f


def test_subst_forall_no_capture_needed() -> None:
    # subst(forall z. P(x, z), "x", Const(1)) — safe, no rename needed
    f = ForAll("z", Atom("P", (Var("x"), Var("z"))))
    result = subst(f, "x", Const(1))
    assert result == ForAll("z", Atom("P", (Const(1), Var("z"))))


def test_subst_capture_avoidance() -> None:
    # subst(forall y. P(x, y), "x", Var("y"))
    # Naive sub would give forall y. P(y, y) — WRONG (capture!)
    # Correct: bound y is renamed to avoid capturing the free y in replacement
    f = ForAll("y", Atom("P", (Var("x"), Var("y"))))
    result = subst(f, "x", Var("y"))
    # The bound variable must have been renamed
    assert isinstance(result, ForAll)
    assert result.var != "y", "bound variable should have been renamed to avoid capture"
    # The free occurrence of y should be present in the body
    assert free_vars(result) == frozenset({"y"})
    # The renamed var should not clash with y
    body_fvs = free_vars(result.body)
    assert "y" in body_fvs


def test_subst_exists_capture_avoidance() -> None:
    # Same as above but with Exists
    f = Exists("y", Atom("Q", (Var("x"), Var("y"))))
    result = subst(f, "x", Var("y"))
    assert isinstance(result, Exists)
    assert result.var != "y"
    assert free_vars(result) == frozenset({"y"})


def test_subst_not() -> None:
    f = Not(Atom("P", (Var("x"),)))
    assert subst(f, "x", Const(3)) == Not(Atom("P", (Const(3),)))


def test_subst_implies() -> None:
    f = Implies(Atom("P", (Var("x"),)), Atom("Q", (Var("x"),)))
    assert subst(f, "x", Const(0)) == Implies(
        Atom("P", (Const(0),)), Atom("Q", (Const(0),))
    )


def test_subst_bot_unchanged() -> None:
    assert subst(Bot(), "x", Const(1)) == Bot()


def test_subst_equals() -> None:
    f = Equals(Var("x"), Const(0))
    assert subst(f, "x", Const(5)) == Equals(Const(5), Const(0))


def test_subst_idempotent_when_var_not_free() -> None:
    # subst is identity when var not free
    f = ForAll("x", Atom("P", (Var("x"),)))
    result = subst(f, "x", Const(99))
    assert result == f


def test_subst_or() -> None:
    f = Or(Atom("P", (Var("x"),)), Atom("Q", (Var("x"),)))
    assert subst(f, "x", Const(1)) == Or(Atom("P", (Const(1),)), Atom("Q", (Const(1),)))


def test_subst_iff() -> None:
    f = Iff(Atom("P", (Var("x"),)), Atom("Q", (Var("x"),)))
    assert subst(f, "x", Const(1)) == Iff(Atom("P", (Const(1),)), Atom("Q", (Const(1),)))


# ---------------------------------------------------------------------------
# __repr__ coverage — one assertion per formula/term type
# ---------------------------------------------------------------------------


def test_repr_var() -> None:
    assert repr(Var("x")) == "x"


def test_repr_const_int() -> None:
    assert repr(Const(7)) == "7"


def test_repr_func_nullary() -> None:
    assert repr(Func("f", ())) == "f"


def test_repr_func_with_args() -> None:
    assert repr(Func("f", (Var("x"), Const(1)))) == "f(x, 1)"


def test_repr_atom_nullary() -> None:
    assert repr(Atom("P")) == "P"


def test_repr_atom_with_args() -> None:
    assert repr(Atom("P", (Var("x"),))) == "P(x)"


def test_repr_equals() -> None:
    assert repr(Equals(Var("x"), Const(0))) == "(x = 0)"


def test_repr_not() -> None:
    assert repr(Not(Atom("P"))) == "~P"


def test_repr_and() -> None:
    assert repr(And(Atom("P"), Atom("Q"))) == "(P & Q)"


def test_repr_or() -> None:
    assert repr(Or(Atom("P"), Atom("Q"))) == "(P | Q)"


def test_repr_implies() -> None:
    assert repr(Implies(Atom("P"), Atom("Q"))) == "(P -> Q)"


def test_repr_iff() -> None:
    assert repr(Iff(Atom("P"), Atom("Q"))) == "(P <-> Q)"


def test_repr_bot() -> None:
    assert repr(Bot()) == "_|_"


def test_repr_forall() -> None:
    assert repr(ForAll("x", Atom("P", (Var("x"),)))) == "(forall x. P(x))"


def test_repr_exists() -> None:
    assert repr(Exists("x", Atom("P", (Var("x"),)))) == "(exists x. P(x))"


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------

# Small strategies for generating random formulas

var_names = st.sampled_from(["x", "y", "z", "w"])
const_vals = st.integers(min_value=0, max_value=9)


@st.composite
def terms(draw: st.DrawFn, max_depth: int = 2) -> Var | Const | Func:
    if max_depth == 0:
        return draw(st.one_of(
            var_names.map(Var),
            const_vals.map(Const),
        ))
    return draw(st.one_of(
        var_names.map(Var),
        const_vals.map(Const),
        st.builds(
            Func,
            name=st.sampled_from(["f", "g", "h"]),
            args=st.tuples(terms(max_depth=max_depth - 1)),
        ),
    ))


@st.composite
def formulas(draw: st.DrawFn, max_depth: int = 2) -> ...:
    if max_depth == 0:
        pred = draw(st.sampled_from(["P", "Q", "R"]))
        arg = draw(terms())
        return Atom(pred, (arg,))
    return draw(st.one_of(
        st.builds(Atom, pred=st.sampled_from(["P", "Q", "R"]), args=st.tuples(terms())),
        st.builds(Not, body=formulas(max_depth=max_depth - 1)),
        st.builds(And, left=formulas(max_depth=max_depth - 1), right=formulas(max_depth=max_depth - 1)),
        st.builds(ForAll, var=var_names, body=formulas(max_depth=max_depth - 1)),
        st.just(Bot()),
    ))


@given(f=formulas(), var=var_names, repl=terms())
@settings(max_examples=200)
def test_subst_free_vars_subset(f: ..., var: str, repl: Var | Const | Func) -> None:
    # free_vars(subst(f, var, repl)) ⊆ (free_vars(f) - {var}) ∪ free_vars_term(repl)
    result = subst(f, var, repl)
    expected_upper_bound = (free_vars(f) - {var}) | free_vars_term(repl)
    assert free_vars(result) <= expected_upper_bound


@given(f=formulas(), var=var_names, repl=terms())
@settings(max_examples=200)
def test_subst_identity_when_not_free(f: ..., var: str, repl: Var | Const | Func) -> None:
    # subst is identity when var not free in f
    if var not in free_vars(f):
        assert subst(f, var, repl) == f


@given(f=formulas())
@settings(max_examples=300)
def test_subst_self_var_identity(f: ...) -> None:
    # subst(f, x, Var(x)) == f for any x
    for var in ["x", "y", "z"]:
        assert subst(f, var, Var(var)) == f
