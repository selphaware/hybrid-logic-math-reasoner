"""Constraint classifier — pure, no solver calls.

Implements the eight classification rules (C1-C8) from
DISPATCH_DESIGN.md §4. Returns a ClassifyDecision telling the
Dispatcher which solver (if any) should handle the goal.

Key architectural points:
- This module is the only caller of the contested-shape detector.
  The detector lists ALL contested patterns (currently only 0^0).
  When ARITH_EVAL_DESIGN.md adds a new contested case, extend
  _is_contested_when_ground in lock-step. See DISPATCH_DESIGN.md
  §7.3 for the rationale.
- This module does NOT import the kernel's private _eval_term /
  _eval_atom helpers. The trust boundary stays clean. It reproduces
  only the small shape-checking subset it needs (DISPATCH §4.3).
- No mutable state. Every function is pure.
"""

from __future__ import annotations

from fractions import Fraction

from hlmr.dispatch import ClassifyDecision, OutsideFragmentReason, RouteTarget
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.ir.kb import KnowledgeBase
from hlmr.unify.substitution import Substitution, apply_to_formula


# ---------------------------------------------------------------------------
# Arithmetic predicate sets (module-level frozen constants)
# ---------------------------------------------------------------------------

#: Binary comparison operators routed to Z3.
_COMPARISON_PREDS: frozenset[str] = frozenset({"<", "<=", ">", ">=", "!="})

#: Ternary predicate-form arithmetic atoms routed to Z3.
_TERNARY_PREDS: frozenset[str] = frozenset({"plus", "minus", "times", "divides"})

#: All M2 arithmetic predicate names. A predicate in this set that also
#: appears in the KB is treated as arithmetic (KB route is skipped).
_ARITH_PREDICATE_SET: frozenset[str] = (
    _COMPARISON_PREDS | _TERNARY_PREDS | frozenset({"root_of"})
)

#: Binary/unary arithmetic operator names for Func nodes.
_ARITH_OPERATORS: frozenset[str] = frozenset({"+", "-", "*", "/", "^"})


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def classify(
    goal: Atom | Equals,
    subst: Substitution,
    kb: KnowledgeBase,
) -> ClassifyDecision:
    """Classify a single goal and return a routing verdict.

    Steps:
      1. Apply subst to goal so prior bindings are visible.
      2. Pattern-match the goal's top-level shape.
      3. Return ClassifyDecision. Conservative default: REJECTED.

    Rules are evaluated top-to-bottom; the first matching rule wins.
    (DISPATCH_DESIGN.md §4.1–4.2)
    """
    g = apply_to_formula(subst, goal)
    return _classify_applied(g, kb)


