"""22 ND rule checkers and the RULES dispatch dict.

Each checker receives (conclusion_line, proof) and returns None on success
or a RuleError subtype on failure. The line has already been validated for
structural well-formedness by check_proof before a rule checker is called.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Callable

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
    Meta,
    Not,
    Or,
    Term,
    Var,
    free_vars,
    subst,
)
from hlmr.ir.justification import RuleApp
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel.errors import (
    BadBoxRef,
    EigenvarViolation,
    EvaluationFalse,
    FormulaMismatch,
    MalformedArithmetic,
    MissingExtra,
    OutOfScope,
    RuleError,
    WrongFormulaShape,
    WrongRefCount,
)
from hlmr.kernel.scope import is_accessible, is_box

# Type alias for a rule checker function
RuleChecker = Callable[[ProofLine, Proof], RuleError | None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_refs(
    line: ProofLine,
    proof: Proof,
    expected_lines: int,
    expected_boxes: int,
) -> RuleError | None:
    app = line.justification
    assert isinstance(app, RuleApp)
    if len(app.line_refs) != expected_lines or len(app.box_refs) != expected_boxes:
        return WrongRefCount(
            app.rule,
            expected_lines,
            len(app.line_refs),
            expected_boxes,
            len(app.box_refs),
        )
    return None


def _check_accessible(line: ProofLine, proof: Proof, ref: int) -> RuleError | None:
    app = line.justification
    assert isinstance(app, RuleApp)
    if not is_accessible(ref, line.number, proof):
        return OutOfScope(app.rule, ref, line.number)
    return None


def _check_box(
    line: ProofLine, proof: Proof, start: int, end: int
) -> RuleError | None:
    app = line.justification
    assert isinstance(app, RuleApp)
    ok, reason = is_box(start, end, proof, line.number)
    if not ok:
        return BadBoxRef(app.rule, start, end, reason)
    return None


def _require_extra(line: ProofLine, key: str) -> RuleError | None:
    app = line.justification
    assert isinstance(app, RuleApp)
    if key not in app.extra:
        return MissingExtra(app.rule, key)
    return None


# ---------------------------------------------------------------------------
# Propositional rules (16)
# ---------------------------------------------------------------------------


def _andI(line: ProofLine, proof: Proof) -> RuleError | None:
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    l_ref, r_ref = app.line_refs
    if err := _check_accessible(line, proof, l_ref):
        return err
    if err := _check_accessible(line, proof, r_ref):
        return err
    p = proof.line(l_ref).formula
    q = proof.line(r_ref).formula
    if line.formula != And(p, q):
        return FormulaMismatch("andI", And(p, q), line.formula)
    return None


def _andE_L(line: ProofLine, proof: Proof) -> RuleError | None:
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    f = proof.line(ref).formula
    if not isinstance(f, And):
        return WrongFormulaShape("andE_L", ref, "And(P, Q)")
    if line.formula != f.left:
        return FormulaMismatch("andE_L", f.left, line.formula)
    return None


def _andE_R(line: ProofLine, proof: Proof) -> RuleError | None:
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    f = proof.line(ref).formula
    if not isinstance(f, And):
        return WrongFormulaShape("andE_R", ref, "And(P, Q)")
    if line.formula != f.right:
        return FormulaMismatch("andE_R", f.right, line.formula)
    return None


def _orI_L(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P derive P | Q (Q is taken from the conclusion)."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    if not isinstance(line.formula, Or):
        return WrongFormulaShape("orI_L", line.number, "Or(P, Q)")
    if line.formula.left != proof.line(ref).formula:
        return FormulaMismatch("orI_L", proof.line(ref).formula, line.formula.left)
    return None


def _orI_R(line: ProofLine, proof: Proof) -> RuleError | None:
    """From Q derive P | Q (P is taken from the conclusion)."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    if not isinstance(line.formula, Or):
        return WrongFormulaShape("orI_R", line.number, "Or(P, Q)")
    if line.formula.right != proof.line(ref).formula:
        return FormulaMismatch("orI_R", proof.line(ref).formula, line.formula.right)
    return None


