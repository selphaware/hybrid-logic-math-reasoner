"""Tests for hlmr.unify.substitution (M1 §7.1).

Note: tests/test_substitution.py covers hlmr.ir.formula.subst (logical-variable
substitution). This file covers hlmr.unify.substitution (metavariable substitution).
"""

from __future__ import annotations

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Func,
    Iff,
    Implies,
    Not,
    Or,
    Var,
)
from hlmr.ir.meta import Meta
from hlmr.unify.substitution import (
    Substitution,
    apply_to_formula,
    apply_to_term,
    compose,
)

# ---------------------------------------------------------------------------
# apply_to_term
# ---------------------------------------------------------------------------


def test_apply_term_empty_subst_unchanged() -> None:
    for t in [Var("x"), Const(1), Meta("?X"), Func("f", (Meta("?X"),))]:
        assert apply_to_term({}, t) is t


def test_apply_term_meta_in_subst() -> None:
    s: Substitution = {"?X": Const("a")}
    assert apply_to_term(s, Meta("?X")) == Const("a")


def test_apply_term_meta_not_in_subst() -> None:
    s: Substitution = {"?X": Const("a")}
    assert apply_to_term(s, Meta("?Y")) == Meta("?Y")


def test_apply_term_var_untouched() -> None:
    # Var is NOT a substitution target, even if the subst has a matching key.
    s: Substitution = {"x": Const("a"), "?x": Const("b")}
    assert apply_to_term(s, Var("x")) == Var("x")


def test_apply_term_const_untouched() -> None:
    s: Substitution = {"?X": Const("a")}
    assert apply_to_term(s, Const(42)) == Const(42)


def test_apply_term_func_meta_in_args() -> None:
    s: Substitution = {"?X": Const("alice")}
    t = Func("f", (Meta("?X"), Var("y")))
    assert apply_to_term(s, t) == Func("f", (Const("alice"), Var("y")))


def test_apply_term_func_nested() -> None:
    s: Substitution = {"?X": Const(1)}
    inner = Func("g", (Meta("?X"),))
    outer = Func("f", (inner,))
    result = apply_to_term(s, outer)
    assert result == Func("f", (Func("g", (Const(1),)),))


def test_apply_term_func_no_change_returns_same() -> None:
    # No Meta in args → same object returned (optimisation).
    s: Substitution = {"?X": Const("a")}
    t = Func("f", (Var("y"),))
    assert apply_to_term(s, t) is t


def test_apply_term_one_pass_no_chaining() -> None:
    # s = {"?X": Meta("?Y"), "?Y": Const("a")}
    # apply_to_term(s, Meta("?X")) must return Meta("?Y"), NOT Const("a").
    # One-pass contract: chaining is the unifier's responsibility.
    s: Substitution = {"?X": Meta("?Y"), "?Y": Const("a")}
    result = apply_to_term(s, Meta("?X"))
    assert result == Meta("?Y")
    assert result != Const("a")


def test_apply_term_replacement_is_meta_itself_untouched() -> None:
    # If the replacement is a Meta and that Meta isn't in s, it stays.
    s: Substitution = {"?X": Meta("?Z")}
    assert apply_to_term(s, Meta("?X")) == Meta("?Z")


# ---------------------------------------------------------------------------
# apply_to_formula
# ---------------------------------------------------------------------------


def test_apply_formula_empty_subst_identity() -> None:
    f = Atom("p", (Meta("?X"),))
    assert apply_to_formula({}, f) is f


def test_apply_formula_atom() -> None:
    s: Substitution = {"?X": Const("alice")}
    f = Atom("parent", (Meta("?X"), Var("y")))
    assert apply_to_formula(s, f) == Atom("parent", (Const("alice"), Var("y")))


def test_apply_formula_equals_lhs() -> None:
    s: Substitution = {"?X": Const(0)}
    f = Equals(Meta("?X"), Var("y"))
    assert apply_to_formula(s, f) == Equals(Const(0), Var("y"))


def test_apply_formula_equals_rhs() -> None:
    s: Substitution = {"?Y": Const(0)}
    f = Equals(Var("x"), Meta("?Y"))
    assert apply_to_formula(s, f) == Equals(Var("x"), Const(0))


def test_apply_formula_not() -> None:
    s: Substitution = {"?X": Const("a")}
    f = Not(Atom("p", (Meta("?X"),)))
    assert apply_to_formula(s, f) == Not(Atom("p", (Const("a"),)))


def test_apply_formula_and() -> None:
    s: Substitution = {"?X": Const("a")}
    f = And(Atom("p", (Meta("?X"),)), Atom("q", (Meta("?X"),)))
    expected = And(Atom("p", (Const("a"),)), Atom("q", (Const("a"),)))
    assert apply_to_formula(s, f) == expected


