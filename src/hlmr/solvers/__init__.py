"""solvers/ — typed bridge protocols and result ADTs.

This module defines the contracts that Z3 and SymPy bridges implement.
It contains ZERO solver-library imports (no z3, no sympy). Actual bridges
live in z3_bridge.py and sympy_bridge.py (future session).

The Dispatcher in dispatch/route.py imports only from here, never from
the real bridge implementations, so it stays solver-library-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Protocol, runtime_checkable

from hlmr.ir.formula import Atom, Equals


# ---------------------------------------------------------------------------
# Z3 result ADT (DISPATCH_DESIGN.md §5.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Z3Sat:
    """Z3 found a satisfying model.

    model maps meta-variable names (e.g. '?P') to ground numeric values.
    The dispatcher converts these to Const(int|Fraction) terms.
    """
    model: dict[str, int | Fraction] = field(hash=False)


@dataclass(frozen=True)
class Z3Unsat:
    """Z3 proved the constraints are unsatisfiable."""


@dataclass(frozen=True)
class Z3Unknown:
    """Z3 could not decide satisfiability (e.g. non-linear constraints)."""
    reason: str


@dataclass(frozen=True)
class Z3Timeout:
    """Z3 exceeded the time budget."""


Z3Result = Z3Sat | Z3Unsat | Z3Unknown | Z3Timeout


# ---------------------------------------------------------------------------
# SymPy result ADT (DISPATCH_DESIGN.md §5.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymPyFiniteRoots:
    """SymPy found a finite set of roots."""
    roots: tuple[int | Fraction, ...]


@dataclass(frozen=True)
class SymPyNoRealRoots:
    """SymPy determined the polynomial has no real roots."""


@dataclass(frozen=True)
class SymPyConditionSet:
    """SymPy returned a ConditionSet — could not reduce to explicit roots."""
    reason: str


@dataclass(frozen=True)
class SymPyError:
    """SymPy raised an unexpected error during evaluation."""
    msg: str


SymPyResult = SymPyFiniteRoots | SymPyNoRealRoots | SymPyConditionSet | SymPyError


# ---------------------------------------------------------------------------
# Bridge protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Z3Bridge(Protocol):
    """Protocol for the Z3 solver bridge.

    The dispatcher calls check() with a tuple of ground-or-meta arithmetic
    constraints and receives a typed Z3Result. The real bridge (z3_bridge.py)
    translates Atom/Equals IR nodes into z3 expressions inside a persistent
    z3.Context; the mock bridge (in tests) returns pre-configured results.
    """

    def check(
        self,
        constraints: tuple[Atom | Equals, ...],
        timeout_ms: int,
    ) -> Z3Result:
        ...


@runtime_checkable
class SymPyBridge(Protocol):
    """Protocol for the SymPy solver bridge.

    The dispatcher calls solveset() with a single root_of/2 or Equals goal
    and receives a typed SymPyResult. Stateless: each call is independent.
    """

    def solveset(
        self,
        goal: Atom | Equals,
    ) -> SymPyResult:
        ...


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "SymPyBridge",
    "SymPyConditionSet",
    "SymPyError",
    "SymPyFiniteRoots",
    "SymPyNoRealRoots",
    "SymPyResult",
    "Z3Bridge",
    "Z3Result",
    "Z3Sat",
    "Z3Timeout",
    "Z3Unknown",
    "Z3Unsat",
    # Real bridge classes (z3_bridge.py / sympy_bridge.py).
    # Imported here so callers can use `from hlmr.solvers import RealZ3Bridge`
    # without knowing which module they come from.
    "RealZ3Bridge",
    "RealSymPyBridge",
]


# Re-export the real bridge implementations under canonical names.
# The actual solver imports (z3, sympy) live only in the bridge modules.
def __getattr__(name: str):
    if name == "RealZ3Bridge":
        from hlmr.solvers.z3_bridge import Z3Bridge as _Z3Bridge
        return _Z3Bridge
    if name == "RealSymPyBridge":
        from hlmr.solvers.sympy_bridge import SymPyBridge as _SymPyBridge
        return _SymPyBridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