def _classify_applied(g: Atom | Equals, kb: KnowledgeBase) -> ClassifyDecision:
    """Classify a post-substitution goal. Internal; called by classify()."""

    # ------------------------------------------------------------------
    # Rule C1: KB predicate — goal predicate is in the KB and NOT in the
    # arithmetic set → route to M1's clause-picker.
    # ------------------------------------------------------------------
    match g:
        case Atom(pred=pred) if (
            pred not in _ARITH_PREDICATE_SET
            and any(c.head.pred == pred for c in kb.clauses)
        ):
            return ClassifyDecision(target=RouteTarget.KB)

    # ------------------------------------------------------------------
    # Rule C2: Binary comparison operator atoms.
    # pred ∈ {<, <=, >, >=, !=}, arity exactly 2.
    # Both terms must be arithmetic-evaluable shapes (Const, Meta, Var,
    # or +-*/^ Func). If the terms contain a ground 0^0 subterm, C8
    # fires and the goal is rejected as a contested convention.
    # ------------------------------------------------------------------
    match g:
        case Atom(pred=pred, args=(a, b)) if pred in _COMPARISON_PREDS:
            # Transcendental check (^ with Var/Meta exponent) must run before the
            # arithmetic-evaluable check: _is_arithmetic_evaluable_term accepts
            # Func("^", (a, b)) for any arithmetic a, b — including Var/Meta in
            # exponent position — so without this guard, 2^x > 5 would reach Z3.
            if _has_var_or_meta_exponent(a) or _has_var_or_meta_exponent(b):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.TRANSCENDENTAL,
                    detail=f"comparison atom '{pred}' contains a transcendental expression",
                )
            if not (_is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.UNRECOGNISED_SHAPE,
                    detail=f"comparison atom '{pred}' has non-arithmetic argument",
                )
            # C8 check: contested ground 0^0 subterm
            if _is_contested_when_ground(a) or _is_contested_when_ground(b):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.CONTESTED_CONVENTION,
                    detail=(
                        "comparison atom contains a contested mathematical expression "
                        "(currently 0^0; see docs/strategic_direction.md §6.9)"
                    ),
                )
            return ClassifyDecision(target=RouteTarget.Z3)

    # ------------------------------------------------------------------
    # Rule C3: Ternary predicate-form atoms.
    # pred ∈ {plus, minus, times, divides}, arity exactly 3.
    # All three arguments must be arithmetic-evaluable.
    # C8 check applies to all three args.
    # ------------------------------------------------------------------
    match g:
        case Atom(pred=pred, args=(a, b, c)) if pred in _TERNARY_PREDS:
            # Same ordering rule as C2: transcendental check before arithmetic-evaluable
            # check, for the same reason.
            if any(_has_var_or_meta_exponent(x) for x in (a, b, c)):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.TRANSCENDENTAL,
                    detail=f"predicate '{pred}' contains a transcendental expression",
                )
            if not all(_is_arithmetic_evaluable_term(x) for x in (a, b, c)):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.UNRECOGNISED_SHAPE,
                    detail=f"predicate '{pred}' has non-arithmetic argument",
                )
            if any(_is_contested_when_ground(x) for x in (a, b, c)):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.CONTESTED_CONVENTION,
                    detail=(
                        f"predicate '{pred}' contains a contested mathematical expression "
                        "(currently 0^0; see docs/strategic_direction.md §6.9)"
                    ),
                )
            return ClassifyDecision(target=RouteTarget.Z3)

    # ------------------------------------------------------------------
    # Rule C4: root_of/2 — symbolic algebraic equations → SymPy.
    # If poly is a polynomial in one variable → SYMPY.
    # If poly contains ^ with Var/Meta exponent → TRANSCENDENTAL.
    # Otherwise → UNRECOGNISED_SHAPE.
    # ------------------------------------------------------------------
    match g:
        case Atom(pred="root_of", args=(_, poly)):
            if _is_polynomial_in_one_var(poly):
                return ClassifyDecision(target=RouteTarget.SYMPY)
            if _has_var_or_meta_exponent(poly):
                return ClassifyDecision(
                    target=RouteTarget.REJECTED,
                    reason=OutsideFragmentReason.TRANSCENDENTAL,
                    detail="root_of polynomial contains a transcendental expression (^ with variable exponent)",
                )
            return ClassifyDecision(
                target=RouteTarget.REJECTED,
                reason=OutsideFragmentReason.UNRECOGNISED_SHAPE,
                detail="root_of polynomial is not a polynomial with rational coefficients in one variable",
            )

    # ------------------------------------------------------------------
    # Rule C5: Equals IR node.
    # - Both sides arithmetic → Z3 (linear) or SYMPY (polynomial) or
    #   REJECTED (transcendental).
    # - Both sides non-arithmetic → KB (unification-style).
    # - Mixed → REJECTED with UNRECOGNISED_SHAPE.
    # ------------------------------------------------------------------
    match g:
        case Equals(lhs=lhs, rhs=rhs):
            lhs_arith = _is_arithmetic_evaluable_term(lhs)
            rhs_arith = _is_arithmetic_evaluable_term(rhs)

            if lhs_arith and rhs_arith:
                # Check for transcendentals first
                if _has_var_or_meta_exponent(lhs) or _has_var_or_meta_exponent(rhs):
                    return ClassifyDecision(
                        target=RouteTarget.REJECTED,
                        reason=OutsideFragmentReason.TRANSCENDENTAL,
                        detail="equality contains a transcendental expression",
                    )
                # C8: contested shape
                if _is_contested_when_ground(lhs) or _is_contested_when_ground(rhs):
                    return ClassifyDecision(
                        target=RouteTarget.REJECTED,
                        reason=OutsideFragmentReason.CONTESTED_CONVENTION,
                        detail=(
                            "equality contains a contested mathematical expression "
                            "(currently 0^0; see docs/strategic_direction.md §6.9)"
                        ),
                    )
                # Linear → Z3; polynomial (non-linear in metas) → SymPy
                if _is_polynomial_nonlinear_in_metas(lhs) or _is_polynomial_nonlinear_in_metas(rhs):
                    return ClassifyDecision(target=RouteTarget.SYMPY)
                return ClassifyDecision(target=RouteTarget.Z3)

            if not lhs_arith and not rhs_arith:
                # Both non-arithmetic: treat as unification-style equality → KB
                return ClassifyDecision(target=RouteTarget.KB)

            # Mixed: one side arithmetic, one side not → unrecognised
            return ClassifyDecision(
                target=RouteTarget.REJECTED,
                reason=OutsideFragmentReason.UNRECOGNISED_SHAPE,
                detail="equality has one arithmetic side and one non-arithmetic side",
            )

    # ------------------------------------------------------------------
    # Rule C7 (default): anything else → conservative rejection.
    # C6 (multi-goal) is not handled here; classify() is called per-goal.
    # ------------------------------------------------------------------
    return ClassifyDecision(
        target=RouteTarget.REJECTED,
        reason=OutsideFragmentReason.UNRECOGNISED_SHAPE,
        detail=f"unrecognised goal shape: {type(g).__name__}",
    )


