"""Invalid proofs must fail with specific error types (prd_milestone_0.md §9.1)."""

import pytest

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Iff,
    Implies,
    Not,
    Or,
    Var,
)
from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel import check_proof
from hlmr.kernel.errors import (
    BadBoxRef,
    CheckFailure,
    EigenvarViolation,
    FormulaMismatch,
    GoalMismatch,
    MissingExtra,
    OutOfScope,
    StructuralError,
    UnknownRule,
    WrongFormulaShape,
    WrongRefCount,
)

P = Atom("P")
Q = Atom("Q")
R = Atom("R")


def expect_failure(proof: Proof, error_type: type) -> CheckFailure:
    result = check_proof(proof)
    assert isinstance(result, CheckFailure), f"Expected CheckFailure, got {result}"
    assert isinstance(result.reason, error_type), (
        f"Expected {error_type.__name__}, got {type(result.reason).__name__}: {result.reason}"
    )
    return result


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------


def test_empty_proof_rejected() -> None:
    expect_failure(Proof(()), StructuralError)


def test_premise_at_nonzero_depth() -> None:
    expect_failure(
        Proof((ProofLine(1, P, Assumption(), 1), ProofLine(2, Q, Premise(), 1))),
        StructuralError,
    )


def test_depth_jump_too_large() -> None:
    # depth jumps from 0 to 2
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Assumption(), 2),
        )),
        StructuralError,
    )


def test_unclosed_box() -> None:
    # Proof ends inside a box
    expect_failure(
        Proof((
            ProofLine(1, P, Assumption(), 1),
        )),
        StructuralError,
    )


def test_assumption_no_depth_increase() -> None:
    # Assumption that doesn't increase depth
    expect_failure(
        Proof((
            ProofLine(1, P, Assumption(), 0),
        )),
        StructuralError,
    )


def test_non_assumption_opens_box() -> None:
    # depth increases but not via Assumption
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Premise(), 1),
        )),
        StructuralError,
    )


# ---------------------------------------------------------------------------
# UnknownRule
# ---------------------------------------------------------------------------


def test_unknown_rule() -> None:
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, RuleApp("nonexistent_rule", (1,)), 0),
        )),
        UnknownRule,
    )


# ---------------------------------------------------------------------------
# WrongRefCount
# ---------------------------------------------------------------------------


def test_andI_wrong_ref_count() -> None:
    # andI needs 2 line refs; give it 1
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, And(P, Q), RuleApp("andI", (1,)), 0),
        )),
        WrongRefCount,
    )


def test_impI_wrong_ref_count() -> None:
    # impI needs 0 line refs and 1 box ref; give it 1 line ref
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Implies(P, P), RuleApp("impI", (1,)), 0),
        )),
        WrongRefCount,
    )


# ---------------------------------------------------------------------------
# WrongFormulaShape
# ---------------------------------------------------------------------------


def test_andE_L_not_an_and() -> None:
    # andE_L requires an And, but ref is P (not And)
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, P, RuleApp("andE_L", (1,)), 0),
        )),
        WrongFormulaShape,
    )


def test_impE_not_an_implies() -> None:
    expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, Q, RuleApp("impE", (1, 2)), 0),
        )),
        WrongFormulaShape,
    )


def test_notI_conclusion_not_not() -> None:
    # notI requires ~P as conclusion but we write P (WrongFormulaShape)
    # Box (2,4): P ⊢ Bot is valid; conclusion P is not Not(_)
    expect_failure(
        Proof((
            ProofLine(1, Not(P), Premise(), 0),
            ProofLine(2, P, Assumption(), 1),
            ProofLine(3, Not(P), RuleApp("reit", (1,)), 1),
            ProofLine(4, Bot(), RuleApp("notE", (2, 3)), 1),
            ProofLine(5, P, RuleApp("notI", box_refs=((2, 4),)), 0),
        )),
        WrongFormulaShape,
    )


# ---------------------------------------------------------------------------
# FormulaMismatch — the 99_BAD_andI case
# ---------------------------------------------------------------------------


def test_andI_formula_mismatch() -> None:
    # andI(P, Q) but conclusion is And(Q, P) — wrong order
    result = expect_failure(
        Proof((
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, And(Q, P), RuleApp("andI", (1, 2)), 0),
        )),
        FormulaMismatch,
    )
    assert result.line == 3


def test_impE_conclusion_mismatch() -> None:
    # P -> Q, P ⊢ (wrong conclusion R)
    expect_failure(
        Proof((
            ProofLine(1, Implies(P, Q), Premise(), 0),
            ProofLine(2, P, Premise(), 0),
            ProofLine(3, R, RuleApp("impE", (1, 2)), 0),
        )),
        FormulaMismatch,
    )


