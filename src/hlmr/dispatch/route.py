"""dispatch/route.py — the Dispatcher class.

Routes classified goals to Z3 or SymPy bridges, verifies every witness
through check_proof before returning, and applies the Case 1 / Case 2
discriminator per DISPATCH_DESIGN.md §7.

Import constraints (enforced by test_kernel_isolation.py and by code review):
  - Imports hlmr.kernel only via check_proof (the public API).
  - Never imports _eval_term or _eval_atom.
  - Never imports z3 or sympy directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from fractions import Fraction

from hlmr.dispatch import (
    ClassifyDecision,
    DispatchOutcome,
    DispatchResult,
    InfinitelyManySolutions,
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    OutsideFragmentReason,
    RouteTarget,
    Underdetermined,
    UniqueSolution,
)
from hlmr.dispatch.classify import _is_contested_when_ground, classify
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.ir.justification import RuleApp
from hlmr.ir.kb import KnowledgeBase
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import (
    CheckFailure,
    EvaluationFalse,
    MalformedArithmetic,
    Verified,
)
from hlmr.log.recorder import SessionRecorder
from hlmr.solve.sld import DispatcherResolvedStep
from hlmr.solvers import (
    SymPyBridge,
    SymPyConditionSet,
    SymPyError,
    SymPyFiniteRoots,
    SymPyNoRealRoots,
    Z3Bridge,
    Z3Sat,
    Z3Timeout,
    Z3Unknown,
    Z3Unsat,
)
from hlmr.unify.substitution import Substitution, apply_to_formula, apply_to_term, compose


# ---------------------------------------------------------------------------
# Exception types
# ---------------------------------------------------------------------------


class DispatchError(Exception):
    """Generic dispatcher error (KB-routed goal reached dispatcher, bridge
    crash, etc.)."""


class SolverKernelDisagreement(Exception):
    """Case 1 — the solver returned a witness that the kernel rejects on a
    non-contested shape. Development-time crash. Per prd.md §4 the kernel is
    the sole arbiter of correctness."""


# ---------------------------------------------------------------------------
# Internal result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifyResult:
    """Result of _verify_arith_ground — thin wrapper over check_proof output."""

    ok: bool
    error_class: type | None  # MalformedArithmetic | EvaluationFalse | None
    formula: Atom | Equals

    @classmethod
    def from_check_result(
        cls, r: object, formula: Atom | Equals
    ) -> VerifyResult:
        if isinstance(r, Verified):
            return cls(ok=True, error_class=None, formula=formula)
        # CheckFailure
        assert isinstance(r, CheckFailure)
        return cls(ok=False, error_class=type(r.reason), formula=formula)


# ---------------------------------------------------------------------------
# The contested-shape post-filter (DISPATCH_DESIGN.md §7.3)
# ---------------------------------------------------------------------------


def _ground_atom_lands_on_contested_shape(f: Atom | Equals) -> bool:
    """True iff f contains a ground 0^0 subterm in any argument position.

    Reuses classify._is_contested_when_ground for the term walk to keep
    the classify-side pre-filter and verify-time post-filter in lock-step
    (DISPATCH §7.3 KEY DESIGN POINT). Extend classify._is_contested_when_ground
    when a new contested case is added; this function tracks it automatically.
    """
    match f:
        case Atom(args=args):
            return any(_is_contested_when_ground(a) for a in args)
        case Equals(lhs=lhs, rhs=rhs):
            return _is_contested_when_ground(lhs) or _is_contested_when_ground(rhs)
        case _:  # pragma: no cover
            return False


# ---------------------------------------------------------------------------
# Helpers for root_of verify-atom construction (DISPATCH §5.3)
# ---------------------------------------------------------------------------


def _polynomial_var(poly: Term) -> Var | Meta | None:
    """Return the single Var or Meta in poly, or None if there's none or >1."""
    found: set[str] = set()
    kind: dict[str, type] = {}

    def walk(t: Term) -> None:
        match t:
            case Var(name=n):
                found.add(n)
                kind[n] = Var
            case Meta(name=n):
                found.add(n)
                kind[n] = Meta
            case Func(args=args):
                for a in args:
                    walk(a)

    walk(poly)
    if len(found) != 1:
        return None
    name = next(iter(found))
    cls = kind[name]
    return cls(name)