def _orE(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P|Q, box [P ⊢ R], box [Q ⊢ R] derive R."""
    if err := _check_refs(line, proof, 1, 2):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (disj_ref,) = app.line_refs
    (box1_start, box1_end), (box2_start, box2_end) = app.box_refs
    if err := _check_accessible(line, proof, disj_ref):
        return err
    if err := _check_box(line, proof, box1_start, box1_end):
        return err
    if err := _check_box(line, proof, box2_start, box2_end):
        return err
    disj = proof.line(disj_ref).formula
    if not isinstance(disj, Or):
        return WrongFormulaShape("orE", disj_ref, "Or(P, Q)")
    p, q = disj.left, disj.right
    # Box 1 assumption must be P
    box1_assumption = proof.line(box1_start).formula
    if box1_assumption != p:
        return FormulaMismatch("orE", p, box1_assumption)
    # Box 2 assumption must be Q
    box2_assumption = proof.line(box2_start).formula
    if box2_assumption != q:
        return FormulaMismatch("orE", q, box2_assumption)
    # Both box conclusions must equal the overall conclusion R
    r = line.formula
    box1_conclusion = proof.line(box1_end).formula
    if box1_conclusion != r:
        return FormulaMismatch("orE", r, box1_conclusion)
    box2_conclusion = proof.line(box2_end).formula
    if box2_conclusion != r:
        return FormulaMismatch("orE", r, box2_conclusion)
    return None


def _impI(line: ProofLine, proof: Proof) -> RuleError | None:
    """From box [P ⊢ Q] derive P -> Q."""
    if err := _check_refs(line, proof, 0, 1):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (box_start, box_end) = app.box_refs[0]
    if err := _check_box(line, proof, box_start, box_end):
        return err
    if not isinstance(line.formula, Implies):
        return WrongFormulaShape("impI", line.number, "Implies(P, Q)")
    p = line.formula.left
    q = line.formula.right
    box_assumption = proof.line(box_start).formula
    if box_assumption != p:
        return FormulaMismatch("impI", p, box_assumption)
    box_conclusion = proof.line(box_end).formula
    if box_conclusion != q:
        return FormulaMismatch("impI", q, box_conclusion)
    return None


def _impE(line: ProofLine, proof: Proof) -> RuleError | None:
    """Modus ponens: from P -> Q and P derive Q."""
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    imp_ref, p_ref = app.line_refs
    if err := _check_accessible(line, proof, imp_ref):
        return err
    if err := _check_accessible(line, proof, p_ref):
        return err
    imp = proof.line(imp_ref).formula
    if not isinstance(imp, Implies):
        return WrongFormulaShape("impE", imp_ref, "Implies(P, Q)")
    p_given = proof.line(p_ref).formula
    if p_given != imp.left:
        return FormulaMismatch("impE", imp.left, p_given)
    if line.formula != imp.right:
        return FormulaMismatch("impE", imp.right, line.formula)
    return None


def _notI(line: ProofLine, proof: Proof) -> RuleError | None:
    """From box [P ⊢ ⊥] derive ~P."""
    if err := _check_refs(line, proof, 0, 1):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (box_start, box_end) = app.box_refs[0]
    if err := _check_box(line, proof, box_start, box_end):
        return err
    if not isinstance(line.formula, Not):
        return WrongFormulaShape("notI", line.number, "Not(P)")
    p = line.formula.body
    box_assumption = proof.line(box_start).formula
    if box_assumption != p:
        return FormulaMismatch("notI", p, box_assumption)
    box_conclusion = proof.line(box_end).formula
    if box_conclusion != Bot():
        return FormulaMismatch("notI", Bot(), box_conclusion)
    return None


def _notE(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P and ~P derive ⊥."""
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    p_ref, notp_ref = app.line_refs
    if err := _check_accessible(line, proof, p_ref):
        return err
    if err := _check_accessible(line, proof, notp_ref):
        return err
    p = proof.line(p_ref).formula
    notp = proof.line(notp_ref).formula
    if not isinstance(notp, Not):
        return WrongFormulaShape("notE", notp_ref, "Not(P)")
    if notp.body != p:
        return FormulaMismatch("notE", p, notp.body)
    if line.formula != Bot():
        return FormulaMismatch("notE", Bot(), line.formula)
    return None


def _botE(line: ProofLine, proof: Proof) -> RuleError | None:
    """From ⊥ derive any conclusion."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    if proof.line(ref).formula != Bot():
        return WrongFormulaShape("botE", ref, "Bot()")
    return None


def _iffI(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P -> Q and Q -> P derive P <-> Q."""
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    lr_ref, rl_ref = app.line_refs
    if err := _check_accessible(line, proof, lr_ref):
        return err
    if err := _check_accessible(line, proof, rl_ref):
        return err
    lr = proof.line(lr_ref).formula
    rl = proof.line(rl_ref).formula
    if not isinstance(lr, Implies):
        return WrongFormulaShape("iffI", lr_ref, "Implies(P, Q)")
    if not isinstance(rl, Implies):
        return WrongFormulaShape("iffI", rl_ref, "Implies(Q, P)")
    if not isinstance(line.formula, Iff):
        return WrongFormulaShape("iffI", line.number, "Iff(P, Q)")
    expected = Iff(lr.left, lr.right)
    if line.formula != expected:
        return FormulaMismatch("iffI", expected, line.formula)
    if rl.left != lr.right or rl.right != lr.left:
        return FormulaMismatch("iffI", Implies(lr.right, lr.left), rl)
    return None


def _iffE_L(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P <-> Q and P derive Q."""
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    iff_ref, p_ref = app.line_refs
    if err := _check_accessible(line, proof, iff_ref):
        return err
    if err := _check_accessible(line, proof, p_ref):
        return err
    iff = proof.line(iff_ref).formula
    if not isinstance(iff, Iff):
        return WrongFormulaShape("iffE_L", iff_ref, "Iff(P, Q)")
    p_given = proof.line(p_ref).formula
    if p_given != iff.left:
        return FormulaMismatch("iffE_L", iff.left, p_given)
    if line.formula != iff.right:
        return FormulaMismatch("iffE_L", iff.right, line.formula)
    return None


def _iffE_R(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P <-> Q and Q derive P."""
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    iff_ref, q_ref = app.line_refs
    if err := _check_accessible(line, proof, iff_ref):
        return err
    if err := _check_accessible(line, proof, q_ref):
        return err
    iff = proof.line(iff_ref).formula
    if not isinstance(iff, Iff):
        return WrongFormulaShape("iffE_R", iff_ref, "Iff(P, Q)")
    q_given = proof.line(q_ref).formula
    if q_given != iff.right:
        return FormulaMismatch("iffE_R", iff.right, q_given)
    if line.formula != iff.left:
        return FormulaMismatch("iffE_R", iff.left, line.formula)
    return None


def _reit(line: ProofLine, proof: Proof) -> RuleError | None:
    """Reiterate a line from an enclosing scope."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    src = proof.line(ref).formula
    if line.formula != src:
        return FormulaMismatch("reit", src, line.formula)
    return None


def _PBC(line: ProofLine, proof: Proof) -> RuleError | None:
    """Classical: from box [~P ⊢ ⊥] derive P."""
    if err := _check_refs(line, proof, 0, 1):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    (box_start, box_end) = app.box_refs[0]
    if err := _check_box(line, proof, box_start, box_end):
        return err
    box_assumption = proof.line(box_start).formula
    if not isinstance(box_assumption, Not):
        return WrongFormulaShape("PBC", box_start, "Not(P)")
    p = box_assumption.body
    if line.formula != p:
        return FormulaMismatch("PBC", p, line.formula)
    box_conclusion = proof.line(box_end).formula
    if box_conclusion != Bot():
        return FormulaMismatch("PBC", Bot(), box_conclusion)
    return None


# ---------------------------------------------------------------------------
# First-order rules (4)
# ---------------------------------------------------------------------------


def _forallI(line: ProofLine, proof: Proof) -> RuleError | None:
    """From box [⊢ P[a/x]] derive forall x. P.

    Eigenvariable a must not appear free in any accessible line before the box,
    and must not appear free in the body P of the universal.
    """
    if err := _check_refs(line, proof, 0, 1):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    if err := _require_extra(line, "eigenvar"):
        return err
    (box_start, box_end) = app.box_refs[0]
    if err := _check_box(line, proof, box_start, box_end):
        return err
    if not isinstance(line.formula, ForAll):
        return WrongFormulaShape("forallI", line.number, "ForAll(x, P)")
    x = line.formula.var
    body = line.formula.body
    eigenvar = app.extra["eigenvar"]

    # eigenvar must not appear free in body of the universal
    if eigenvar in free_vars(body):
        return EigenvarViolation(
            "forallI",
            eigenvar,
            f"eigenvar '{eigenvar}' appears free in body of forall",
        )
    # eigenvar must not appear free in any accessible line before the box
    for k in range(1, box_start):
        if is_accessible(k, box_start, proof):
            if eigenvar in free_vars(proof.line(k).formula):
                return EigenvarViolation(
                    "forallI",
                    eigenvar,
                    f"eigenvar '{eigenvar}' appears free in accessible line {k}",
                )
    # The box conclusion must equal P[eigenvar/x]
    expected_conclusion = subst(body, x, Var(eigenvar))
    actual_conclusion = proof.line(box_end).formula
    if actual_conclusion != expected_conclusion:
        return FormulaMismatch("forallI", expected_conclusion, actual_conclusion)
    return None


def _forallE(line: ProofLine, proof: Proof) -> RuleError | None:
    """From forall x. P derive P[t/x]."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    if err := _require_extra(line, "term"):
        return err
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    f = proof.line(ref).formula
    if not isinstance(f, ForAll):
        return WrongFormulaShape("forallE", ref, "ForAll(x, P)")
    t = app.extra["term"]
    expected = subst(f.body, f.var, t)
    if line.formula != expected:
        return FormulaMismatch("forallE", expected, line.formula)
    return None


def _existsI(line: ProofLine, proof: Proof) -> RuleError | None:
    """From P[t/x] derive exists x. P."""
    if err := _check_refs(line, proof, 1, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    if err := _require_extra(line, "term"):
        return err
    (ref,) = app.line_refs
    if err := _check_accessible(line, proof, ref):
        return err
    if not isinstance(line.formula, Exists):
        return WrongFormulaShape("existsI", line.number, "Exists(x, P)")
    x = line.formula.var
    body = line.formula.body
    t = app.extra["term"]
    expected_witness = subst(body, x, t)
    p_tx = proof.line(ref).formula
    if p_tx != expected_witness:
        return FormulaMismatch("existsI", expected_witness, p_tx)
    return None


def _existsE(line: ProofLine, proof: Proof) -> RuleError | None:
    """From exists x. P and box [P[a/x] ⊢ Q] derive Q.

    Eigenvariable a must not appear free in:
    - the existential being eliminated
    - any accessible line before the box
    - the conclusion Q (eigenvar cannot escape its scope)
    """
    if err := _check_refs(line, proof, 1, 1):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    if err := _require_extra(line, "eigenvar"):
        return err
    (exists_ref,) = app.line_refs
    (box_start, box_end) = app.box_refs[0]
    if err := _check_accessible(line, proof, exists_ref):
        return err
    if err := _check_box(line, proof, box_start, box_end):
        return err
    exists_f = proof.line(exists_ref).formula
    if not isinstance(exists_f, Exists):
        return WrongFormulaShape("existsE", exists_ref, "Exists(x, P)")
    x = exists_f.var
    body = exists_f.body
    eigenvar = app.extra["eigenvar"]

    # eigenvar must not appear free in the existential
    if eigenvar in free_vars(exists_f):
        return EigenvarViolation(
            "existsE",
            eigenvar,
            f"eigenvar '{eigenvar}' appears free in existential formula",
        )
    # eigenvar must not appear free in any accessible line before the box
    for k in range(1, box_start):
        if is_accessible(k, box_start, proof):
            if eigenvar in free_vars(proof.line(k).formula):
                return EigenvarViolation(
                    "existsE",
                    eigenvar,
                    f"eigenvar '{eigenvar}' appears free in accessible line {k}",
                )
    # eigenvar must not appear free in the conclusion Q
    q = line.formula
    if eigenvar in free_vars(q):
        return EigenvarViolation(
            "existsE",
            eigenvar,
            f"eigenvar '{eigenvar}' escapes scope (free in conclusion)",
        )
    # Box assumption must equal P[eigenvar/x]
    expected_assumption = subst(body, x, Var(eigenvar))
    actual_assumption = proof.line(box_start).formula
    if actual_assumption != expected_assumption:
        return FormulaMismatch("existsE", expected_assumption, actual_assumption)
    # Box conclusion must equal Q
    box_conclusion = proof.line(box_end).formula
    if box_conclusion != q:
        return FormulaMismatch("existsE", q, box_conclusion)
    return None


# ---------------------------------------------------------------------------
# Equality rules (2)
# ---------------------------------------------------------------------------


def _eqRefl(line: ProofLine, proof: Proof) -> RuleError | None:
    """Derive t = t for any term t."""
    if err := _check_refs(line, proof, 0, 0):
        return err
    if not isinstance(line.formula, Equals):
        return WrongFormulaShape("eqRefl", line.number, "Equals(t, t)")
    if line.formula.lhs != line.formula.rhs:
        expected = Equals(line.formula.lhs, line.formula.lhs)
        return FormulaMismatch("eqRefl", expected, line.formula)
    return None


def _eqSubst(line: ProofLine, proof: Proof) -> RuleError | None:
    """From t = u and P[t/x] derive P[u/x].

    extra: {"var": str, "template": Formula}  (template is P with free x)
    """
    if err := _check_refs(line, proof, 2, 0):
        return err
    app = line.justification
    assert isinstance(app, RuleApp)
    if err := _require_extra(line, "var"):
        return err
    if err := _require_extra(line, "template"):
        return err
    eq_ref, pt_ref = app.line_refs
    if err := _check_accessible(line, proof, eq_ref):
        return err
    if err := _check_accessible(line, proof, pt_ref):
        return err
    eq_f = proof.line(eq_ref).formula
    if not isinstance(eq_f, Equals):
        return WrongFormulaShape("eqSubst", eq_ref, "Equals(t, u)")
    t, u = eq_f.lhs, eq_f.rhs
    x = app.extra["var"]
    template = app.extra["template"]
    expected_premise = subst(template, x, t)
    actual_premise = proof.line(pt_ref).formula
    if actual_premise != expected_premise:
        return FormulaMismatch("eqSubst", expected_premise, actual_premise)
    expected_conclusion = subst(template, x, u)
    if line.formula != expected_conclusion:
        return FormulaMismatch("eqSubst", expected_conclusion, line.formula)
    return None


# ---------------------------------------------------------------------------
# Arithmetic evaluation (arithEval — the 23rd rule, added in M2)
# ---------------------------------------------------------------------------


def _eval_term(t: Term) -> int | Fraction | None:
    """Return the numeric value of t, or None if t is non-evaluable.

    Defence-in-depth: rejects bool, float, Meta, and Var independently
    of any upstream guard (§9.6–9.9 of ARITH_EVAL_DESIGN.md).
    """
    match t:
        case Const(value=v):
            if isinstance(v, bool):      # bool is int subclass — reject
                return None
            if isinstance(v, float):     # defence-in-depth
                return None
            if isinstance(v, int):
                return v
            if isinstance(v, Fraction):
                return v
            return None                  # str, anything else

        case Func(name="+", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None:
                return None
            return va + vb

        case Func(name="-", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None:
                return None
            return va - vb

        case Func(name="-", args=(a,)):  # unary negation (arity 1)
            va = _eval_term(a)
            if va is None:
                return None
            return -va

        case Func(name="*", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None:
                return None
            return va * vb

        case Func(name="/", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None:
                return None
            if vb == 0:
                return None              # division by zero
            return Fraction(va) / Fraction(vb)

        case Func(name="^", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None:
                return None
            if isinstance(vb, bool) or not isinstance(vb, int):
                return None              # exponent must be int (not bool)
            if va == 0 and vb <= 0:
                return None              # 0^0 contested; 0^negative undefined
            if vb < 0:
                return Fraction(va) ** vb  # forces Fraction, avoids float
            return va ** vb              # int^int -> int; Fraction^int -> Fraction

        case _:                          # Var, Meta, unknown Func, wrong arity
            return None


def _eval_atom(f: Atom | Equals) -> bool | None:
    """Return the boolean value of a ground arithmetic atom, or None
    if non-evaluable."""
    match f:
        case Atom(pred="<", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va < vb)
        case Atom(pred="<=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va <= vb)
        case Atom(pred=">", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va > vb)
        case Atom(pred=">=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va >= vb)
        case Atom(pred="!=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va != vb)

        case Atom(pred="plus", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va + vb == vc
        case Atom(pred="minus", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va - vb == vc
        case Atom(pred="times", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            return va * vb == vc
        case Atom(pred="divides", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None:
                return None
            if vb == 0:
                return None
            return Fraction(va) / Fraction(vb) == vc

        case Equals(lhs=lhs, rhs=rhs):
            vl, vr = _eval_term(lhs), _eval_term(rhs)
            if vl is None or vr is None:
                return None
            return vl == vr

        case _:
            return None  # unknown predicate, wrong arity, non-Atom/Equals shape


def _arithEval(line: ProofLine, proof: Proof) -> RuleError | None:
    if err := _check_refs(line, proof, expected_lines=0, expected_boxes=0):
        return err
    f = line.formula
    if not isinstance(f, (Atom, Equals)):
        return MalformedArithmetic(
            line.number, f,
            "arithEval requires Atom or Equals, got " + type(f).__name__,
        )
    result = _eval_atom(f)
    if result is None:
        return MalformedArithmetic(line.number, f, "non-evaluable arithmetic atom")
    if result is False:
        return EvaluationFalse(line.number, f)
    return None  # result is True — accept


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

RULES: dict[str, RuleChecker] = {
    "andI": _andI,
    "andE_L": _andE_L,
    "andE_R": _andE_R,
    "orI_L": _orI_L,
    "orI_R": _orI_R,
    "orE": _orE,
    "impI": _impI,
    "impE": _impE,
    "notI": _notI,
    "notE": _notE,
    "botE": _botE,
    "iffI": _iffI,
    "iffE_L": _iffE_L,
    "iffE_R": _iffE_R,
    "reit": _reit,
    "PBC": _PBC,
    "forallI": _forallI,
    "forallE": _forallE,
    "existsI": _existsI,
    "existsE": _existsE,
    "eqRefl": _eqRefl,
    "eqSubst": _eqSubst,
    "arithEval": _arithEval,
}
