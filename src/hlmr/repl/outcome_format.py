"""User-friendly formatters for DispatchOutcome and ClassifyDecision.

Used by the REPL to display solver outcomes and the :solver command output.
All functions return plain strings; no I/O is performed here.
"""

from __future__ import annotations

from fractions import Fraction

from hlmr.dispatch import (
    ClassifyDecision,
    InfinitelyManySolutions,
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    RouteTarget,
    Underdetermined,
    UniqueSolution,
)
from hlmr.ir.formula import Const, Func, Meta, Term, Var
from hlmr.unify.substitution import Substitution

DispatchOutcome = (
    UniqueSolution
    | MultipleSolutions
    | InfinitelyManySolutions
    | NoSolution
    | Underdetermined
    | OutsideFragment
)


def format_substitution(subst: Substitution) -> str:
    """Format a substitution as '{?X = 5, ?Y = 8}'."""
    if not subst:
        return "{}"
    items = ", ".join(
        f"{k} = {_fmt_term(v)}" for k, v in sorted(subst.items())
    )
    return "{" + items + "}"


def format_outcome(outcome: object) -> str:
    """User-friendly multi-line string for any DispatchOutcome."""
    match outcome:
        case UniqueSolution(binding=b):
            return f"UniqueSolution: {format_substitution(b)}"

        case MultipleSolutions(solutions=sols):
            lines = [f"MultipleSolutions (n={len(sols)}):"]
            for i, s in enumerate(sols):
                lines.append(f"  [{i}] {format_substitution(s)}")
            return "\n".join(lines)

        case InfinitelyManySolutions(example=ex, free_metas=free):
            free_str = ", ".join(free) if free else "(none)"
            return (
                f"InfinitelyManySolutions: example {format_substitution(ex)}; "
                f"free metas: {free_str}"
            )

        case NoSolution():
            return "NoSolution"

        case Underdetermined(partial_binding=pb, unbound=ub):
            ub_str = ", ".join(ub) if ub else "(none)"
            return (
                f"Underdetermined: partial binding {format_substitution(pb)}; "
                f"unbound: {ub_str}"
            )

        case OutsideFragment(classification=cls, reason=reason):
            return (
                f"OutsideFragment({cls.value}): {reason}"
                if reason
                else f"OutsideFragment({cls.value})"
            )

        case _:
            return repr(outcome)


def format_classify_decision(decision: ClassifyDecision) -> str:
    """User-friendly string for a ClassifyDecision."""
    target_str = decision.target.value
    if decision.reason is not None:
        return f"route={target_str} reason={decision.reason.value}"
    return f"route={target_str}"


def _fmt_term(t: Term) -> str:
    match t:
        case Var(name=n) | Meta(name=n):
            return n
        case Const(value=v):
            if isinstance(v, Fraction):
                return f"{v.numerator}/{v.denominator}" if v.denominator != 1 else str(v.numerator)
            return str(v)
        case Func(name=n, args=args):
            return f"{n}({', '.join(_fmt_term(a) for a in args)})"
    return repr(t)  # pragma: no cover