def _subst_var_in_term(poly: Term, var_name: str, replacement: Term) -> Term:
    """Substitute `replacement` for every Var(var_name) in poly."""
    match poly:
        case Var(name=n) if n == var_name:
            return replacement
        case Meta(name=n) if n == var_name:
            return replacement
        case Func(name=fname, args=args):
            new_args = tuple(_subst_var_in_term(a, var_name, replacement) for a in args)
            if new_args == args:
                return poly
            return Func(fname, new_args)
        case _:
            return poly


def _construct_verify_atom(
    goal: Atom | Equals,
    binding: Substitution,
) -> Atom | Equals:
    """Build the ground atom that arithEval will verify.

    For most goals: apply binding to goal directly.
    For root_of(target, poly): substitute the bound root into the polynomial
    and assert equality to zero (DISPATCH §5.3 verify-atom construction block).
    """
    match goal:
        case Atom(pred="root_of", args=(target, poly)):
            root_term = apply_to_term(binding, target)
            pvar = _polynomial_var(poly)
            if pvar is None:
                # Fallback: poly is a constant; just verify as Equals(poly, 0)
                return Equals(poly, Const(0))
            instantiated = _subst_var_in_term(poly, pvar.name, root_term)
            return Equals(instantiated, Const(0))
        case _:
            result = apply_to_formula(binding, goal)
            assert isinstance(result, (Atom, Equals))
            return result


# ---------------------------------------------------------------------------
# Free-meta detection helpers (for underdetermination check, DISPATCH §5.2.e)
# ---------------------------------------------------------------------------


def _meta_names_in_term(t: Term) -> set[str]:
    """Collect all Meta names in t."""
    found: set[str] = set()

    def walk(x: Term) -> None:
        match x:
            case Meta(name=n):
                found.add(n)
            case Func(args=args):
                for a in args:
                    walk(a)

    walk(t)
    return found


def _meta_names_in_formula(f: Atom | Equals) -> set[str]:
    match f:
        case Atom(args=args):
            result: set[str] = set()
            for a in args:
                result |= _meta_names_in_term(a)
            return result
        case Equals(lhs=lhs, rhs=rhs):
            return _meta_names_in_term(lhs) | _meta_names_in_term(rhs)
        case _:  # pragma: no cover
            return set()


def _negate_z3_model(model: dict[str, int | Fraction]) -> Atom | Equals:
    """Construct a formula asserting NOT(all bindings in model hold simultaneously).

    For underdetermination detection: if a second model satisfies the constraints
    AND this negation, the first model is not unique.

    Simple implementation: negate the conjunction by asserting at least one
    differs. We express this as a disjunction; since Z3Bridge takes a tuple of
    constraints (conjunction), we approximate by negating one key binding.
    Full negation would need OR, which isn't in our IR. So: for each binding
    ?X=v, add constraint ?X != v. The caller checks if ANY second sat exists
    after adding all these negations.
    """
    # Return a list of "?X != v" atoms for each binding.
    # _dispatch_z3 calls this and passes them as additional constraints.
    raise NotImplementedError("_negate_z3_model returns list; use _build_negation_constraints")


def _build_negation_constraints(
    model: dict[str, int | Fraction]
) -> tuple[Atom | Equals, ...]:
    """Build inequality constraints that negate every binding in model.

    Used in the add-negation-and-recheck step (DISPATCH §5.2.e) to detect
    whether the Z3 result is underdetermined.
    """
    constraints: list[Atom | Equals] = []
    for meta_name, value in model.items():
        if isinstance(value, int):
            val_term: Term = Const(value)
        else:
            val_term = Const(value)
        constraints.append(Atom("!=", (Meta(meta_name), val_term)))
    return tuple(constraints)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


