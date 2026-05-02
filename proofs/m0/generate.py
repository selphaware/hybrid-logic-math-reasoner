"""Generate the M0 example proof JSON files (prd_milestone_0.md §5, §10).

Run from repo root:
    python proofs/m0/generate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add src to path so we can import hlmr without installing
_here = Path(__file__).parent
_src = _here.parent.parent / "src"
sys.path.insert(0, str(_src))

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
from hlmr.ir.serialise import to_json
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified

P = Atom("P")
Q = Atom("Q")
R = Atom("R")

OUT = Path(__file__).parent


def save(name: str, proof: Proof, expect_valid: bool = True) -> None:
    result = check_proof(proof)
    if expect_valid:
        if not isinstance(result, Verified):
            raise RuntimeError(f"{name}: expected Verified but got {result}")
    else:
        if isinstance(result, Verified):
            raise RuntimeError(f"{name}: expected failure but got Verified")
    path = OUT / name
    path.write_text(to_json(proof), encoding="utf-8")
    status = "verified" if isinstance(result, Verified) else f"rejected ({type(result.reason).__name__})"
    print(f"  {name}: {len(proof.lines)} lines, {status}")


def main() -> None:
    print("Generating M0 example proofs...")

    # ------------------------------------------------------------------
    # 01_modus_ponens.json — P -> Q, P ⊢ Q
    # ------------------------------------------------------------------
    save("01_modus_ponens.json", Proof(
        lines=(
            ProofLine(1, Implies(P, Q), Premise(), 0),
            ProofLine(2, P, Premise(), 0),
            ProofLine(3, Q, RuleApp("impE", (1, 2)), 0),
        ),
        goal=Q,
    ))

    # ------------------------------------------------------------------
    # 02_imp_reflexive.json — ⊢ P -> P
    # ------------------------------------------------------------------
    save("02_imp_reflexive.json", Proof(
        lines=(
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("reit", (1,)), 1),
            ProofLine(3, Implies(P, P), RuleApp("impI", box_refs=((1, 2),)), 0),
        ),
        goal=Implies(P, P),
    ))

    # ------------------------------------------------------------------
    # 03_de_morgan.json — ~(P & Q) ⊢ ~P | ~Q
    # Strategy: PBC — assume ~(~P|~Q), show ⊥ via nested notI boxes
    #   [P ⊢ [Q ⊢ P&Q ⊢ ⊥] → ~Q → ~P|~Q → ⊥] → ~P → ~P|~Q → ⊥
    # ------------------------------------------------------------------
    npq = Not(And(P, Q))
    goal_03 = Or(Not(P), Not(Q))
    not_goal = Not(goal_03)
    save("03_de_morgan.json", Proof(
        lines=(
            ProofLine(1, npq, Premise(), 0),
            ProofLine(2, not_goal, Assumption(), 1),      # PBC box starts
            ProofLine(3, P, Assumption(), 2),             # notI box for ~P starts
            ProofLine(4, Q, Assumption(), 3),             # notI box for ~Q starts
            ProofLine(5, And(P, Q), RuleApp("andI", (3, 4)), 3),
            ProofLine(6, Bot(), RuleApp("notE", (5, 1)), 3),
            ProofLine(7, Not(Q), RuleApp("notI", box_refs=((4, 6),)), 2),
            ProofLine(8, goal_03, RuleApp("orI_R", (7,)), 2),
            ProofLine(9, Bot(), RuleApp("notE", (8, 2)), 2),
            ProofLine(10, Not(P), RuleApp("notI", box_refs=((3, 9),)), 1),
            ProofLine(11, goal_03, RuleApp("orI_L", (10,)), 1),
            ProofLine(12, Bot(), RuleApp("notE", (11, 2)), 1),
            ProofLine(13, goal_03, RuleApp("PBC", box_refs=((2, 12),)), 0),
        ),
        goal=goal_03,
    ))

    # ------------------------------------------------------------------
    # 04_contrapositive.json — P -> Q ⊢ ~Q -> ~P
    # ------------------------------------------------------------------
    pq = Implies(P, Q)
    goal_04 = Implies(Not(Q), Not(P))
    save("04_contrapositive.json", Proof(
        lines=(
            ProofLine(1, pq, Premise(), 0),
            ProofLine(2, Not(Q), Assumption(), 1),
            ProofLine(3, P, Assumption(), 2),
            ProofLine(4, Q, RuleApp("impE", (1, 3)), 2),
            ProofLine(5, Bot(), RuleApp("notE", (4, 2)), 2),
            ProofLine(6, Not(P), RuleApp("notI", box_refs=((3, 5),)), 1),
            ProofLine(7, goal_04, RuleApp("impI", box_refs=((2, 6),)), 0),
        ),
        goal=goal_04,
    ))

    # ------------------------------------------------------------------
    # 05_or_commutative.json — P | Q ⊢ Q | P
    # ------------------------------------------------------------------
    goal_05 = Or(Q, P)
    save("05_or_commutative.json", Proof(
        lines=(
            ProofLine(1, Or(P, Q), Premise(), 0),
            ProofLine(2, P, Assumption(), 1),
            ProofLine(3, goal_05, RuleApp("orI_R", (2,)), 1),
            ProofLine(4, Q, Assumption(), 1),
            ProofLine(5, goal_05, RuleApp("orI_L", (4,)), 1),
            ProofLine(6, goal_05, RuleApp("orE", (1,), ((2, 3), (4, 5))), 0),
        ),
        goal=goal_05,
    ))

    # ------------------------------------------------------------------
    # 06_double_negation.json — P ⊢ ~~P
    # ------------------------------------------------------------------
    goal_06 = Not(Not(P))
    save("06_double_negation.json", Proof(
        lines=(
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Not(P), Assumption(), 1),
            ProofLine(3, Bot(), RuleApp("notE", (1, 2)), 1),
            ProofLine(4, goal_06, RuleApp("notI", box_refs=((2, 3),)), 0),
        ),
        goal=goal_06,
    ))

    # ------------------------------------------------------------------
    # 07_forall_instantiate.json — forall x. P(x) ⊢ P(alice)
    # ------------------------------------------------------------------
    Px = ForAll("x", Atom("P", (Var("x"),)))
    alice = Const("alice")
    Pa = Atom("P", (alice,))
    save("07_forall_instantiate.json", Proof(
        lines=(
            ProofLine(1, Px, Premise(), 0),
            ProofLine(2, Pa, RuleApp("forallE", (1,), extra={"term": alice}), 0),
        ),
        goal=Pa,
    ))

    # ------------------------------------------------------------------
    # 08_forall_rename.json — forall x. P(x) ⊢ P(bob)
    # ------------------------------------------------------------------
    bob = Const("bob")
    Pb = Atom("P", (bob,))
    save("08_forall_rename.json", Proof(
        lines=(
            ProofLine(1, Px, Premise(), 0),
            ProofLine(2, Pb, RuleApp("forallE", (1,), extra={"term": bob}), 0),
        ),
        goal=Pb,
    ))

    # ------------------------------------------------------------------
    # 09_exists_elim.json — exists x. P(x), [P(a) ⊢ Q] ⊢ Q
    # ------------------------------------------------------------------
    Ex = Exists("x", Atom("P", (Var("x"),)))
    Pa2 = Atom("P", (Var("a"),))
    save("09_exists_elim.json", Proof(
        lines=(
            ProofLine(1, Ex, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, Pa2, Assumption(), 1),
            ProofLine(4, Q, RuleApp("reit", (2,)), 1),
            ProofLine(5, Q, RuleApp("existsE", (1,), ((3, 4),), extra={"eigenvar": "a"}), 0),
        ),
        goal=Q,
    ))

    # ------------------------------------------------------------------
    # 10_eq_subst.json — x=y, P(x) ⊢ P(y)
    # ------------------------------------------------------------------
    x, y = Var("x"), Var("y")
    eq_xy = Equals(x, y)
    Px2 = Atom("P", (x,))
    Py = Atom("P", (y,))
    template = Atom("P", (Var("v"),))
    save("10_eq_subst.json", Proof(
        lines=(
            ProofLine(1, eq_xy, Premise(), 0),
            ProofLine(2, Px2, Premise(), 0),
            ProofLine(3, Py, RuleApp("eqSubst", (1, 2), extra={"var": "v", "template": template}), 0),
        ),
        goal=Py,
    ))

    # ------------------------------------------------------------------
    # 11_eq_transitive.json — x=y, y=z ⊢ x=z
    # ------------------------------------------------------------------
    z = Var("z")
    eq_yz = Equals(y, z)
    eq_xz = Equals(x, z)
    template2 = Equals(x, Var("v"))
    save("11_eq_transitive.json", Proof(
        lines=(
            ProofLine(1, eq_xy, Premise(), 0),
            ProofLine(2, eq_yz, Premise(), 0),
            ProofLine(3, eq_xz, RuleApp("eqSubst", (2, 1), extra={"var": "v", "template": template2}), 0),
        ),
        goal=eq_xz,
    ))

    # ------------------------------------------------------------------
    # 12_ex_falso.json — ⊥ ⊢ P
    # ------------------------------------------------------------------
    save("12_ex_falso.json", Proof(
        lines=(
            ProofLine(1, Bot(), Premise(), 0),
            ProofLine(2, P, RuleApp("botE", (1,)), 0),
        ),
        goal=P,
    ))

    # ------------------------------------------------------------------
    # 99_BAD_andI.json — Must FAIL with FormulaMismatch
    # andI(P, Q) but conclusion is And(Q, P) — wrong order
    # ------------------------------------------------------------------
    save("99_BAD_andI.json", Proof(
        lines=(
            ProofLine(1, P, Premise(), 0),
            ProofLine(2, Q, Premise(), 0),
            ProofLine(3, And(Q, P), RuleApp("andI", (1, 2)), 0),
        ),
    ), expect_valid=False)

    # ------------------------------------------------------------------
    # 99_BAD_oos.json — Must FAIL with OutOfScope
    # Reference into discharged box
    # ------------------------------------------------------------------
    save("99_BAD_oos.json", Proof(
        lines=(
            ProofLine(1, P, Assumption(), 1),
            ProofLine(2, P, RuleApp("reit", (1,)), 1),
            ProofLine(3, Implies(P, P), RuleApp("impI", box_refs=((1, 2),)), 0),
            ProofLine(4, P, RuleApp("reit", (1,)), 0),
        ),
    ), expect_valid=False)

    # ------------------------------------------------------------------
    # 99_BAD_eigenvar.json — Must FAIL with EigenvarViolation
    # eigenvar 'a' appears free in premise P(a)
    # ------------------------------------------------------------------
    Pa3 = Atom("P", (Var("a"),))
    Fa = ForAll("x", Atom("P", (Var("x"),)))
    save("99_BAD_eigenvar.json", Proof(
        lines=(
            ProofLine(1, Pa3, Premise(), 0),
            ProofLine(2, Pa3, Assumption(), 1),
            ProofLine(3, Fa, RuleApp("forallI", box_refs=((2, 2),), extra={"eigenvar": "a"}), 0),
        ),
    ), expect_valid=False)

    print(f"\nDone. Written to {OUT}/")


if __name__ == "__main__":
    main()