# ---------------------------------------------------------------------------
# Helper: contested-shape detector (C8 / DISPATCH §7.3)
# ---------------------------------------------------------------------------


def _is_zero_const(t: Term) -> bool:
    """True iff t is Const(0) as an integer or rational.

    Used exclusively by _is_contested_when_ground to check whether
    a Func("^", (a, b)) has both a and b equal to zero.
    """
    match t:
        case Const(value=v):
            return (
                not isinstance(v, bool)
                and isinstance(v, (int, Fraction))
                and v == 0
            )
        case _:
            return False


def _is_contested_when_ground(t: Term) -> bool:
    """True iff t contains a ground Func("^", (Const(0), Const(0))) — i.e., 0^0.

    0^0 is contested between mathematical conventions:
    - Combinatorics, discrete maths, polynomial rings: 0^0 = 1.
    - Real analysis: undefined (x^y limit doesn't exist as x,y→0).
    The kernel's arithEval rejects 0^0 per the conservative-default
    principle (ARITH_EVAL_DESIGN.md §6.1, §9.5). The dispatcher pre-
    filters goals containing a ground 0^0 before routing to Z3/SymPy.

    This function implements the classify-side pre-filter (C8). The
    identical post-filter (at verify-time) is _ground_atom_lands_on_
    contested_shape in route.py.

    IMPORTANT: extend this function in lock-step with ARITH_EVAL_DESIGN.md's
    contested-case list (currently only 0^0). If a future release adds a
    new contested case to arithEval but NOT here, the dispatcher crashes via
    Case 1 (loud failure) instead of graceful OutsideFragment — acceptable
    per DISPATCH_DESIGN.md §7.3.

    See also: docs/strategic_direction.md §6.9 and §11.7.
    """
    match t:
        case Func(name="^", args=(a, b)):
            # Direct 0^0: both arms must be the zero constant.
            if _is_zero_const(a) and _is_zero_const(b):
                return True
            # Recurse into arms for nested cases (e.g. (0^0) + 1).
            return _is_contested_when_ground(a) or _is_contested_when_ground(b)
        case Func(args=args):
            return any(_is_contested_when_ground(a) for a in args)
        case _:
            return False


# ---------------------------------------------------------------------------
# Helper: arithmetic shape checks
# ---------------------------------------------------------------------------