@dataclass
class Dispatcher:
    """Stateful dispatcher; one per REPL session.

    Owns references to Z3 and SymPy bridges; a KnowledgeBase (for predicate
    classification); an optional SessionRecorder; and a timeout in ms.

    last_outside_fragment is set whenever dispatch() returns an OutsideFragment
    outcome — the REPL polls it to display a helpful rejection message.
    """

    z3_bridge: Z3Bridge
    sympy_bridge: SymPyBridge
    kb: KnowledgeBase
    logger: SessionRecorder | None = None
    timeout_ms: int = 5000

    last_outside_fragment: OutsideFragment | None = field(
        default=None, init=False
    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self, goal: Atom | Equals, subst: Substitution
    ) -> ClassifyDecision:
        """Re-export of classify.classify() bound to self.kb."""
        return classify(goal, subst, self.kb)

    def dispatch(
        self, goal: Atom | Equals, subst: Substitution
    ) -> DispatchResult:
        """Classify + route + verify per DISPATCH §5.1."""
        g = apply_to_formula(subst, goal)
        assert isinstance(g, (Atom, Equals))

        decision = classify(g, subst, self.kb)
        self._log_classify(g, decision)

        match decision.target:
            case RouteTarget.KB:
                raise DispatchError(
                    f"KB-classified goal reached dispatcher: {g!r}. "
                    "Caller (manual_solve) should route KB goals through "
                    "the clause-picker loop, not the dispatcher."
                )
            case RouteTarget.REJECTED:
                outcome = OutsideFragment(
                    classification=decision.reason,  # type: ignore[arg-type]
                    reason=decision.detail or "rejected by classifier",
                )
                self.last_outside_fragment = outcome
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)
            case RouteTarget.Z3:
                return self._dispatch_z3(g, decision, subst)
            case RouteTarget.SYMPY:
                return self._dispatch_sympy(g, decision, subst)

    # ------------------------------------------------------------------
    # Z3 dispatch path (DISPATCH §5.2)
    # ------------------------------------------------------------------

    def _dispatch_z3(
        self,
        goal: Atom | Equals,
        decision: ClassifyDecision,
        subst: Substitution,
    ) -> DispatchResult:
        # Collect meta names in the goal (post-subst application).
        original_metas = _meta_names_in_formula(goal)

        # Ground-atom short-circuit (DISPATCH §11.5): if fully ground, verify
        # directly without calling Z3. False → NoSolution (no solver witness
        # to blame for Case 1); contested shape → OutsideFragment.
        if not original_metas:
            verify = self._verify_arith_ground(goal)
            if verify.ok:
                step = self._make_step(
                    goal, goal, RouteTarget.Z3, {},
                    "ground (no metas; short-circuited)",
                )
                outcome: DispatchOutcome = UniqueSolution(binding={})
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=step)
            # Ground atom is false or malformed. Not a solver/kernel disagreement
            # (no solver was involved). Check contested shape for CONTESTED_CONVENTION;
            # all other failures map to NoSolution.
            if _ground_atom_lands_on_contested_shape(goal):
                out = OutsideFragment(
                    classification=OutsideFragmentReason.CONTESTED_CONVENTION,
                    reason=(
                        f"Goal {goal!r} depends on a contested mathematical "
                        f"convention (currently 0^0; see "
                        f"docs/strategic_direction.md §6.9)."
                    ),
                )
                self.last_outside_fragment = out
                self._log_outcome(out)
                return DispatchResult(decision=decision, outcome=out, step=None)
            out_ns: DispatchOutcome = NoSolution()
            self._log_outcome(out_ns)
            return DispatchResult(decision=decision, outcome=out_ns, step=None)

        # Non-ground: call Z3.
        constraints = (goal,)
        self._log_route(goal, RouteTarget.Z3)
        t0 = time.monotonic()
        z3_result = self.z3_bridge.check(constraints, timeout_ms=self.timeout_ms)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self._log_solver_call("z3", constraints, elapsed_ms)
        self._log_solver_result("z3", z3_result)

        match z3_result:
            case Z3Sat(model=model):
                binding = self._z3_model_to_subst(model)

                # Underdetermination check via add-negation-and-recheck
                # (DISPATCH §5.2.e). Recheck whenever the goal has multiple
                # free metas (multi-variable constraints are typically
                # underdetermined) OR when some meta is absent from the model.
                if len(original_metas) > 1 or self._has_free_metas_in_model(model, original_metas):
                    neg_constraints = _build_negation_constraints(model)
                    second = self.z3_bridge.check(
                        constraints + neg_constraints,
                        timeout_ms=self.timeout_ms,
                    )
                    if isinstance(second, Z3Sat):
                        # A second model exists → underdetermined.
                        unbound = tuple(
                            n for n in original_metas
                            if n not in model or isinstance(model.get(n), Meta)
                        )
                        outcome = Underdetermined(
                            partial_binding=binding,
                            unbound=unbound if unbound else tuple(original_metas),
                        )
                        self._log_outcome(outcome)
                        return DispatchResult(
                            decision=decision, outcome=outcome, step=None
                        )
                    # else: first model IS unique; fall through.

                ground = _construct_verify_atom(goal, binding)
                verify = self._verify_arith_ground(ground)
                result = self._classify_verify_result(
                    verify, ground, decision, binding,
                    route=RouteTarget.Z3,
                    solver_summary=str(model),
                    original_goal=goal,
                    subst_extension=binding,
                )
                self._log_outcome(result.outcome)
                return result

            case Z3Unsat():
                outcome = NoSolution()
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

            case Z3Unknown(reason=reason):
                outcome = OutsideFragment(
                    classification=OutsideFragmentReason.SOLVER_UNKNOWN,
                    reason=f"Z3 returned unknown: {reason}",
                )
                self.last_outside_fragment = outcome
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

            case Z3Timeout():
                outcome = OutsideFragment(
                    classification=OutsideFragmentReason.SOLVER_TIMEOUT,
                    reason=f"Z3 timed out after {self.timeout_ms}ms",
                )
                self.last_outside_fragment = outcome
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

    # ------------------------------------------------------------------
    # SymPy dispatch path (DISPATCH §5.3)
    # ------------------------------------------------------------------

    def _dispatch_sympy(
        self,
        goal: Atom | Equals,
        decision: ClassifyDecision,
        subst: Substitution,
    ) -> DispatchResult:
        # Identify the target meta (first arg of root_of, or lhs of Equals).
        target_meta = self._sympy_target_meta(goal)

        self._log_route(goal, RouteTarget.SYMPY)
        t0 = time.monotonic()
        sp_result = self.sympy_bridge.solveset(goal)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self._log_solver_call("sympy", (goal,), elapsed_ms)
        self._log_solver_result("sympy", sp_result)

        match sp_result:
            case SymPyFiniteRoots(roots=roots) if len(roots) == 1:
                binding = self._sympy_root_to_subst(roots[0], target_meta)
                ground = _construct_verify_atom(goal, binding)
                verify = self._verify_arith_ground(ground)
                result = self._classify_verify_result(
                    verify, ground, decision, binding,
                    route=RouteTarget.SYMPY,
                    solver_summary=f"sympy: {roots}",
                    original_goal=goal,
                    subst_extension=binding,
                )
                self._log_outcome(result.outcome)
                return result

            case SymPyFiniteRoots(roots=roots) if len(roots) > 1:
                return self._dispatch_sympy_multi_root(
                    goal, decision, roots, target_meta
                )

            case SymPyFiniteRoots():
                # Empty roots tuple → no solution
                outcome = NoSolution()
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

            case SymPyNoRealRoots():
                outcome = NoSolution()
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

            case SymPyConditionSet(reason=reason):
                outcome = OutsideFragment(
                    classification=OutsideFragmentReason.NON_LINEAR_BEYOND_SYMPY,
                    reason=f"SymPy returned ConditionSet: {reason}",
                )
                self.last_outside_fragment = outcome
                self._log_outcome(outcome)
                return DispatchResult(decision=decision, outcome=outcome, step=None)

            case SymPyError(msg=msg):
                raise DispatchError(f"SymPy bridge error: {msg}")

    def _dispatch_sympy_multi_root(
        self,
        goal: Atom | Equals,
        decision: ClassifyDecision,
        roots: tuple[int | Fraction, ...],
        target_meta: str | None,
    ) -> DispatchResult:
        """Partition multiple SymPy roots per DISPATCH §3.1 / §5.3."""
        valid_bindings: list[Substitution] = []
        valid_steps: list[DispatcherResolvedStep] = []

        for i, root in enumerate(roots):
            b = self._sympy_root_to_subst(root, target_meta)
            ga = _construct_verify_atom(goal, b)
            vr = self._verify_arith_ground(ga)

            if vr.ok:
                step = self._make_step(
                    goal, ga, RouteTarget.SYMPY, b,
                    solver_summary=f"sympy: {roots}; witness {i}",
                )
                valid_bindings.append(b)
                valid_steps.append(step)
                continue

            # vr.ok is False — discriminate Case 1 vs Case 2.
            if (
                vr.error_class is MalformedArithmetic
                and _ground_atom_lands_on_contested_shape(ga)
            ):
                # Case 2 — contested convention; log and drop.
                self._log_contested_rejection(ga, RouteTarget.SYMPY, b)
                continue

            # Case 1 — disagreement on non-contested shape. Crash via
            # _classify_verify_result (which always raises for Case 1).
            self._classify_verify_result(
                vr, ga, decision, b,
                route=RouteTarget.SYMPY,
                solver_summary=f"sympy: {roots}; witness {i}",
                original_goal=goal,
                subst_extension=b,
            )
            # _classify_verify_result raises; this line is unreachable.
            raise DispatchError(  # pragma: no cover
                "_classify_verify_result must raise for Case 1 — got fall-through"
            )

        # Outcome narrowing per §3.1.
        n_valid = len(valid_bindings)
        if n_valid == 0:
            outcome: DispatchOutcome = NoSolution()
            self._log_outcome(outcome)
            return DispatchResult(decision=decision, outcome=outcome, step=None)
        if n_valid == 1:
            outcome = UniqueSolution(binding=valid_bindings[0])
            self._log_outcome(outcome)
            return DispatchResult(
                decision=decision,
                outcome=outcome,
                step=valid_steps[0],
            )
        # ≥2 valid witnesses.
        outcome = MultipleSolutions(
            solutions=tuple(valid_bindings),
            steps=tuple(valid_steps),
        )
        self._log_outcome(outcome)
        return DispatchResult(decision=decision, outcome=outcome, step=None)

    # ------------------------------------------------------------------
    # Verify-before-return (DISPATCH §5.4)
    # ------------------------------------------------------------------

    def _verify_arith_ground(
        self, ground_atom: Atom | Equals
    ) -> VerifyResult:
        """Build a one-line Proof and run it through check_proof.

        Goes through the public check_proof API only — never through
        _eval_term / _eval_atom (DISPATCH §5.4, ARITH_EVAL_DESIGN §8.3).
        """
        line = ProofLine(
            number=1,
            formula=ground_atom,
            justification=RuleApp("arithEval", (), (), {}),
            box_depth=0,
        )
        one_line = Proof(lines=(line,), goal=ground_atom)
        result = check_proof(one_line)
        vr = VerifyResult.from_check_result(result, ground_atom)
        self._log_verify(ground_atom, vr)
        return vr

    # ------------------------------------------------------------------
    # Case 1 / Case 2 discriminator (DISPATCH §7.2)
    # ------------------------------------------------------------------

    def _classify_verify_result(
        self,
        verify: VerifyResult,
        ground: Atom | Equals,
        decision: ClassifyDecision,
        binding: Substitution,
        *,
        route: RouteTarget,
        solver_summary: str,
        original_goal: Atom | Equals,
        subst_extension: Substitution,
    ) -> DispatchResult:
        if verify.ok:
            step = self._make_step(
                original_goal, ground, route, binding, solver_summary
            )
            return DispatchResult(
                decision=decision,
                outcome=UniqueSolution(binding=subst_extension),
                step=step,
            )

        # verify.ok is False.
        if verify.error_class is EvaluationFalse:
            # Case 1 — true disagreement. Crash.
            raise SolverKernelDisagreement(
                f"Solver via {route.value} returned witness {binding!r} "
                f"for goal {original_goal!r}; arithEval rejects the resulting "
                f"ground atom {ground!r} with EvaluationFalse. This is a "
                f"development-time crash. Investigate the bridge translation "
                f"or the solver's witness."
            )

        # verify.error_class is MalformedArithmetic.
        if _ground_atom_lands_on_contested_shape(ground):
            # Case 2 — sound rejection on contested content.
            self._log_contested_rejection(ground, route, binding)
            outcome = OutsideFragment(
                classification=OutsideFragmentReason.CONTESTED_CONVENTION,
                reason=(
                    f"Goal resolves to {ground!r} which depends on a contested "
                    f"mathematical convention (currently 0^0; see "
                    f"docs/strategic_direction.md §6.9). The kernel does not "
                    f"commit to a value here; M3+ theory seeds may declare this "
                    f"as an axiom (e.g. `axiom pow_zero_zero: 0^0 = 1`)."
                ),
            )
            self.last_outside_fragment = outcome
            return DispatchResult(decision=decision, outcome=outcome, step=None)

        # MalformedArithmetic on a non-contested shape — Case 1. Crash.
        raise SolverKernelDisagreement(
            f"Solver via {route.value} returned witness {binding!r} "
            f"for goal {original_goal!r}; arithEval rejects the resulting "
            f"ground atom {ground!r} with MalformedArithmetic on a shape "
            f"that is fully within the evaluable set. This is a bridge "
            f"translation bug or a kernel bug. Investigate."
        )

    # ------------------------------------------------------------------
    # Step construction (DISPATCH §5.5)
    # ------------------------------------------------------------------

    def _make_step(
        self,
        goal: Atom | Equals,
        ground: Atom | Equals,
        route: RouteTarget,
        binding: Substitution,
        solver_summary: str,
    ) -> DispatcherResolvedStep:
        return DispatcherResolvedStep(
            goal_resolved=goal,
            ground_atom=ground,
            route=route,
            binding_added=binding,
            solver_summary=solver_summary,
        )

    # ------------------------------------------------------------------
    # Z3 result helpers
    # ------------------------------------------------------------------

    def _z3_model_to_subst(
        self, model: dict[str, int | Fraction]
    ) -> Substitution:
        """Convert a Z3 model dict to a Substitution."""
        return {
            name: Const(value)
            for name, value in model.items()
        }

    def _has_free_metas_in_model(
        self,
        model: dict[str, int | Fraction],
        original_metas: set[str],
    ) -> bool:
        """True iff any meta from original_metas is absent from the model.

        Z3 may assign arbitrary values to unconstrained metas; if the meta
        doesn't appear in the model at all, we treat it as free.
        """
        return any(m not in model for m in original_metas)

    # ------------------------------------------------------------------
    # SymPy result helpers
    # ------------------------------------------------------------------

    def _sympy_target_meta(self, goal: Atom | Equals) -> str | None:
        """Return the name of the meta being solved for in a SymPy goal."""
        match goal:
            case Atom(pred="root_of", args=(target, _)):
                if isinstance(target, Meta):
                    return target.name
                return None
            case Equals(lhs=Meta(name=n)):
                return n
            case Equals(rhs=Meta(name=n)):
                return n
            case _:
                return None

    def _sympy_root_to_subst(
        self,
        root: int | Fraction,
        target_meta: str | None,
    ) -> Substitution:
        """Convert a single SymPy root to a Substitution."""
        if target_meta is None:
            return {}
        return {target_meta: Const(root)}

    # ------------------------------------------------------------------
    # Logging helpers (DISPATCH §10)
    # ------------------------------------------------------------------

    def _log_classify(
        self, goal: Atom | Equals, decision: ClassifyDecision
    ) -> None:
        if self.logger is None:
            return
        try:
            self.logger._write_v2_event("dispatch_classify", {
                "goal": str(goal),
                "decision": {
                    "target": decision.target.value,
                    "reason": decision.reason.value if decision.reason else None,
                    "detail": decision.detail,
                },
            })
        except Exception:
            pass

    def _log_route(self, goal: Atom | Equals, target: RouteTarget) -> None:
        if self.logger is None:
            return
        try:
            self.logger._write_v2_event("dispatch_route", {
                "goal": str(goal),
                "target": target.value,
                "timeout_ms": self.timeout_ms,
            })
        except Exception:
            pass

    def _log_solver_call(
        self,
        solver: str,
        constraints: tuple[Atom | Equals, ...],
        elapsed_ms: int,
    ) -> None:
        if self.logger is None:
            return
        try:
            self.logger._write_v2_event("solver_call", {
                "solver": solver,
                "constraints": str(constraints),
                "elapsed_ms": elapsed_ms,
            })
        except Exception:
            pass

    def _log_solver_result(self, solver: str, result: object) -> None:
        if self.logger is None:
            return
        try:
            self.logger._write_v2_event("solver_result", {
                "solver": solver,
                "result_kind": type(result).__name__,
                "summary": repr(result)[:200],
            })
        except Exception:
            pass

    def _log_verify(
        self, ground: Atom | Equals, vr: VerifyResult
    ) -> None:
        if self.logger is None:
            return
        try:
            if vr.ok:
                result_str = "ok"
            elif vr.error_class is EvaluationFalse:
                result_str = "evaluation_false"
            else:
                result_str = "malformed_arithmetic"
            self.logger._write_v2_event("verify_arith", {
                "ground_atom": str(ground),
                "result": result_str,
            })
        except Exception:
            pass

    def _log_outcome(self, outcome: DispatchOutcome) -> None:
        if self.logger is None:
            return
        try:
            payload: dict = {"outcome_kind": type(outcome).__name__}
            match outcome:
                case UniqueSolution(binding=b):
                    payload["binding"] = {k: str(v) for k, v in b.items()}
                case OutsideFragment(classification=cls):
                    payload["outside_fragment_reason"] = cls.value
                case Underdetermined(unbound=ub):
                    payload["free_metas"] = list(ub)
                case _:
                    pass
            self.logger._write_v2_event("dispatch_outcome", payload)
        except Exception:
            pass

    def _log_contested_rejection(
        self,
        ground: Atom | Equals,
        route: RouteTarget,
        binding: Substitution,
    ) -> None:
        if self.logger is None:
            return
        try:
            self.logger._write_v2_event("contested_rejection", {
                "ground_atom": str(ground),
                "route": route.value,
                "binding": {k: str(v) for k, v in binding.items()},
            })
        except Exception:
            pass
