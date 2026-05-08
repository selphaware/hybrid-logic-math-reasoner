"""dispatch/ — public API surface for the M2 dispatcher.

This module exports the outcome ADT, classification types, RouteTarget,
and (from route.py) the Dispatcher class and exception types.

Session 4a: OutsideFragmentReason, the six outcome dataclasses,
            DispatchOutcome, ClassifyDecision, DispatchResult.
Session 4b: Dispatcher, SolverKernelDisagreement, DispatchError
            (re-exported from route.py; imported lazily to avoid cycles).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from hlmr.unify.substitution import Substitution

# DispatcherResolvedStep is used in MultipleSolutions.steps and DispatchResult.step.
# The import is TYPE_CHECKING-only to avoid the circular import:
#   dispatch/__init__.py → solve/sld.py → dispatch/__init__.py
# At runtime, the frozen dataclasses hold the correct value; type checkers
# (mypy, pyright) see the import via TYPE_CHECKING.
if TYPE_CHECKING:
    from hlmr.solve.sld import DispatcherResolvedStep


# ---------------------------------------------------------------------------
# Route targets and the reason enum
# ---------------------------------------------------------------------------


class RouteTarget(Enum):
    KB = "kb"               # M1 SLD path; not handled by the Dispatcher class
    Z3 = "z3"               # linear arithmetic, finite domains
    SYMPY = "sympy"         # symbolic algebraic equations
    REJECTED = "rejected"   # OutsideFragment — classifier refuses to route


class OutsideFragmentReason(Enum):
    TRANSCENDENTAL = "transcendental"
    CONTESTED_CONVENTION = "contested_convention"
    UNRECOGNISED_SHAPE = "unrecognised_shape"
    NON_LINEAR_BEYOND_SYMPY = "non_linear_beyond_sympy"
    SOLVER_TIMEOUT = "solver_timeout"
    SOLVER_UNKNOWN = "solver_unknown"


# ---------------------------------------------------------------------------
# The six outcome dataclasses (DISPATCH_DESIGN.md §3.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UniqueSolution:
    """The constraint has exactly one satisfying assignment.
    binding maps query-meta names to ground terms."""

    binding: Substitution = field(hash=False)


@dataclass(frozen=True)
class MultipleSolutions:
    """The constraint has finitely many *verified valid* satisfying
    assignments, all enumerated. solutions is non-empty (≥2 entries).

    steps is paired one-to-one with solutions: steps[i] is the
    pre-verified DispatcherResolvedStep that the renderer would
    walk if the user picks solutions[i].

    Partitioning of bridge-returned witnesses (§5.3 / §7 / §12.6).
    When the bridge returns a candidate root set, the dispatcher
    runs verify-before-return (§5.4) on each candidate and
    partitions the results into three classes:

      (a) Verified valid — arithEval accepts the constructed
          ground atom. The witness joins the solutions/steps arrays.
      (b) Case 2 — verify rejects with MalformedArithmetic on a
          contested-shape ground atom (currently `0^0` per
          ARITH_EVAL_DESIGN.md §11.3 M14; see §7.3 for the
          contested-shape detector). The witness is logged as a
          contested rejection (informational, surfaced in the REPL
          — see §12.6) and DROPPED from the result. It does not
          join solutions/steps.
      (c) Case 1 — verify rejects with EvaluationFalse, or with
          MalformedArithmetic on a non-contested shape (§7.2).
          This is a true solver/kernel disagreement — the
          dispatcher CRASHES via SolverKernelDisagreement. No
          partial result is returned.

    Outcome narrowing on the count of (a):
      0 valid → outcome becomes NoSolution()
      1 valid → outcome becomes UniqueSolution(binding=…)
                with step = the single pre-built step
      ≥2 valid → outcome stays MultipleSolutions(solutions, steps)

    This means a MultipleSolutions outcome reaching the caller
    always carries ≥2 verified valid witnesses; partial-contested
    inputs that reduce the valid set to <2 are silently narrowed
    to a more specific outcome. §12.6 walks through the canonical
    example (?X^?X = 1 with bridge-roots {1, 0} → ?X=0 dropped as
    Case 2 → outcome narrows to UniqueSolution({?X: 1}))."""

    solutions: tuple[Substitution, ...] = field(hash=False)
    steps: tuple[DispatcherResolvedStep, ...]


@dataclass(frozen=True)
class InfinitelyManySolutions:
    """The constraint admits infinitely many satisfying assignments.
    example is one such; free_metas lists which meta names remain
    unbound when example is applied."""

    example: Substitution = field(hash=False)
    free_metas: tuple[str, ...]


@dataclass(frozen=True)
class NoSolution:
    """The constraint is unsatisfiable. The dispatcher reports this
    as the resolved outcome for that goal — the caller decides
    whether to backtrack via 'back' or abort."""


@dataclass(frozen=True)
class Underdetermined:
    """The constraint admits a binding for some metas but leaves
    others structurally unbound (chains of metas that never resolve
    to ground terms). Generalises M1's HARDENING_FINDINGS.md
    universal-fact case to cover solver-side underdetermination too.

    partial_binding is the saturated substitution from the solver
    (or from SLD, in the M1-universal-fact case). unbound names the
    metas in the original query that, after applying partial_binding
    and saturating, still resolve to a Meta rather than a ground
    term."""

    partial_binding: Substitution = field(hash=False)
    unbound: tuple[str, ...]


@dataclass(frozen=True)
class OutsideFragment:
    """The constraint is outside HLMR's M2 decidable fragment. The
    classification field names the specific reason (used for
    logging, REPL display, and dispatch-test assertions). reason is
    a free-form human-readable message."""

    classification: OutsideFragmentReason
    reason: str


# Discriminated union of all six outcomes.
DispatchOutcome = (
    UniqueSolution
    | MultipleSolutions
    | InfinitelyManySolutions
    | NoSolution
    | Underdetermined
    | OutsideFragment
)


# ---------------------------------------------------------------------------
# Classification types (DISPATCH_DESIGN.md §3.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifyDecision:
    """The classifier's pure verdict on a single goal.

    Produced by classify(); consumed by Dispatcher.dispatch().
    No solver calls were made to produce this."""

    target: RouteTarget
    reason: OutsideFragmentReason | None = None
    detail: str = ""


# ---------------------------------------------------------------------------
# DispatchResult (DISPATCH_DESIGN.md §3.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchResult:
    """Thin wrapper combining the classify decision, the routing outcome,
    and (on UniqueSolution) the DispatcherResolvedStep the renderer walks.

    step is set ONLY for UniqueSolution (one witness, one step).
    For MultipleSolutions, the per-solution steps live on outcome.steps
    (paired with outcome.solutions); manual_solve picks the chosen step.
    For NoSolution, Underdetermined, and OutsideFragment, step is None —
    the renderer is not invoked on those paths."""

    decision: ClassifyDecision
    outcome: DispatchOutcome
    step: DispatcherResolvedStep | None


# ---------------------------------------------------------------------------
# Re-export Dispatcher, DispatchError, SolverKernelDisagreement from route.py.
# This import is deferred to avoid the circular route.py → dispatch/__init__.py
# → route.py chain. Use TYPE_CHECKING for type annotations; for runtime use,
# callers import directly from hlmr.dispatch.route.
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from hlmr.dispatch.route import DispatchError, Dispatcher, SolverKernelDisagreement


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "ClassifyDecision",
    "DispatchError",
    "DispatchOutcome",
    "DispatchResult",
    "Dispatcher",
    "InfinitelyManySolutions",
    "MultipleSolutions",
    "NoSolution",
    "OutsideFragment",
    "OutsideFragmentReason",
    "RouteTarget",
    "SolverKernelDisagreement",
    "Underdetermined",
    "UniqueSolution",
]
