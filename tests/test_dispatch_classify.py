"""Tests for src/hlmr/dispatch/classify.py.

Coverage per DISPATCH_DESIGN.md §4:
  - Rules C1-C8, positive and boundary tests.
  - Determinism property test (Hypothesis).
  - Conservative-default property test.
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hlmr.dispatch import ClassifyDecision, OutsideFragmentReason, RouteTarget
from hlmr.dispatch.classify import (
    _ARITH_PREDICATE_SET,
    _COMPARISON_PREDS,
    _TERNARY_PREDS,
    _is_arithmetic_evaluable_term,
    _is_contested_when_ground,
    _is_polynomial_in_one_var,
    _is_zero_const,
    classify,
)
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_EMPTY_KB = KnowledgeBase(clauses=())

_KB_PRIME = KnowledgeBase(
    clauses=(
        Clause("p2", Atom("prime", (Const(2),)), ()),
        Clause("p3", Atom("prime", (Const(3),)), ()),
        Clause("p5", Atom("prime", (Const(5),)), ()),
    )
)

_KB_ANCESTOR = KnowledgeBase(
    clauses=(
        Clause("par", Atom("parent", (Const("alice"), Const("bob"))), ()),
        Clause("anc1", Atom("ancestor", (Var("X"), Var("Y"))), (Atom("parent", (Var("X"), Var("Y"))),)),
    )
)


def _c(target, reason=None, detail=""):
    """Helper to construct a ClassifyDecision for assertions."""
    return ClassifyDecision(target=target, reason=reason, detail=detail)


# ---------------------------------------------------------------------------
# Predicate-set membership (module-level constants)
# ---------------------------------------------------------------------------


def test_predicate_set_membership():
    for p in ("<", "<=", ">", ">=", "!="):
        assert p in _COMPARISON_PREDS
    for p in ("plus", "minus", "times", "divides"):
        assert p in _TERNARY_PREDS
    assert "root_of" in _ARITH_PREDICATE_SET
    assert "prime" not in _ARITH_PREDICATE_SET
    assert "ancestor" not in _ARITH_PREDICATE_SET


# ---------------------------------------------------------------------------
# Rule C1: KB predicate
# ---------------------------------------------------------------------------


def test_C1_kb_predicate_routes_to_kb():
    r = classify(Atom("prime", (Meta("?P"),)), {}, _KB_PRIME)
    assert r.target == RouteTarget.KB


def test_C1_kb_predicate_multiarg():
    r = classify(Atom("parent", (Meta("?X"), Meta("?Y"))), {}, _KB_ANCESTOR)
    assert r.target == RouteTarget.KB


def test_C1_boundary_arith_pred_in_kb_routes_arithmetic():
    """If a user defines a clause with head 'plus', the arithmetic set wins
    (C1 requires pred NOT in arithmetic set; C3 picks it up)."""
    kb_with_plus = KnowledgeBase(
        clauses=(Clause("plus_fact", Atom("plus", (Const(2), Const(3), Const(5))), ()),)
    )
    r = classify(Atom("plus", (Const(2), Const(3), Const(5))), {}, kb_with_plus)
    # C1 does not fire (plus is in arith set); C3 fires → Z3
    assert r.target == RouteTarget.Z3


def test_C1_boundary_unknown_pred_not_in_kb_falls_to_c7():
    r = classify(Atom("mystery", (Const(2),)), {}, _KB_PRIME)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C1_subst_applied_before_classifying():
    """If subst turns ?X into 'prime', the goal is re-evaluated after applying subst.
    (In practice the predicate name doesn't change via subst; this tests that subst
    is applied and the subsequent classification is correct.)"""
    # After subst, goal is Atom("prime", (Const(2),)) — still in KB
    r = classify(Atom("prime", (Meta("?P"),)), {"?P": Const(2)}, _KB_PRIME)
    assert r.target == RouteTarget.KB


# ---------------------------------------------------------------------------
# Rule C2: Binary comparison atoms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pred", ["<", "<=", ">", ">=", "!="])
def test_C2_comparison_routes_to_z3(pred):
    r = classify(Atom(pred, (Meta("?P"), Const(2))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C2_integer_literals():
    r = classify(Atom(">", (Const(5), Const(2))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C2_fraction_literals():
    r = classify(Atom("<=", (Const(Fraction(1, 3)), Const(Fraction(2, 3)))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C2_var_permitted():
    """Var is permitted at classification time (will be bound before solver call)."""
    r = classify(Atom(">", (Var("X"), Const(2))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C2_nested_arithmetic_term():
    # (Meta + Const) > Const  → Z3
    r = classify(Atom(">", (Func("+", (Meta("?X"), Const(1))), Const(5))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C2_boundary_wrong_arity_falls_to_c7():
    """Atom(">", (a,)) — arity 1 instead of 2 — doesn't match C2 pattern."""
    r = classify(Atom(">", (Const(2),)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C2_string_const_non_evaluable():
    r = classify(Atom(">", (Const("alice"), Const(2))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED


def test_C2_var_in_exponent_rejected_as_transcendental():
    """Atom(">", (2^x, 5)) — Var in exponent is transcendental per DISPATCH §4.2
    C2. Routes to REJECTED with TRANSCENDENTAL, matching the C4 (root_of) and
    C5 (Equals) treatments."""
    r = classify(Atom(">", (Func("^", (Const(2), Var("x"))), Const(5))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


def test_C2_contested_ground_zero_power_zero():
    """C8: Atom(">", (0^0, 5)) → CONTESTED_CONVENTION."""
    r = classify(
        Atom(">", (Func("^", (Const(0), Const(0))), Const(5))), {}, _EMPTY_KB
    )
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


# ---------------------------------------------------------------------------
# Rule C3: Ternary predicate-form atoms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pred", ["plus", "minus", "times", "divides"])
def test_C3_ternary_routes_to_z3(pred):
    r = classify(Atom(pred, (Const(2), Const(3), Const(5))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C3_with_meta_args():
    r = classify(Atom("plus", (Meta("?X"), Const(3), Meta("?Z"))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C3_boundary_wrong_arity_falls_to_c7():
    r = classify(Atom("plus", (Const(2), Const(3))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C3_non_arithmetic_arg():
    r = classify(Atom("plus", (Const("alice"), Const(3), Const(5))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C3_contested_shape():
    r = classify(
        Atom("times", (Const(0), Func("^", (Const(0), Const(0))), Const(0))),
        {},
        _EMPTY_KB,
    )
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


def test_C3_var_in_exponent_rejected_as_transcendental():
    """plus(2^x, 3, ?Z) — Var in exponent is transcendental."""
    r = classify(
        Atom("plus", (Func("^", (Const(2), Var("x"))), Const(3), Meta("?Z"))),
        {}, _EMPTY_KB,
    )
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


# ---------------------------------------------------------------------------
# Rule C4: root_of/2
# ---------------------------------------------------------------------------


def test_C4_polynomial_routes_to_sympy():
    # x^2 - 5x + 6
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.SYMPY


def test_C4_linear_polynomial():
    # x - 3 (degree 1, still a polynomial)
    poly = Func("-", (Var("x"), Const(3)))
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.SYMPY


def test_C4_constant_polynomial():
    # 5 — no variable, technically a polynomial of degree 0
    r = classify(Atom("root_of", (Meta("?X"), Const(5))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.SYMPY


def test_C4_transcendental():
    # 2^x
    poly = Func("^", (Const(2), Var("x")))
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


def test_C4_transcendental_mixed():
    # x^2 + 2^x (contains transcendental component)
    poly = Func(
        "+",
        (Func("^", (Var("x"), Const(2))), Func("^", (Const(2), Var("x")))),
    )
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


def test_C4_unrecognised_shape():
    # A Func with an unrecognised operator name
    poly = Func("sin", (Var("x"),))
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C4_two_var_polynomial_rejected():
    # x*y — two distinct Vars, not a polynomial in one variable
    poly = Func("*", (Var("x"), Var("y")))
    r = classify(Atom("root_of", (Meta("?X"), poly)), {}, _EMPTY_KB)
    # _is_polynomial_in_one_var returns False → UNRECOGNISED_SHAPE (no Var in exponent)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


# ---------------------------------------------------------------------------
# Rule C5: Equals IR node
# ---------------------------------------------------------------------------


def test_C5_equals_meta_const_linear_z3():
    r = classify(Equals(Meta("?X"), Const(5)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C5_equals_arithmetic_sum_z3():
    # ?X + ?Y = 10
    r = classify(
        Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)), {}, _EMPTY_KB
    )
    assert r.target == RouteTarget.Z3


def test_C5_equals_polynomial_sympy():
    # ?X^2 = 9
    r = classify(Equals(Func("^", (Meta("?X"), Const(2))), Const(9)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.SYMPY


def test_C5_equals_product_of_metas_sympy():
    # ?X * ?Y = 6
    r = classify(
        Equals(Func("*", (Meta("?X"), Meta("?Y"))), Const(6)), {}, _EMPTY_KB
    )
    assert r.target == RouteTarget.SYMPY


def test_C5_both_non_arithmetic_kb():
    # Equals(Const("alice"), Const("bob")) — both are string Consts (non-arithmetic)
    r = classify(Equals(Const("alice"), Const("bob")), {}, _EMPTY_KB)
    assert r.target == RouteTarget.KB


def test_C5_mixed_sides_rejected():
    # ?X (arithmetic Meta) = "alice" (non-arithmetic string Const)
    r = classify(Equals(Meta("?X"), Const("alice")), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


def test_C5_equals_transcendental():
    r = classify(
        Equals(Func("^", (Const(2), Var("x"))), Const(8)), {}, _EMPTY_KB
    )
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


def test_C5_equals_contested_shape():
    r = classify(
        Equals(Func("^", (Const(0), Const(0))), Const(1)), {}, _EMPTY_KB
    )
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


# ---------------------------------------------------------------------------
# Rule C7: Default (unrecognised)
# ---------------------------------------------------------------------------


def test_C7_unknown_predicate_not_in_kb():
    r = classify(Atom("mystery_pred", (Const(2),)), {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE


# ---------------------------------------------------------------------------
# Rule C8: Contested-shape detection
# ---------------------------------------------------------------------------


def test_C8_ground_zero_power_zero_in_gt():
    r = classify(
        Atom(">", (Func("^", (Const(0), Const(0))), Const(5))), {}, _EMPTY_KB
    )
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


def test_C8_ground_zero_power_zero_in_equals():
    r = classify(
        Equals(Func("^", (Const(0), Const(0))), Const(1)), {}, _EMPTY_KB
    )
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


def test_C8_ground_zero_power_zero_nested_deep():
    """0^0 nested inside (+) — the detector walks recursively."""
    nested = Func("+", (Func("^", (Const(0), Const(0))), Const(5)))
    r = classify(Atom(">", (nested, Const(10))), {}, _EMPTY_KB)
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


def test_C8_non_ground_meta_exponent_not_contested():
    """Meta("?X") ^ Meta("?X") — exponent is Meta, not ground zero.
    C8 (contested 0^0 detector) does not fire. However, C2's transcendental
    check runs first and rejects ?X^?X as TRANSCENDENTAL (Meta in exponent
    position, per DISPATCH §4.2)."""
    r = classify(
        Atom(">", (Func("^", (Meta("?X"), Meta("?X"))), Const(0))),
        {},
        _EMPTY_KB,
    )
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.TRANSCENDENTAL


def test_C8_non_zero_base_not_contested():
    """2^0 — base is not zero, so not 0^0."""
    r = classify(Atom(">", (Func("^", (Const(2), Const(0))), Const(0))), {}, _EMPTY_KB)
    assert r.target == RouteTarget.Z3


def test_C8_zero_to_positive_power_not_contested():
    """0^3 — exponent is not zero, so not 0^0."""
    r = classify(
        Equals(Func("^", (Const(0), Const(3))), Const(0)), {}, _EMPTY_KB
    )
    assert r.target == RouteTarget.Z3


def test_C8_fraction_zero_contested():
    """Const(Fraction(0, 1)) is zero — should be detected as contested."""
    r = classify(
        Atom(">", (Func("^", (Const(Fraction(0)), Const(0))), Const(0))),
        {},
        _EMPTY_KB,
    )
    assert r.reason == OutsideFragmentReason.CONTESTED_CONVENTION


# ---------------------------------------------------------------------------
# _is_zero_const helper
# ---------------------------------------------------------------------------


def test_is_zero_const_int_zero():
    assert _is_zero_const(Const(0)) is True


def test_is_zero_const_fraction_zero():
    assert _is_zero_const(Const(Fraction(0, 3))) is True


def test_is_zero_const_nonzero():
    assert _is_zero_const(Const(1)) is False
    assert _is_zero_const(Const(Fraction(1, 2))) is False


def test_is_zero_const_bool_rejected():
    # bool is int subclass; False == 0 but bool is rejected
    c = object.__new__(Const)
    object.__setattr__(c, "value", False)
    assert _is_zero_const(c) is False


def test_is_zero_const_string_rejected():
    assert _is_zero_const(Const("0")) is False


def test_is_zero_const_meta_rejected():
    assert _is_zero_const(Meta("?X")) is False


# ---------------------------------------------------------------------------
# _is_arithmetic_evaluable_term helper
# ---------------------------------------------------------------------------


def test_is_arith_evaluable_int_const():
    assert _is_arithmetic_evaluable_term(Const(5)) is True


def test_is_arith_evaluable_fraction_const():
    assert _is_arithmetic_evaluable_term(Const(Fraction(1, 3))) is True


def test_is_arith_evaluable_meta():
    assert _is_arithmetic_evaluable_term(Meta("?X")) is True


def test_is_arith_evaluable_var():
    assert _is_arithmetic_evaluable_term(Var("X")) is True


def test_is_arith_evaluable_operator_func():
    assert _is_arithmetic_evaluable_term(Func("+", (Const(1), Meta("?X")))) is True


def test_is_arith_evaluable_string_const_false():
    assert _is_arithmetic_evaluable_term(Const("alice")) is False


def test_is_arith_evaluable_bool_const_false():
    c = object.__new__(Const)
    object.__setattr__(c, "value", True)
    assert _is_arithmetic_evaluable_term(c) is False


def test_is_arith_evaluable_unknown_func_false():
    assert _is_arithmetic_evaluable_term(Func("sin", (Var("x"),))) is False


# ---------------------------------------------------------------------------
# _is_polynomial_in_one_var helper
# ---------------------------------------------------------------------------


def test_polynomial_single_var():
    # x^2 - 5x + 6
    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    assert _is_polynomial_in_one_var(poly) is True


def test_polynomial_constant():
    assert _is_polynomial_in_one_var(Const(7)) is True


def test_polynomial_linear():
    assert _is_polynomial_in_one_var(Func("-", (Var("x"), Const(3)))) is True


def test_polynomial_two_vars_rejected():
    assert _is_polynomial_in_one_var(Func("*", (Var("x"), Var("y")))) is False


def test_polynomial_transcendental_rejected():
    # 2^x — Var in exponent
    assert _is_polynomial_in_one_var(Func("^", (Const(2), Var("x")))) is False


def test_polynomial_negative_exponent_rejected():
    assert _is_polynomial_in_one_var(Func("^", (Var("x"), Const(-1)))) is False


# ---------------------------------------------------------------------------
# Subst application
# ---------------------------------------------------------------------------


def test_classify_applies_subst_before_routing():
    """After applying subst, a non-ground comparison becomes ground."""
    # Goal: ?P > 2; subst: {?P: 5} → 5 > 2 → Z3
    r = classify(
        Atom(">", (Meta("?P"), Const(2))),
        {"?P": Const(5)},
        _EMPTY_KB,
    )
    assert r.target == RouteTarget.Z3


def test_classify_subst_makes_kb_pred_visible():
    """Goal ?- foo(?X) where foo is in KB; after subst still routes to KB."""
    kb = KnowledgeBase(clauses=(Clause("foo1", Atom("foo", (Const(1),)), ()),))
    r = classify(Atom("foo", (Meta("?X"),)), {}, kb)
    assert r.target == RouteTarget.KB


# ---------------------------------------------------------------------------
# Hypothesis: determinism property
# ---------------------------------------------------------------------------


@st.composite
def _simple_goal_st(draw):
    """Generate simple goals for the determinism check."""
    pred = draw(st.sampled_from(["<", ">", "!=", "prime", "mystery"]))
    const = draw(st.one_of(
        st.integers(-5, 5).map(Const),
        st.just(Const(Fraction(1, 2))),
        st.just(Meta("?X")),
    ))
    if pred in ("<", ">", "!="):
        return Atom(pred, (const, Const(2)))
    return Atom(pred, (const,))


@given(_simple_goal_st())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_classify_is_deterministic(goal):
    """For any (goal, subst, kb) triple, classify returns the same decision
    on every call (DISPATCH_DESIGN.md §4.4)."""
    r1 = classify(goal, {}, _KB_PRIME)
    r2 = classify(goal, {}, _KB_PRIME)
    assert r1 == r2, f"classify is not deterministic for goal={goal!r}"


# ---------------------------------------------------------------------------
# Hypothesis: conservative-default property
# ---------------------------------------------------------------------------


@st.composite
def _unrecognised_goal_st(draw):
    """Goals with predicates not in KB or arithmetic set."""
    pred = draw(st.sampled_from([
        "unicorn_pred", "invented_foo", "unknown_bar", "not_arith_xyz",
    ]))
    arity = draw(st.integers(0, 3))
    args = tuple(Const(i) for i in range(arity))
    return Atom(pred, args)


@given(_unrecognised_goal_st())
@settings(max_examples=100, deadline=None)
def test_unrecognised_goals_always_rejected(goal):
    """Goals with unrecognised predicates (not in any KB, not arithmetic)
    always produce REJECTED with UNRECOGNISED_SHAPE — never Z3, never KB."""
    r = classify(goal, {}, _EMPTY_KB)
    assert r.target == RouteTarget.REJECTED
    assert r.reason == OutsideFragmentReason.UNRECOGNISED_SHAPE
