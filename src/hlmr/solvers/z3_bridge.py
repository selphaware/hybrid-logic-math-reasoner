"""solvers/z3_bridge.py — real Z3 bridge.

This is the ONLY file in hlmr that imports z3.
Implements the Z3Bridge protocol from solvers/__init__.py.

Z3 context lifecycle: one z3.Context per Z3Bridge instance, shared across
all check() calls. Each check() creates a fresh z3.Solver bound to the
context. Variables are declared as z3.Real and cached by name; the same
meta name always resolves to the same z3 expression within this context.

Known limitation: typed metavariables (prd_milestone_2.md §6.1) are not
yet inferred by the bridge. All metas are Real. More nuanced typing deferred
until the parser propagates meta types.
"""

from __future__ import annotations

from fractions import Fraction

import z3

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.solvers import Z3Result, Z3Sat, Z3Timeout, Z3Unknown, Z3Unsat


class Z3TranslationError(Exception):
    """Raised when an IR term/formula cannot be translated to Z3."""


class Z3Bridge:
    """Real Z3 bridge; implements the Z3Bridge protocol.

    One z3.Context per instance (DISPATCH_DESIGN.md §9.1). Variables
    declared as z3.Real and cached by meta/var name for the lifetime of
    this bridge. Each check() creates a fresh z3.Solver.
    """

    def __init__(self, default_timeout_ms: int = 5000) -> None:
        self._default_timeout_ms = default_timeout_ms
        self._ctx = z3.Context()
        # Cache: meta/var name → z3.Real variable in self._ctx.
        self._var_cache: dict[str, z3.ArithRef] = {}

    def check(
        self,
        constraints: tuple[Atom | Equals, ...],
        timeout_ms: int,
    ) -> Z3Result:
        """Translate constraints to Z3 form, check sat, return typed result."""
        solver = z3.Solver(ctx=self._ctx)
        solver.set("timeout", timeout_ms)

        # Collect the meta/var names referenced in this call so we know
        # which entries to extract from the model.
        referenced: set[str] = set()

        try:
            for c in constraints:
                z3_expr = self._formula(c, referenced)
                solver.add(z3_expr)
        except Z3TranslationError:
            raise

        outcome = solver.check()

        if outcome == z3.sat:
            model = solver.model()
            py_model: dict[str, int | Fraction] = {}
            for name in referenced:
                if name not in self._var_cache:
                    continue
                var = self._var_cache[name]
                val = model[var]
                if val is None:
                    # Z3 did not assign a value — variable is unconstrained.
                    continue
                py_model[name] = _z3_val_to_python(val)
            return Z3Sat(model=py_model)

        if outcome == z3.unsat:
            return Z3Unsat()

        # outcome == z3.unknown
        reason = solver.reason_unknown()
        if "timeout" in reason.lower() or "canceled" in reason.lower():
            return Z3Timeout()
        return Z3Unknown(reason=reason)

    # ------------------------------------------------------------------
    # Formula translation
    # ------------------------------------------------------------------

    def _formula(
        self, f: Atom | Equals, referenced: set[str]
    ) -> z3.BoolRef:
        """Translate a single Atom or Equals to a Z3 BoolRef."""
        match f:
            case Equals(lhs=lhs, rhs=rhs):
                return self._term(lhs, referenced) == self._term(rhs, referenced)
            case Atom(pred="<", args=(a, b)):
                return self._term(a, referenced) < self._term(b, referenced)
            case Atom(pred="<=", args=(a, b)):
                return self._term(a, referenced) <= self._term(b, referenced)
            case Atom(pred=">", args=(a, b)):
                return self._term(a, referenced) > self._term(b, referenced)
            case Atom(pred=">=", args=(a, b)):
                return self._term(a, referenced) >= self._term(b, referenced)
            case Atom(pred="!=", args=(a, b)):
                return self._term(a, referenced) != self._term(b, referenced)
            case Atom(pred="plus", args=(a, b, c)):
                return (
                    self._term(a, referenced) + self._term(b, referenced)
                    == self._term(c, referenced)
                )
            case Atom(pred="minus", args=(a, b, c)):
                return (
                    self._term(a, referenced) - self._term(b, referenced)
                    == self._term(c, referenced)
                )
            case Atom(pred="times", args=(a, b, c)):
                return (
                    self._term(a, referenced) * self._term(b, referenced)
                    == self._term(c, referenced)
                )
            case Atom(pred="divides", args=(a, b, c)):
                # Z3's theory of rationals treats x/0 = 0 as a total function,
                # so without a guard Z3 returns sat with b=0, which arithEval
                # rejects (Python's Fraction raises ZeroDivisionError). Adding
                # an explicit b != 0 constraint aligns Z3's model space with
                # arithEval's domain — any sat result is guaranteed non-zero
                # divisor and survives the verify-before-return step cleanly.
                b_term = self._term(b, referenced)
                return z3.And(
                    b_term != z3.RealVal(0, ctx=self._ctx),
                    self._term(a, referenced) / b_term == self._term(c, referenced),
                )
            case _:
                raise Z3TranslationError(
                    f"Cannot translate formula to Z3: {f!r}. "
                    "The classifier should have rejected this shape."
                )

    def _term(self, t: Term, referenced: set[str]) -> z3.ArithRef:
        """Translate an IR Term to a Z3 arithmetic expression."""
        match t:
            case Const(value=v) if isinstance(v, bool):
                raise Z3TranslationError(
                    f"Bool constant {v!r} is not arithmetic."
                )
            case Const(value=v) if isinstance(v, int):
                return z3.RealVal(v, ctx=self._ctx)
            case Const(value=v) if isinstance(v, Fraction):
                return z3.RatVal(v.numerator, v.denominator, ctx=self._ctx)
            case Const(value=v):
                raise Z3TranslationError(
                    f"Const({v!r}) is a string constant; cannot translate to Z3 arithmetic. "
                    "The classifier should have rejected this."
                )
            case Meta(name=n) | Var(name=n):
                referenced.add(n)
                return self._get_var(n)
            case Func(name="+", args=(a, b)):
                return self._term(a, referenced) + self._term(b, referenced)
            case Func(name="-", args=(a, b)):
                return self._term(a, referenced) - self._term(b, referenced)
            case Func(name="-", args=(a,)):
                return -self._term(a, referenced)
            case Func(name="*", args=(a, b)):
                return self._term(a, referenced) * self._term(b, referenced)
            case Func(name="/", args=(a, b)):
                return self._term(a, referenced) / self._term(b, referenced)
            case Func(name="^", args=(a, Const(value=n))) if isinstance(n, int) and n >= 0:
                return self._term(a, referenced) ** n
            case Func(name="^"):
                raise Z3TranslationError(
                    f"Power with non-constant or negative exponent: {t!r}. "
                    "The classifier should have rejected transcendentals."
                )
            case _:
                raise Z3TranslationError(f"Cannot translate term to Z3: {t!r}")

    def _get_var(self, name: str) -> z3.ArithRef:
        """Get (or create) the z3.Real variable for this meta/var name."""
        if name not in self._var_cache:
            self._var_cache[name] = z3.Real(name, ctx=self._ctx)
        return self._var_cache[name]


# ---------------------------------------------------------------------------
# Model value conversion
# ---------------------------------------------------------------------------


def _z3_val_to_python(val: z3.ExprRef) -> int | Fraction:
    """Convert a Z3 model value to Python int or Fraction.

    RatNumRef with denominator 1 normalises to int.
    """
    if isinstance(val, z3.IntNumRef):
        return int(val.as_long())
    if isinstance(val, z3.RatNumRef):
        n = int(val.numerator_as_long())
        d = int(val.denominator_as_long())
        if d == 1:
            return n
        return Fraction(n, d)
    raise Z3TranslationError(
        f"Z3 returned unexpected value type {type(val).__name__}: {val!r}. "
        "Expected IntNumRef or RatNumRef for the linear-arithmetic fragment."
    )
