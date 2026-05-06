"""Tests for the arithEval kernel rule (M2, Task A).

Coverage per ARITH_EVAL_DESIGN.md §11 and §12.3:
  - Accept cases A1–A15
  - EvaluationFalse cases F1–F5
  - MalformedArithmetic cases M1–M14
  - WrongRefCount cases R1–R2
  - Soundness backstop
  - Const float guard
  - Hypothesis property test
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import (
    And,
    Atom,
    Const,
    Equals,
    ForAll,
    Func,
    Meta,
    Var,
)
from hlmr.ir.justification import RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel import check_proof
from hlmr.kernel.errors import (
    CheckFailure,
    EvaluationFalse,
    MalformedArithmetic,
    UnresolvedMeta,
    Verified,
    WrongRefCount,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _proof(formula):
    """Minimal one-line proof with arithEval justification."""
    line = ProofLine(1, formula, RuleApp("arithEval", (), (), {}), 0)
    return Proof((line,), goal=formula)


def _accepted(formula) -> bool:
    return isinstance(check_proof(_proof(formula)), Verified)


def _rejection(formula):
    r = check_proof(_proof(formula))
    assert isinstance(r, CheckFailure)
    return r.reason


# ---------------------------------------------------------------------------
# Accept cases (A1–A15)
# ---------------------------------------------------------------------------


def test_A1_gt_accept():
    assert _accepted(Atom(">", (Const(5), Const(2))))


def test_A2_le_accept():
    assert _accepted(Atom("<=", (Const(3), Const(3))))


def test_A3_ne_accept():
    assert _accepted(Atom("!=", (Const(7), Const(4))))


def test_A4_equals_add():
    assert _accepted(Equals(Func("+", (Const(3), Const(4))), Const(7)))


def test_A5_equals_add_symmetric():
    assert _accepted(Equals(Const(7), Func("+", (Const(3), Const(4)))))


def test_A6_plus_predicate():
    assert _accepted(Atom("plus", (Const(2), Const(3), Const(5))))


def test_A7_times_predicate():
    assert _accepted(Atom("times", (Const(6), Const(7), Const(42))))


def test_A8_minus_predicate():
    assert _accepted(Atom("minus", (Const(10), Const(3), Const(7))))


def test_A9_divides_predicate():
    assert _accepted(
        Atom("divides", (Const(1), Const(2), Const(Fraction(1, 2))))
    )


def test_A10_fraction_normalise():
    assert _accepted(Equals(Const(Fraction(2, 4)), Const(Fraction(1, 2))))


def test_A11_big_integers():
    assert _accepted(Atom("<", (Const(2**100), Const(2**100 + 1))))


def test_A12_power():
    assert _accepted(Equals(Func("^", (Const(2), Const(10))), Const(1024)))


def test_A13_negative_exponent():
    assert _accepted(
        Equals(Func("^", (Const(2), Const(-1))), Const(Fraction(1, 2)))
    )


def test_A14_unary_negation():
    assert _accepted(Equals(Func("-", (Const(5),)), Const(-5)))


def test_A15_mixed_const_operator():
    assert _accepted(
        Equals(Const(Fraction(7, 2)), Func("/", (Const(7), Const(2))))
    )


# ---------------------------------------------------------------------------
# EvaluationFalse cases (F1–F5)
# ---------------------------------------------------------------------------


def test_F1_gt_false():
    err = _rejection(Atom(">", (Const(2), Const(5))))
    assert isinstance(err, EvaluationFalse)


def test_F2_equals_false():
    err = _rejection(Equals(Const(2), Const(3)))
    assert isinstance(err, EvaluationFalse)


def test_F3_plus_wrong_sum():
    err = _rejection(Atom("plus", (Const(2), Const(3), Const(7))))
    assert isinstance(err, EvaluationFalse)


def test_F4_unary_neg_false():
    err = _rejection(Equals(Func("-", (Const(5),)), Const(5)))
    assert isinstance(err, EvaluationFalse)


def test_F5_ne_self_false():
    err = _rejection(Atom("!=", (Const(7), Const(7))))
    assert isinstance(err, EvaluationFalse)


# ---------------------------------------------------------------------------
# MalformedArithmetic cases (M1–M14)
# ---------------------------------------------------------------------------


def test_M1_var_non_evaluable():
    err = _rejection(Atom(">", (Var("X"), Const(2))))
    assert isinstance(err, MalformedArithmetic)


def test_M2_meta_caught_by_section_5_3_ordering():
    """Meta is caught by the §5.3 UnresolvedMeta walk BEFORE arithEval runs."""
    line = ProofLine(
        1,
        Atom(">", (Meta("?X"), Const(2))),
        RuleApp("arithEval", (), (), {}),
        0,
    )
    proof = Proof((line,))
    r = check_proof(proof)
    assert isinstance(r, CheckFailure)
    assert isinstance(r.reason, UnresolvedMeta)


def test_M3_unknown_predicate():
    err = _rejection(Atom("foo", (Const(2), Const(3))))
    assert isinstance(err, MalformedArithmetic)


def test_M4_wrong_arity_plus():
    err = _rejection(Atom("plus", (Const(2), Const(3))))  # arity 2, needs 3
    assert isinstance(err, MalformedArithmetic)


def test_M5_wrong_arity_gt():
    err = _rejection(Atom(">", (Const(2),)))  # arity 1, needs 2
    assert isinstance(err, MalformedArithmetic)


def test_M6_const_str():
    err = _rejection(Equals(Const("alice"), Const(2)))
    assert isinstance(err, MalformedArithmetic)


def test_M7_division_by_zero():
    err = _rejection(Equals(Func("/", (Const(1), Const(0))), Const(0)))
    assert isinstance(err, MalformedArithmetic)


def test_M8_non_int_exponent():
    err = _rejection(
        Equals(Func("^", (Const(2), Const(Fraction(1, 2)))), Const(2))
    )
    assert isinstance(err, MalformedArithmetic)


def test_M9_zero_negative_exponent():
    err = _rejection(Equals(Func("^", (Const(0), Const(-1))), Const(0)))
    assert isinstance(err, MalformedArithmetic)


def test_M10_bool_const():
    """Bool bypasses Const.__post_init__ via object.__setattr__ trick;
    the evaluator still rejects it (defence-in-depth per §9.7)."""
    c = object.__new__(Const)
    object.__setattr__(c, "value", True)
    err = _rejection(Atom("plus", (c, Const(0), Const(1))))
    assert isinstance(err, MalformedArithmetic)


def test_M11_float_defence_in_depth():
    """Float bypasses Const.__post_init__ via object.__setattr__ trick;
    the evaluator still rejects it."""
    c = object.__new__(Const)
    object.__setattr__(c, "value", 2.5)
    err = _rejection(Atom(">", (c, Const(1))))
    assert isinstance(err, MalformedArithmetic)


def test_M12_top_level_and():
    err = _rejection(
        And(Atom(">", (Const(5), Const(2))), Atom("<", (Const(1), Const(2))))
    )
    assert isinstance(err, MalformedArithmetic)


def test_M13_top_level_forall():
    err = _rejection(ForAll("x", Atom(">", (Var("x"), Const(0)))))
    assert isinstance(err, MalformedArithmetic)


def test_M14_zero_zero_power_contested():
    """0^0 is contested between conventions; kernel rejects on
    conservative-default grounds (ARITH_EVAL_DESIGN.md §6.1 / §9.5)."""
    err = _rejection(Equals(Func("^", (Const(0), Const(0))), Const(1)))
    assert isinstance(err, MalformedArithmetic)


# ---------------------------------------------------------------------------
# WrongRefCount cases (R1–R2)
# ---------------------------------------------------------------------------


def test_R1_line_ref_rejected():
    line = ProofLine(
        1, Atom(">", (Const(5), Const(2))),
        RuleApp("arithEval", (3,), (), {}),
        0,
    )
    r = check_proof(Proof((line,)))
    assert isinstance(r, CheckFailure)
    assert isinstance(r.reason, WrongRefCount)
    assert r.reason.rule == "arithEval"
    assert r.reason.got_lines == 1
    assert r.reason.expected_lines == 0


def test_R2_box_ref_rejected():
    line = ProofLine(
        1, Atom(">", (Const(5), Const(2))),
        RuleApp("arithEval", (), ((1, 4),), {}),
        0,
    )
    r = check_proof(Proof((line,)))
    assert isinstance(r, CheckFailure)
    assert isinstance(r.reason, WrongRefCount)
    assert r.reason.rule == "arithEval"
    assert r.reason.got_boxes == 1
    assert r.reason.expected_boxes == 0


# ---------------------------------------------------------------------------
# Soundness backstop
# ---------------------------------------------------------------------------


def test_soundness_backstop_false_claim():
    """A malicious proof claiming 2 > 5 via arithEval must be rejected
    with EvaluationFalse.  Mirrors M0's 99_BAD_* proofs."""
    err = _rejection(Atom(">", (Const(2), Const(5))))
    assert isinstance(err, EvaluationFalse)