# ---------------------------------------------------------------------------
# OutOfScope — the 99_BAD_oos case
# ---------------------------------------------------------------------------


def test_reference_into_discharged_box() -> None:
    # Line 3 refers to line 1 which is inside the box [1,2]
    result = expect_failure(
        Proof((
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("reit", (1,)), 1),
            ProofLine(3, Implies(P, P), RuleApp("impI", box_refs=((1, 2),)), 0),
            # Now illegally reference line 1 from outside its box
            ProofLine(4, P, RuleApp("reit", (1,)), 0),
        )),
        OutOfScope,
    )
    assert result.line == 4


def test_reit_from_deeper_scope() -> None:
    # Line 4 inside a second box tries to reit line 2 from a discharged box
    expect_failure(
        Proof((
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("reit", (1,)), 1),
            ProofLine(3, Implies(P, P), RuleApp("impI", box_refs=((1, 2),)), 0),
            ProofLine(4, Q, Assumption(), 1),
            ProofLine(5, P, RuleApp("reit", (2,)), 1),  # line 2 is discharged
            ProofLine(6, Implies(Q, P), RuleApp("impI", box_refs=((4, 5),)), 0),
        )),
        OutOfScope,
    )


# ---------------------------------------------------------------------------
# BadBoxRef
# ---------------------------------------------------------------------------


def test_impI_box_not_discharged() -> None:
    # impI box ref pointing to an open box (box end == conclusion line - 1,
    # but depth not returned to 0 before conclusion)
    # Build a proof where the box isn't properly closed
    expect_failure(
        Proof((
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("impI", box_refs=((1, 1),)), 1),
        )),
        BadBoxRef,  # box not discharged at depth-1 line
    )


# ---------------------------------------------------------------------------
# EigenvarViolation — the 99_BAD_eigenvar case
# ---------------------------------------------------------------------------


def test_forallI_eigenvar_in_accessible_line() -> None:
    # eigenvar 'a' appears free in premise P(a) before the box
    Pa = Atom("P", (Var("a"),))
    Fa = ForAll("x", Atom("P", (Var("x"),)))
    result = expect_failure(
        Proof((
            ProofLine(1, Pa, Premise(), 0),       # 'a' is free here
            ProofLine(2, Pa, Assumption(), 1),
            ProofLine(3, Fa, RuleApp("forallI", box_refs=((2, 2),), extra={"eigenvar": "a"}), 0),
        )),
        EigenvarViolation,
    )
    assert result.line == 3


def test_forallI_eigenvar_in_body() -> None:
    # eigenvar appears free in the body of the forall being derived
    # forall x. P(x, a) — eigenvar 'a' is free in body P(x, a)
    body = Atom("P", (Var("x"), Var("a")))
    f = ForAll("x", body)
    expect_failure(
        Proof((
            ProofLine(1, Atom("P", (Var("a"), Var("a"))), Assumption(), 1),
            ProofLine(2, f, RuleApp("forallI", box_refs=((1, 1),), extra={"eigenvar": "a"}), 0),
        )),
        EigenvarViolation,
    )


def test_existsE_eigenvar_escapes() -> None:
    # eigenvar 'a' appears free in the conclusion P(a): eigenvar escapes scope
    # exists x. P(x) has no 'a', so the "accessible line" check doesn't fire first
    Ex = Exists("x", Atom("P", (Var("x"),)))
    Pa = Atom("P", (Var("a"),))
    expect_failure(
        Proof((
            ProofLine(1, Ex, Premise(), 0),
            ProofLine(2, Pa, Assumption(), 1),
            ProofLine(3, Pa, RuleApp("reit", (2,)), 1),
            # conclusion Pa has 'a' free — eigenvar escapes
            ProofLine(4, Pa, RuleApp("existsE", (1,), ((2, 3),), extra={"eigenvar": "a"}), 0),
        )),
        EigenvarViolation,
    )


# ---------------------------------------------------------------------------
# MissingExtra
# ---------------------------------------------------------------------------


def test_forallE_missing_term() -> None:
    Px = ForAll("x", Atom("P", (Var("x"),)))
    expect_failure(
        Proof((
            ProofLine(1, Px, Premise(), 0),
            ProofLine(2, Atom("P", (Const(1),)), RuleApp("forallE", (1,)), 0),
        )),
        MissingExtra,
    )