def test_apply_formula_or() -> None:
    s: Substitution = {"?X": Const("a")}
    f = Or(Atom("p", (Meta("?X"),)), Atom("q"))
    assert apply_to_formula(s, f) == Or(Atom("p", (Const("a"),)), Atom("q"))


def test_apply_formula_implies() -> None:
    s: Substitution = {"?X": Const("a")}
    f = Implies(Atom("p", (Meta("?X"),)), Atom("q", (Meta("?X"),)))
    expected = Implies(Atom("p", (Const("a"),)), Atom("q", (Const("a"),)))
    assert apply_to_formula(s, f) == expected


def test_apply_formula_iff() -> None:
    s: Substitution = {"?X": Const("a")}
    f = Iff(Atom("p", (Meta("?X"),)), Atom("q", (Meta("?X"),)))
    expected = Iff(Atom("p", (Const("a"),)), Atom("q", (Const("a"),)))
    assert apply_to_formula(s, f) == expected


def test_apply_formula_bot_unchanged() -> None:
    # Bot has no Terms inside; the same instance is returned.
    s: Substitution = {"?X": Const("a")}
    b = Bot()
    assert apply_to_formula(s, b) is b


def test_apply_formula_forall_body_substituted() -> None:
    # ForAll bound var "x" is a str, not a Meta — unaffected by substitution.
    # Meta("?X") in the body IS substituted.
    s: Substitution = {"?X": Const("alice")}
    f = ForAll("x", Atom("mortal", (Meta("?X"),)))
    result = apply_to_formula(s, f)
    assert result == ForAll("x", Atom("mortal", (Const("alice"),)))
    assert result.var == "x"  # bound variable name unchanged


def test_apply_formula_exists_body_substituted() -> None:
    s: Substitution = {"?X": Var("y")}
    f = Exists("z", Atom("p", (Meta("?X"), Var("z"))))
    result = apply_to_formula(s, f)
    assert result == Exists("z", Atom("p", (Var("y"), Var("z"))))


def test_apply_formula_no_meta_in_formula_unchanged() -> None:
    s: Substitution = {"?X": Const("a")}
    f = Atom("human", (Const("socrates"),))
    assert apply_to_formula(s, f) is f


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------


def test_compose_empty_s1_is_s2() -> None:
    s2: Substitution = {"?X": Const("a"), "?Y": Var("z")}
    assert compose({}, s2) == s2


def test_compose_empty_s2_is_s1() -> None:
    s1: Substitution = {"?X": Const("a"), "?Y": Var("z")}
    assert compose(s1, {}) == s1


def test_compose_worked_example() -> None:
    # From the §7.1 docstring:
    # s1 = {"?X": Const("a")}, s2 = {"?Y": Meta("?X")}
    # compose(s1, s2) = {"?Y": Const("a"), "?X": Const("a")}
    s1: Substitution = {"?X": Const("a")}
    s2: Substitution = {"?Y": Meta("?X")}
    result = compose(s1, s2)
    assert result == {"?Y": Const("a"), "?X": Const("a")}


def test_compose_associativity() -> None:
    # compose(compose(s1, s2), s3) == compose(s1, compose(s2, s3))
    s1: Substitution = {"?X": Const("a")}
    s2: Substitution = {"?Y": Meta("?X")}
    s3: Substitution = {"?Z": Meta("?Y")}
    lhs = compose(compose(s1, s2), s3)
    rhs = compose(s1, compose(s2, s3))
    assert lhs == rhs
    # Both should give {"?Z": Const("a"), "?Y": Const("a"), "?X": Const("a")}
    assert lhs == {"?Z": Const("a"), "?Y": Const("a"), "?X": Const("a")}


def test_compose_contract_apply_term() -> None:
    # apply(compose(s1, s2), t) == apply(s1, apply(s2, t))
    s1: Substitution = {"?X": Const("a")}
    s2: Substitution = {"?Y": Meta("?X")}
    c = compose(s1, s2)
    for t in [Meta("?Y"), Meta("?X"), Func("f", (Meta("?Y"),)), Var("z"), Const(1)]:
        assert apply_to_term(c, t) == apply_to_term(s1, apply_to_term(s2, t))


def test_compose_s2_key_shadows_s1() -> None:
    # When s2 binds a key that s1 also binds, s2's binding is resolved
    # through s1 — s2 is applied first.
    s1: Substitution = {"?X": Const("b")}
    s2: Substitution = {"?X": Const("a")}
    # apply(s2, Meta("?X")) = Const("a"); apply(s1, Const("a")) = Const("a")
    result = compose(s1, s2)
    assert apply_to_term(result, Meta("?X")) == Const("a")