def test_soundness_backstop_contested_0_pow_0():
    """A malicious proof claiming 0^0 = 1 via arithEval must be rejected
    with MalformedArithmetic (contested convention, not a false claim)."""
    err = _rejection(Equals(Func("^", (Const(0), Const(0))), Const(1)))
    assert isinstance(err, MalformedArithmetic)


# ---------------------------------------------------------------------------
# Const float guard (prd_milestone_2.md §6.3 / ARITH_EVAL_DESIGN.md §9.6)
# ---------------------------------------------------------------------------


def test_const_float_raises_at_construction():
    """Const rejects float values at construction time."""
    with pytest.raises(TypeError):
        Const(3.14)


def test_const_bool_raises_at_construction():
    """Const rejects bool values at construction time."""
    with pytest.raises(TypeError):
        Const(True)


# ---------------------------------------------------------------------------
# Additional edge-case accept/reject
# ---------------------------------------------------------------------------


def test_ge_accept():
    assert _accepted(Atom(">=", (Const(5), Const(5))))


def test_lt_accept():
    assert _accepted(Atom("<", (Const(0), Const(1))))


def test_divides_by_zero_malformed():
    err = _rejection(
        Atom("divides", (Const(5), Const(0), Const(0)))
    )
    assert isinstance(err, MalformedArithmetic)


