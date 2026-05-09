"""solvers/sympy_bridge.py — real SymPy bridge.

This is the ONLY file in hlmr that imports sympy.
Implements the SymPyBridge protocol from solvers/__init__.py.

Uses sympy.solveset with domain=S.Reals. No nsolve, no float arithmetic.
Results containing irrationals (sympy.sqrt, etc.) are returned as
SymPyConditionSet, which the dispatcher maps to OutsideFragment.
"""

from __future__ import annotations

from fractions import Fraction

import sympy
from sympy import S

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.solvers import (
    SymPyConditionSet,
    SymPyError,
    SymPyFiniteRoots,
    SymPyNoRealRoots,
    SymPyResult,
)


class SymPyTranslationError(Exception):
    """Raised when an IR term/formula cannot be translated to SymPy."""


class SymPyBridge:
    """Real SymPy bridge; implements the SymPyBridge protocol.

    Stateless: each solveset() call is independent. Uses
    sympy.solveset(..., domain=S.Reals) throughout.
    """

    def solveset(self, goal: Atom | Equals) -> SymPyResult:
        """Translate goal to SymPy, solve, return typed result."""
        try:
            return self._solve(goal)
        except SymPyTranslationError as e:
            return SymPyError(msg=str(e))
        except Exception as e:
            return SymPyError(msg=f"SymPy raised unexpectedly: {e!r}")

    # ------------------------------------------------------------------
    # Internal solve logic
    # ------------------------------------------------------------------

    def _solve(self, goal: Atom | Equals) -> SymPyResult:
        match goal:
            case Atom(pred="root_of", args=(_, poly)):
                return self._solve_root_of(poly)
            case Equals(lhs=lhs, rhs=rhs):
                return self._solve_equals(lhs, rhs)
            case _:
                raise SymPyTranslationError(
                    f"SymPy bridge received non-root_of/Equals goal: {goal!r}. "
                    "The classifier routes comparison atoms to Z3, not SymPy."
                )

    def _solve_root_of(self, poly: Term) -> SymPyResult:
        """Solve root_of(_, poly) by finding poly's real roots."""
        sp_expr = self._term(poly)
        free = sp_expr.free_symbols

        if len(free) == 0:
            # Constant polynomial — no variable to solve for.
            return SymPyFiniteRoots(roots=())

        if len(free) > 1:
            raise SymPyTranslationError(
                f"Polynomial has {len(free)} free symbols {free}; "
                "expected at most 1. The classifier should have rejected this."
            )

        symbol = next(iter(free))
        return self._call_solveset(sp_expr, symbol)

    def _solve_equals(self, lhs: Term, rhs: Term) -> SymPyResult:
        """Solve Equals(lhs, rhs) for the single free variable."""
        sp_lhs = self._term(lhs)
        sp_rhs = self._term(rhs)
        residual = sp_lhs - sp_rhs
        free = residual.free_symbols

        if len(free) == 0:
            # No variable — evaluate directly.
            if residual == 0:
                return SymPyFiniteRoots(roots=())  # identity; no binding
            return SymPyNoRealRoots()

        if len(free) > 1:
            raise SymPyTranslationError(
                f"Equals goal has {len(free)} free symbols {free}; expected 1."
            )

        symbol = next(iter(free))
        return self._call_solveset(residual, symbol)

    def _call_solveset(
        self, expr: sympy.Expr, symbol: sympy.Symbol
    ) -> SymPyResult:
        """Call sympy.solveset and convert the result to SymPyResult.

        Uses SymPy's set properties rather than isinstance checks on
        singleton classes (EmptySet is a singleton instance in SymPy 1.12+,
        not a plain class, so isinstance(result, sympy.EmptySet) raises).
        """
        result = sympy.solveset(expr, symbol, domain=S.Reals)

        # Empty set: check .is_empty (sympy.EmptySet is an instance, not a
        # class, so isinstance(result, sympy.EmptySet) raises TypeError).
        if result.is_empty:
            return SymPyNoRealRoots()

        # Finite set of explicit solutions. isinstance works here because
        # sympy.FiniteSet is a proper class (unlike EmptySet singleton).
        if isinstance(result, sympy.FiniteSet):
            return self._finite_set_to_result(result)

        # ConditionSet — SymPy could not solve analytically.
        from sympy.sets.conditionset import ConditionSet as _ConditionSet
        if isinstance(result, _ConditionSet):
            return SymPyConditionSet(reason=str(result))

        # Interval or Union → continuous solution set.
        from sympy.sets.sets import Interval as _Interval, Union as _Union
        if isinstance(result, (_Interval, _Union)):
            return SymPyConditionSet(
                reason=f"continuous solution set: {result}"
            )

        # Anything else (ImageSet, etc.).
        return SymPyConditionSet(reason=f"unrecognised solveset result: {result}")

    def _finite_set_to_result(self, fs: sympy.FiniteSet) -> SymPyResult:
        """Convert a FiniteSet to SymPyFiniteRoots, dropping irrationals."""
        roots: list[int | Fraction] = []
        for elem in fs:
            py_val = _sympy_val_to_python(elem)
            if py_val is None:
                # Irrational or otherwise unrepresentable — outside fragment.
                return SymPyConditionSet(
                    reason=(
                        "result contains irrational algebraic numbers; "
                        "outside the kernel-verifiable fragment"
                    )
                )
            roots.append(py_val)
        return SymPyFiniteRoots(roots=tuple(roots))

    # ------------------------------------------------------------------
    # Term translation: IR → SymPy
    # ------------------------------------------------------------------

    def _term(self, t: Term) -> sympy.Expr:
        """Translate an IR Term to a SymPy expression."""
        match t:
            case Const(value=v) if isinstance(v, bool):
                raise SymPyTranslationError(f"Bool constant {v!r} is not arithmetic.")
            case Const(value=v) if isinstance(v, int):
                return sympy.Integer(v)
            case Const(value=v) if isinstance(v, Fraction):
                return sympy.Rational(v.numerator, v.denominator)
            case Const(value=v):
                raise SymPyTranslationError(
                    f"Const({v!r}) is a string constant; cannot translate to SymPy."
                )
            case Var(name=n) | Meta(name=n):
                return sympy.Symbol(n)
            case Func(name="+", args=(a, b)):
                return self._term(a) + self._term(b)
            case Func(name="-", args=(a, b)):
                return self._term(a) - self._term(b)
            case Func(name="-", args=(a,)):
                return -self._term(a)
            case Func(name="*", args=(a, b)):
                return self._term(a) * self._term(b)
            case Func(name="/", args=(a, b)):
                return self._term(a) / self._term(b)
            case Func(name="^", args=(a, b)):
                return self._term(a) ** self._term(b)
            case _:
                raise SymPyTranslationError(
                    f"Cannot translate term to SymPy: {t!r}"
                )


# ---------------------------------------------------------------------------
# SymPy value → Python conversion
# ---------------------------------------------------------------------------


def _sympy_val_to_python(elem: sympy.Expr) -> int | Fraction | None:
    """Convert a SymPy FiniteSet element to int or Fraction.

    Returns None for irrationals (sqrt(2), etc.) so the caller can
    fall back to SymPyConditionSet.
    """
    if isinstance(elem, sympy.Integer):
        return int(elem)
    if isinstance(elem, sympy.Rational):
        return Fraction(int(elem.p), int(elem.q))
    # Float — should not appear (we never call nsolve).
    if isinstance(elem, sympy.Float):
        return None
    # Algebraic irrational (sqrt, cbrt of non-perfect-power, etc.).
    # Check: can it be evaluated to an exact rational?
    try:
        r = sympy.nsimplify(elem, rational=True, tolerance=0)
        if isinstance(r, sympy.Rational):
            return Fraction(int(r.p), int(r.q))
        if isinstance(r, sympy.Integer):
            return int(r)
    except Exception:
        pass
    return None