def test_forallI_missing_eigenvar() -> None:
    Pa = Atom("P", (Var("a"),))
    Px = ForAll("x", Atom("P", (Var("x"),)))
    expect_failure(
        Proof((
            ProofLine(1, Pa, Assumption(), 1),
            ProofLine(2, Px, RuleApp("forallI", box_refs=((1, 1),)), 0),
        )),
        MissingExtra,
    )


def test_eqSubst_missing_template() -> None:
    eq = Equals(Var("x"), Const(0))
    expect_failure(
        Proof((
            ProofLine(1, eq, Premise(), 0),
            ProofLine(2, Atom("P", (Var("x"),)), Premise(), 0),
            ProofLine(3, Atom("P", (Const(0),)), RuleApp("eqSubst", (1, 2), extra={"var": "v"}), 0),
        )),
        MissingExtra,
    )


# ---------------------------------------------------------------------------
# GoalMismatch
# ---------------------------------------------------------------------------


def test_goal_mismatch() -> None:
    # Proof is valid but goal doesn't match final line
    proof = Proof(
        lines=(
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, And(P, Q), RuleApp("andI", (1, 2)), 0),
        ),
        goal=And(Q, P),  # wrong order
    )
    expect_failure(proof, GoalMismatch)


# ---------------------------------------------------------------------------
# existsE — eigenvar checks not covered by test_existsE_eigenvar_escapes
# ---------------------------------------------------------------------------


def test_existsE_eigenvar_free_in_existential() -> None:
    # 'a' appears free inside the existential formula itself (∃x. P(a))
    # The check at the top of _existsE fires before the conclusion check.
    Ex = Exists("x", Atom("P", (Var("a"),)))  # free_vars(Ex) = {"a"}
    Pa = Atom("P", (Var("a"),))
    expect_failure(
        Proof((
            ProofLine(1, Ex, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, Pa, Assumption(), 1),
            ProofLine(4, Q, RuleApp("reit", (2,)), 1),
            ProofLine(5, Q, RuleApp("existsE", (1,), ((3, 4),), extra={"eigenvar": "a"}), 0),
        )),
        EigenvarViolation,
    )


def test_existsE_eigenvar_in_accessible_line() -> None:
    # 'a' is free in an accessible premise before the box; ∃x. P(x) has no 'a'.
    # _existsE checks accessible lines BEFORE checking the conclusion, so even
    # though the conclusion also has 'a' free, line 558 fires first.
    Ex = Exists("x", Atom("P", (Var("x"),)))  # free_vars = {}
    Qa = Atom("Q", (Var("a"),))               # 'a' free; accessible from box
    Pa = Atom("P", (Var("a"),))
    expect_failure(
        Proof((
            ProofLine(1, Ex, Premise(), 0),
            ProofLine(2, Qa, Premise(), 0),   # 'a' free, accessible from box_start=3
            ProofLine(3, Pa, Assumption(), 1),
            ProofLine(4, Qa, RuleApp("reit", (2,)), 1),  # reit Qa correctly
            ProofLine(5, Qa, RuleApp("existsE", (1,), ((3, 4),), extra={"eigenvar": "a"}), 0),
        )),
        EigenvarViolation,
    )


# ---------------------------------------------------------------------------
# orE — box assumption mismatches
# ---------------------------------------------------------------------------


def test_orE_box1_assumption_mismatch() -> None:
    # Box 1 opens with R instead of P
    expect_failure(
        Proof((
            ProofLine(1, Or(P, Q), Premise(), 0),
            ProofLine(2, R, Premise(), 0),
            ProofLine(3, R, Assumption(), 1),        # should be P
            ProofLine(4, R, RuleApp("reit", (3,)), 1),
            ProofLine(5, Q, Assumption(), 1),
            ProofLine(6, R, RuleApp("reit", (2,)), 1),
            ProofLine(7, R, RuleApp("orE", (1,), ((3, 4), (5, 6))), 0),
        )),
        FormulaMismatch,
    )


def test_orE_box2_assumption_mismatch() -> None:
    # Box 2 opens with R instead of Q
    expect_failure(
        Proof((
            ProofLine(1, Or(P, Q), Premise(), 0),
            ProofLine(2, R, Premise(), 0),
            ProofLine(3, P, Assumption(), 1),
            ProofLine(4, R, RuleApp("reit", (2,)), 1),
            ProofLine(5, R, Assumption(), 1),        # should be Q
            ProofLine(6, R, RuleApp("reit", (2,)), 1),
            ProofLine(7, R, RuleApp("orE", (1,), ((3, 4), (5, 6))), 0),
        )),
        FormulaMismatch,
    )