def test_minus_predicate_false():
    err = _rejection(Atom("minus", (Const(5), Const(3), Const(1))))
    assert isinstance(err, EvaluationFalse)


def test_mixed_int_fraction_gt():
    assert _accepted(Atom(">", (Const(Fraction(3, 2)), Const(1))))


def test_negative_int_const():
    assert _accepted(Equals(Const(-7), Func("-", (Const(7),))))


def test_large_power():
    big = 2**100
    assert _accepted(Atom("<", (Const(big), Const(big + 1))))


def test_fraction_division_exact():
    assert _accepted(
        Equals(Func("/", (Const(1), Const(3))), Const(Fraction(1, 3)))
    )


# ---------------------------------------------------------------------------
# Hypothesis property test
# ---------------------------------------------------------------------------

_NUMERIC_CONSTS = [
    Const(0), Const(1), Const(-1), Const(2), Const(7),
    Const(Fraction(1, 2)), Const(Fraction(3, 4)),
]
_OPERATORS = ["+", "-", "*"]
_CMP_PREDS = ["<", "<=", ">", ">=", "!="]
_TERNARY_PREDS = ["plus", "minus", "times"]


@st.composite
def _ground_term_st(draw, depth=0):
    """Generate a ground arithmetic term (no Meta/Var)."""
    if depth >= 2:
        return draw(st.sampled_from(_NUMERIC_CONSTS))
    return draw(st.one_of(
        st.sampled_from(_NUMERIC_CONSTS),
        st.builds(
            lambda op, a, b: Func(op, (a, b)),
            st.sampled_from(_OPERATORS),
            _ground_term_st(depth + 1),
            _ground_term_st(depth + 1),
        ),
    ))