def _is_arithmetic_evaluable_term(t: Term) -> bool:
    """True iff t is built from Const(int|Fraction), Meta, Var, and
    operator Func nodes from {+, -, *, /, ^}. Meta and Var are permitted
    at classification time — they may be bound by the substitution or by
    the solver call that follows.

    This is a SHAPE check, not an evaluation. It reproduces the subset of
    arithEval's evaluable-term rules that the classifier needs, without
    importing kernel internals (DISPATCH §4.3).
    """
    match t:
        case Const(value=v):
            return not isinstance(v, bool) and isinstance(v, (int, Fraction))
        case Meta():
            return True
        case Var():
            return True
        case Func(name="+", args=(a, b)):
            return _is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)
        case Func(name="-", args=(a, b)):
            return _is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)
        case Func(name="-", args=(a,)):
            return _is_arithmetic_evaluable_term(a)
        case Func(name="*", args=(a, b)):
            return _is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)
        case Func(name="/", args=(a, b)):
            return _is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)
        case Func(name="^", args=(a, b)):
            return _is_arithmetic_evaluable_term(a) and _is_arithmetic_evaluable_term(b)
        case _:
            return False


def _has_metas_or_vars(t: Term) -> bool:
    """True iff t contains any Meta or Var node."""
    match t:
        case Meta() | Var():
            return True
        case Func(args=args):
            return any(_has_metas_or_vars(a) for a in args)
        case _:
            return False


def _has_var_or_meta_exponent(t: Term) -> bool:
    """True iff t contains Func("^", (base, Var|Meta)) — a transcendental
    shape (e.g. 2^x, x^y). An integer-constant exponent (e.g. x^2) is
    not transcendental and returns False.

    Used to distinguish polynomial from transcendental expressions in
    C4 (root_of) and C5 (Equals).
    """
    match t:
        case Func(name="^", args=(base, exp)):
            if isinstance(exp, (Var, Meta)):
                return True
            return _has_var_or_meta_exponent(base) or _has_var_or_meta_exponent(exp)
        case Func(args=args):
            return any(_has_var_or_meta_exponent(a) for a in args)
        case _:
            return False


def _is_polynomial_in_one_var(poly: Term) -> bool:
    """True iff poly is a polynomial with rational coefficients in a single
    Var or Meta, using only +, -, *, and ^ with non-negative integer Const
    exponents. No /, no Var/Meta in exponent position.

    Used by Rule C4 (root_of) to determine whether to route to SymPy.
    """
    seen: set[str] = set()

    def walk(t: Term) -> bool:
        match t:
            case Const(value=v):
                return not isinstance(v, bool) and isinstance(v, (int, Fraction))
            case Var(name=n):
                seen.add(n)
                return len(seen) <= 1
            case Meta(name=n):
                seen.add(n)
                return len(seen) <= 1
            case Func(name="+", args=(a, b)):
                return walk(a) and walk(b)
            case Func(name="-", args=(a, b)):
                return walk(a) and walk(b)
            case Func(name="-", args=(a,)):
                return walk(a)
            case Func(name="*", args=(a, b)):
                return walk(a) and walk(b)
            case Func(name="^", args=(base, exp)):
                # Exponent must be a non-negative integer constant; any
                # Var/Meta in exponent position means transcendental.
                if not isinstance(exp, Const):
                    return False
                if isinstance(exp.value, bool) or not isinstance(exp.value, int):
                    return False
                if exp.value < 0:
                    return False
                return walk(base)
            case _:
                return False

    return walk(poly)


def _is_polynomial_nonlinear_in_metas(t: Term) -> bool:
    """True iff t contains a non-linear term involving metas/vars:
    - x^n for integer n ≥ 2 where x contains metas/vars, OR
    - x * y where both x and y contain metas/vars.

    Used by Rule C5 to distinguish linear (→ Z3) from polynomial (→ SymPy)
    arithmetic equalities.
    """
    match t:
        case Func(name="^", args=(base, exp)):
            if (
                isinstance(exp, Const)
                and isinstance(exp.value, int)
                and not isinstance(exp.value, bool)
                and exp.value >= 2
                and _has_metas_or_vars(base)
            ):
                return True
            return _is_polynomial_nonlinear_in_metas(base) or _is_polynomial_nonlinear_in_metas(exp)
        case Func(name="*", args=(a, b)):
            if _has_metas_or_vars(a) and _has_metas_or_vars(b):
                return True
            return _is_polynomial_nonlinear_in_metas(a) or _is_polynomial_nonlinear_in_metas(b)
        case Func(args=args):
            return any(_is_polynomial_nonlinear_in_metas(a) for a in args)
        case _:
            return False
