"""Kernel rejects proofs containing unresolved Meta terms (M1 §5.3).

UnresolvedMeta is a defence-in-depth check: even if the renderer produces
a structurally-complete proof, any line whose formula still contains a
Meta triggers immediate rejection before any rule dispatch.
"""

from __future__ import annotations

from hlmr.ir.formula import Atom, Const, ForAll, Func, Meta, Var
from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel import check_proof
from hlmr.kernel.errors import (
    CheckFailure,
    UnresolvedMeta,
    Verified,
)

# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

P = Atom("P")
Q = Atom("Q")


def _assert_unresolved(proof: Proof, line: int, meta_name: str) -> None:
    result = check_proof(proof)
    assert isinstance(result, CheckFailure), f"Expected CheckFailure, got {result}"
    assert isinstance(result.reason, UnresolvedMeta), (
        f"Expected UnresolvedMeta, got {type(result.reason).__name__}: {result.reason}"
    )
    assert result.line == line, f"Expected error at line {line}, got {result.line}"
    assert result.reason.line == line
    assert result.reason.meta_name == meta_name


# ---------------------------------------------------------------------------
# Meta in various formula positions
# ---------------------------------------------------------------------------


def test_meta_directly_in_atom_arg() -> None:
    # Atom("p", (Meta("?X"),)) as a Premise
    proof = Proof((
        ProofLine(1, Atom("p", (Meta("?X"),)), Premise(), 0),
    ))
    _assert_unresolved(proof, 1, "?X")


def test_meta_nested_in_func_in_atom() -> None:
    # Meta inside Func inside Atom arg
    proof = Proof((
        ProofLine(1, Atom("p", (Func("f", (Meta("?Y"),)),)), Premise(), 0),
    ))
    _assert_unresolved(proof, 1, "?Y")


def test_meta_inside_forall_body() -> None:
    # Meta inside a quantifier body
    proof = Proof((
        ProofLine(1, ForAll("x", Atom("p", (Meta("?Z"), Var("x")))), Premise(), 0),
    ))
    _assert_unresolved(proof, 1, "?Z")


def test_meta_on_second_line_reports_correct_line() -> None:
    # First line is clean; Meta appears on line 2
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Atom("q", (Meta("?X"),)), Premise(), 0),
    ))
    _assert_unresolved(proof, 2, "?X")


def test_meta_first_line_reported_before_later_meta() -> None:
    # Both lines have Meta; the first one is reported
    proof = Proof((
        ProofLine(1, Atom("p", (Meta("?A"),)), Premise(), 0),
        ProofLine(2, Atom("q", (Meta("?B"),)), Premise(), 0),
    ))
    _assert_unresolved(proof, 1, "?A")


# ---------------------------------------------------------------------------
# Negative control: Meta-free proofs still verify
# ---------------------------------------------------------------------------


def test_meta_free_premise_verifies() -> None:
    # A single Premise with no Meta should verify normally
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
    ))
    result = check_proof(proof)
    assert isinstance(result, Verified), f"Expected Verified, got {result}"


def test_meta_free_two_line_proof_verifies() -> None:
    # Premise + andI (ground terms only)
    from hlmr.ir.formula import And
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Q, Premise(), 0),
        ProofLine(3, And(P, Q), RuleApp("andI", (1, 2)), 0),
    ))
    result = check_proof(proof)
    assert isinstance(result, Verified), f"Expected Verified, got {result}"


def test_meta_free_ground_const_proof_verifies() -> None:
    # Atom with Const args — no Meta anywhere
    f = Atom("human", (Const("socrates"),))
    proof = Proof((
        ProofLine(1, f, Premise(), 0),
    ))
    result = check_proof(proof)
    assert isinstance(result, Verified), f"Expected Verified, got {result}"


# ---------------------------------------------------------------------------
# UnresolvedMeta fires before rule-application errors
# ---------------------------------------------------------------------------


def test_unresolved_meta_before_rule_error() -> None:
    # Line 1: Premise with Meta (triggers UnresolvedMeta).
    # Line 2: andE1 applied to line 1, which isn't an And (would trigger
    #          WrongFormulaShape if we got that far).
    # The kernel must return UnresolvedMeta, not the rule error.
    proof = Proof((
        ProofLine(1, Atom("p", (Meta("?X"),)), Premise(), 0),
        ProofLine(2, Atom("p", (Meta("?X"),)), RuleApp("andE1", (1,)), 0),
    ))
    result = check_proof(proof)
    assert isinstance(result, CheckFailure)
    assert isinstance(result.reason, UnresolvedMeta)
    assert result.line == 1


def test_unresolved_meta_before_structural_error() -> None:
    # Line 1 has Meta; line 2 has wrong sequential number (structural error).
    # UnresolvedMeta should still fire first because the Meta guard runs
    # before the structural sanity pass.
    #
    # We build the Proof tuple directly to bypass normal construction and
    # plant both defects simultaneously.
    proof = Proof((
        ProofLine(1, Atom("p", (Meta("?Q"),)), Premise(), 0),
        ProofLine(99, Q, Premise(), 0),  # wrong line number — structural error
    ))
    result = check_proof(proof)
    assert isinstance(result, CheckFailure)
    assert isinstance(result.reason, UnresolvedMeta)
    assert result.line == 1