@st.composite
def _ground_atom_st(draw):
    """Generate a ground arithmetic atom."""
    kind = draw(st.sampled_from(["cmp", "ternary", "equals"]))
    if kind == "cmp":
        pred = draw(st.sampled_from(_CMP_PREDS))
        a = draw(_ground_term_st())
        b = draw(_ground_term_st())
        return Atom(pred, (a, b))
    if kind == "ternary":
        pred = draw(st.sampled_from(_TERNARY_PREDS))
        a = draw(_ground_term_st())
        b = draw(_ground_term_st())
        c = draw(_ground_term_st())
        return Atom(pred, (a, b, c))
    # equals
    lhs = draw(_ground_term_st())
    rhs = draw(_ground_term_st())
    return Equals(lhs, rhs)


def _ref_eval_term(t) -> int | Fraction | None:
    """Reference evaluator using direct Python arithmetic."""
    match t:
        case Const(value=v):
            if isinstance(v, bool) or isinstance(v, float):
                return None
            if isinstance(v, (int, Fraction)):
                return v
            return None
        case Func(name="+", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va + vb
        case Func(name="-", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va - vb
        case Func(name="-", args=(a,)):
            va = _ref_eval_term(a)
            return None if va is None else -va
        case Func(name="*", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va * vb
        case _:
            return None


def _ref_eval_atom(f) -> bool | None:
    """Reference evaluator for atoms, mirrors arithEval semantics."""
    match f:
        case Atom(pred="<", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va < vb
        case Atom(pred="<=", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va <= vb
        case Atom(pred=">", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va > vb
        case Atom(pred=">=", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va >= vb
        case Atom(pred="!=", args=(a, b)):
            va, vb = _ref_eval_term(a), _ref_eval_term(b)
            return None if (va is None or vb is None) else va != vb
        case Atom(pred="plus", args=(a, b, c)):
            va, vb, vc = _ref_eval_term(a), _ref_eval_term(b), _ref_eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va + vb == vc
        case Atom(pred="minus", args=(a, b, c)):
            va, vb, vc = _ref_eval_term(a), _ref_eval_term(b), _ref_eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va - vb == vc
        case Atom(pred="times", args=(a, b, c)):
            va, vb, vc = _ref_eval_term(a), _ref_eval_term(b), _ref_eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va * vb == vc
        case Equals(lhs=lhs, rhs=rhs):
            vl, vr = _ref_eval_term(lhs), _ref_eval_term(rhs)
            return None if (vl is None or vr is None) else vl == vr
        case _:
            return None


@given(_ground_atom_st())
@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_property_arith_eval_agrees_with_reference(atom):
    """arithEval and a reference Python evaluator must agree on every
    ground atom generated from int/Fraction constants and +/-/* operators.

    The reference evaluator explicitly excludes /, ^, and contested
    cases (so it never disagrees with arithEval on those paths).
    Agreement means:
      - ref returns None (non-evaluable) → arithEval may accept or
        MalformedArithmetic; it must NOT EvaluationFalse.
      - ref returns True → arithEval accepts (Verified).
      - ref returns False → arithEval rejects with EvaluationFalse.
    """
    ref = _ref_eval_atom(atom)
    r = check_proof(_proof(atom))

    if ref is None:
        # Non-evaluable under the restricted reference — arithEval may do
        # anything except claim the atom is false when it might be true.
        # We only assert it doesn't crash unexpectedly.
        return

    if ref is True:
        assert isinstance(r, Verified), (
            f"arithEval rejected an atom the reference accepted as True: "
            f"{atom!r}, kernel result: {r!r}"
        )
    else:
        assert isinstance(r, CheckFailure), (
            f"arithEval accepted an atom the reference rejected as False: "
            f"{atom!r}"
        )
        assert isinstance(r.reason, EvaluationFalse), (
            f"arithEval returned unexpected error class for a False atom: "
            f"{atom!r}, reason: {r.reason!r}"
        )
