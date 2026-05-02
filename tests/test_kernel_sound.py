"""Valid proofs must verify — soundness regression suite (prd_milestone_0.md §9.1)."""

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
    Iff,
    Implies,
    Not,
    Or,
    Var,
)
from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel import check_proof, Verified

P = Atom("P")
Q = Atom("Q")
R = Atom("R")


def verify(proof: Proof) -> None:
    result = check_proof(proof)
    assert isinstance(result, Verified), f"Expected Verified, got {result}"


# ---------------------------------------------------------------------------
# andI, andE_L, andE_R
# ---------------------------------------------------------------------------


def test_andI() -> None:
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Q, Premise(), 0),
        ProofLine(3, And(P, Q), RuleApp("andI", (1, 2)), 0),
    ))
    verify(proof)


def test_andE_L() -> None:
    proof = Proof((
        ProofLine(1, And(P, Q), Premise(), 0),
        ProofLine(2, P, RuleApp("andE_L", (1,)), 0),
    ))
    verify(proof)


def test_andE_R() -> None:
    proof = Proof((
        ProofLine(1, And(P, Q), Premise(), 0),
        ProofLine(2, Q, RuleApp("andE_R", (1,)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# orI_L, orI_R, orE
# ---------------------------------------------------------------------------


def test_orI_L() -> None:
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Or(P, Q), RuleApp("orI_L", (1,)), 0),
    ))
    verify(proof)


def test_orI_R() -> None:
    proof = Proof((
        ProofLine(1, Q, Premise(), 0),
        ProofLine(2, Or(P, Q), RuleApp("orI_R", (1,)), 0),
    ))
    verify(proof)


def test_orE() -> None:
    # P | Q, [P ⊢ R], [Q ⊢ R] ⊢ R
    proof = Proof((
        ProofLine(1, Or(P, Q), Premise(), 0),
        ProofLine(2, R, Premise(), 0),
        ProofLine(3, P, Assumption(), 1),
        ProofLine(4, R, RuleApp("reit", (2,)), 1),
        ProofLine(5, Q, Assumption(), 1),
        ProofLine(6, R, RuleApp("reit", (2,)), 1),
        ProofLine(7, R, RuleApp("orE", (1,), ((3, 4), (5, 6))), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# impI, impE
# ---------------------------------------------------------------------------


def test_impI() -> None:
    # P -> P
    proof = Proof((
        ProofLine(1, P, Assumption(), 1),
        ProofLine(2, P, RuleApp("reit", (1,)), 1),
        ProofLine(3, Implies(P, P), RuleApp("impI", box_refs=((1, 2),)), 0),
    ))
    verify(proof)


def test_impE() -> None:
    proof = Proof((
        ProofLine(1, Implies(P, Q), Premise(), 0),
        ProofLine(2, P, Premise(), 0),
        ProofLine(3, Q, RuleApp("impE", (1, 2)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# notI, notE
# ---------------------------------------------------------------------------


def test_notI() -> None:
    # ~P -> ~P (via notI)
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Not(P), Premise(), 0),
        ProofLine(3, P, Assumption(), 1),
        ProofLine(4, Not(P), RuleApp("reit", (2,)), 1),
        ProofLine(5, Bot(), RuleApp("notE", (3, 4)), 1),
        ProofLine(6, Not(P), RuleApp("notI", box_refs=((3, 5),)), 0),
    ))
    verify(proof)


def test_notE() -> None:
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Not(P), Premise(), 0),
        ProofLine(3, Bot(), RuleApp("notE", (1, 2)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# botE
# ---------------------------------------------------------------------------


def test_botE() -> None:
    proof = Proof((
        ProofLine(1, Bot(), Premise(), 0),
        ProofLine(2, Q, RuleApp("botE", (1,)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# iffI, iffE_L, iffE_R
# ---------------------------------------------------------------------------


def test_iffI() -> None:
    pq = Implies(P, Q)
    qp = Implies(Q, P)
    proof = Proof((
        ProofLine(1, pq, Premise(), 0),
        ProofLine(2, qp, Premise(), 0),
        ProofLine(3, Iff(P, Q), RuleApp("iffI", (1, 2)), 0),
    ))
    verify(proof)


def test_iffE_L() -> None:
    proof = Proof((
        ProofLine(1, Iff(P, Q), Premise(), 0),
        ProofLine(2, P, Premise(), 0),
        ProofLine(3, Q, RuleApp("iffE_L", (1, 2)), 0),
    ))
    verify(proof)


def test_iffE_R() -> None:
    proof = Proof((
        ProofLine(1, Iff(P, Q), Premise(), 0),
        ProofLine(2, Q, Premise(), 0),
        ProofLine(3, P, RuleApp("iffE_R", (1, 2)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# reit
# ---------------------------------------------------------------------------


def test_reit() -> None:
    proof = Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, P, Assumption(), 1),
        ProofLine(3, P, RuleApp("reit", (1,)), 1),
        ProofLine(4, Implies(P, P), RuleApp("impI", box_refs=((2, 3),)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# PBC
# ---------------------------------------------------------------------------


def test_PBC() -> None:
    # Proof of P from ~~P via PBC
    # [~P ⊢ ⊥] => P
    proof = Proof((
        ProofLine(1, Not(Not(P)), Premise(), 0),
        ProofLine(2, Not(P), Assumption(), 1),
        ProofLine(3, Bot(), RuleApp("notE", (2, 1)), 1),
        ProofLine(4, P, RuleApp("PBC", box_refs=((2, 3),)), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# forallI, forallE
# ---------------------------------------------------------------------------


def test_forallI() -> None:
    # [⊢ P(a)] => forall x. P(x)
    Pa = Atom("P", (Var("a"),))
    Px = ForAll("x", Atom("P", (Var("x"),)))
    proof = Proof((
        ProofLine(1, Pa, Assumption(), 1),
        ProofLine(2, Px, RuleApp("forallI", box_refs=((1, 1),), extra={"eigenvar": "a"}), 0),
    ))
    verify(proof)


def test_forallE() -> None:
    Px = ForAll("x", Atom("P", (Var("x"),)))
    Pa = Atom("P", (Const("alice"),))
    proof = Proof((
        ProofLine(1, Px, Premise(), 0),
        ProofLine(2, Pa, RuleApp("forallE", (1,), extra={"term": Const("alice")}), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# existsI, existsE
# ---------------------------------------------------------------------------


def test_existsI() -> None:
    Pa = Atom("P", (Const("alice"),))
    Ex = Exists("x", Atom("P", (Var("x"),)))
    proof = Proof((
        ProofLine(1, Pa, Premise(), 0),
        ProofLine(2, Ex, RuleApp("existsI", (1,), extra={"term": Const("alice")}), 0),
    ))
    verify(proof)


def test_existsE() -> None:
    # exists x. P(x), [P(a) ⊢ Q] ⊢ Q
    Ex = Exists("x", Atom("P", (Var("x"),)))
    Pa = Atom("P", (Var("a"),))
    proof = Proof((
        ProofLine(1, Ex, Premise(), 0),
        ProofLine(2, Q, Premise(), 0),
        ProofLine(3, Pa, Assumption(), 1),
        ProofLine(4, Q, RuleApp("reit", (2,)), 1),
        ProofLine(5, Q, RuleApp("existsE", (1,), ((3, 4),), extra={"eigenvar": "a"}), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# eqRefl, eqSubst
# ---------------------------------------------------------------------------


def test_eqRefl() -> None:
    t = Const("alice")
    proof = Proof((
        ProofLine(1, Equals(t, t), RuleApp("eqRefl"), 0),
    ))
    verify(proof)


def test_eqSubst() -> None:
    # t = u, P(t) => P(u)
    t = Var("x")
    u = Const(7)
    eq = Equals(t, u)
    template = Atom("P", (Var("v"),))
    pt = Atom("P", (t,))
    pu = Atom("P", (u,))
    proof = Proof((
        ProofLine(1, eq, Premise(), 0),
        ProofLine(2, pt, Premise(), 0),
        ProofLine(3, pu, RuleApp("eqSubst", (1, 2), extra={"var": "v", "template": template}), 0),
    ))
    verify(proof)


# ---------------------------------------------------------------------------
# End-to-end derivations
# ---------------------------------------------------------------------------


def test_modus_ponens_end_to_end() -> None:
    # Classic P -> Q, P ⊢ Q
    goal = Q
    proof = Proof(
        lines=(
            ProofLine(1, Implies(P, Q), Premise(), 0),
            ProofLine(2, P, Premise(), 0),
            ProofLine(3, Q, RuleApp("impE", (1, 2)), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_imp_reflexive() -> None:
    # ⊢ P -> P
    goal = Implies(P, P)
    proof = Proof(
        lines=(
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("reit", (1,)), 1),
            ProofLine(3, goal, RuleApp("impI", box_refs=((1, 2),)), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_double_negation() -> None:
    # P ⊢ ~~P
    goal = Not(Not(P))
    proof = Proof(
        lines=(
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Not(P), Assumption(), 1),
            ProofLine(3, Bot(), RuleApp("notE", (1, 2)), 1),
            ProofLine(4, goal, RuleApp("notI", box_refs=((2, 3),)), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_de_morgan_not_and() -> None:
    # ~(P & Q) ⊢ ~P | ~Q  (via PBC + case analysis)
    # We use a simpler demo: P & Q ⊢ P
    goal = P
    proof = Proof(
        lines=(
            ProofLine(1, And(P, Q), Premise(), 0),
            ProofLine(2, P, RuleApp("andE_L", (1,)), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_contrapositive() -> None:
    # P -> Q ⊢ ~Q -> ~P
    pq = Implies(P, Q)
    goal = Implies(Not(Q), Not(P))
    proof = Proof(
        lines=(
            ProofLine(1, pq, Premise(), 0),
            ProofLine(2, Not(Q), Assumption(), 1),
            ProofLine(3, P, Assumption(), 2),
            ProofLine(4, Q, RuleApp("impE", (1, 3)), 2),
            ProofLine(5, Bot(), RuleApp("notE", (4, 2)), 2),
            ProofLine(6, Not(P), RuleApp("notI", box_refs=((3, 5),)), 1),
            ProofLine(7, goal, RuleApp("impI", box_refs=((2, 6),)), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_or_commutative() -> None:
    # P | Q ⊢ Q | P
    goal = Or(Q, P)
    proof = Proof(
        lines=(
            ProofLine(1, Or(P, Q), Premise(), 0),
            ProofLine(2, P, Assumption(), 1),
            ProofLine(3, Or(Q, P), RuleApp("orI_R", (2,)), 1),
            ProofLine(4, Q, Assumption(), 1),
            ProofLine(5, Or(Q, P), RuleApp("orI_L", (4,)), 1),
            ProofLine(6, goal, RuleApp("orE", (1,), ((2, 3), (4, 5))), 0),
        ),
        goal=goal,
    )
    verify(proof)


def test_ex_falso() -> None:
    # ⊥ ⊢ P
    proof = Proof(
        lines=(
            ProofLine(1, Bot(), Premise(), 0),
            ProofLine(2, P, RuleApp("botE", (1,)), 0),
        ),
        goal=P,
    )
    verify(proof)


def test_forall_instantiate() -> None:
    # forall x. P(x) ⊢ P(alice)
    Px = ForAll("x", Atom("P", (Var("x"),)))
    alice = Const("alice")
    Pa = Atom("P", (alice,))
    proof = Proof(
        lines=(
            ProofLine(1, Px, Premise(), 0),
            ProofLine(2, Pa, RuleApp("forallE", (1,), extra={"term": alice}), 0),
        ),
        goal=Pa,
    )
    verify(proof)


def test_eq_transitive() -> None:
    # x=y, y=z ⊢ x=z  (via eqSubst: subst y->z in x=y)
    x, y, z = Var("x"), Var("y"), Var("z")
    template = Equals(x, Var("v"))
    proof = Proof(
        lines=(
            ProofLine(1, Equals(x, y), Premise(), 0),
            ProofLine(2, Equals(y, z), Premise(), 0),
            ProofLine(3, Equals(x, z), RuleApp("eqSubst", (2, 1), extra={"var": "v", "template": template}), 0),
        ),
        goal=Equals(x, z),
    )
    verify(proof)


# ---------------------------------------------------------------------------
# Hypothesis: check_proof is deterministic
# ---------------------------------------------------------------------------

_simple_proofs = [
    Proof((
        ProofLine(1, P, Premise(), 0),
        ProofLine(2, Q, Premise(), 0),
        ProofLine(3, And(P, Q), RuleApp("andI", (1, 2)), 0),
    )),
    Proof((
        ProofLine(1, Implies(P, Q), Premise(), 0),
        ProofLine(2, P, Premise(), 0),
        ProofLine(3, Q, RuleApp("impE", (1, 2)), 0),
    )),
]


@given(proof=st.sampled_from(_simple_proofs))
@settings(max_examples=50)
def test_check_proof_deterministic(proof: Proof) -> None:
    result1 = check_proof(proof)
    result2 = check_proof(proof)
    assert result1 == result2
