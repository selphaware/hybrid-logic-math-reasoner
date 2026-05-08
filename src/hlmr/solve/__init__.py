from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.solve.render import RenderError, _saturate, render
from hlmr.solve.sld import (
    ClauseResolvedStep,
    DispatcherResolvedStep,
    FreshNameGen,
    SLDState,
    SLDStep,
    candidates,
    resolve,
)
from hlmr.unify.substitution import Substitution, apply_to_term, compose

if TYPE_CHECKING:
    from hlmr.dispatch.route import Dispatcher

__all__ = [
    "ClauseResolvedStep",
    "DispatcherResolvedStep",
    "FreshNameGen",
    "RenderError",
    "SLDState",
    "SLDStep",
    "candidates",
    "manual_solve",
    "render",
    "resolve",
]


def _query_meta_names(goal: Atom | Equals) -> set[str]:
    """Return the set of Meta names that appear directly in a query goal."""
    names: set[str] = set()

    def walk(t: Term) -> None:
        match t:
            case Meta(name=n):
                names.add(n)
            case Func(args=args):
                for a in args:
                    walk(a)

    match goal:
        case Atom(args=args):
            for a in args:
                walk(a)
        case Equals(lhs=lhs, rhs=rhs):
            walk(lhs)
            walk(rhs)
    return names


def _is_ground(t: Term) -> bool:
    """Return True if t contains no Meta nodes (is fully grounded)."""
    match t:
        case Meta():
            return False
        case Const() | Var():
            return True
        case Func(args=args):
            return all(_is_ground(a) for a in args)


def manual_solve(
    kb: KnowledgeBase,
    goal: Atom | Equals | tuple[Atom | Equals, ...],
    picker: Callable[[list[Clause], SLDState], int | None],
    dispatcher: Dispatcher | None = None,
    solver_picker: Callable[[tuple[Substitution, ...]], int | None] | None = None,
) -> tuple[Substitution, Proof] | tuple[Substitution, None] | None:
    """Run manual SLD resolution with a user-supplied clause picker.

    M1 mode (dispatcher=None): every goal goes through the picker.
    Behaviour is bit-for-bit identical to the pre-M2 implementation.
    All M1 tests pass unchanged.

    M2 mode (dispatcher provided): each goal is classified.
    KB-routed goals go through the picker (M1 path). Z3/SYMPY-routed
    goals go through dispatcher.dispatch().

    Returns:
      (saturated_subst, kernel_verified_proof) on full success.
      (saturated_subst, None) when goals resolved but proof can't be
        rendered (underdetermined, DispatcherResolvedStep in history,
        multi-goal query — renderer extension lands in Session 5).
      None when resolution fails (no clause, picker abort, NoSolution,
        OutsideFragment from dispatcher).

    Raises RenderError only if a KB-only single-goal proof fails
    kernel re-verification (indicates a renderer bug, not a user error).
    """
    # Normalise goal to a tuple. Track whether the caller passed a single
    # goal (M1 compat path) or a tuple (M2 multi-goal path).
    if isinstance(goal, (Atom, Equals)):
        original_goals: tuple[Atom | Equals, ...] = (goal,)
        is_tuple_goal = False
    else:
        original_goals = tuple(goal)
        is_tuple_goal = True

    state = SLDState(goals=original_goals, subst={}, history=())
    gen = FreshNameGen()

    while state.goals:
        current = state.goals[0]

        if dispatcher is None:
            # M1 mode: every goal through the KB clause-picker.
            cs = candidates(state, kb)
            if not cs:
                return None
            idx = picker(cs, state)
            if idx is None:
                return None
            new_state = resolve(state, cs[idx], gen)
            if new_state is None:
                return None
            state = new_state
        else:
            # M2 mode: classify first.
            from hlmr.dispatch import RouteTarget
            decision = dispatcher.classify(current, state.subst)

            if decision.target == RouteTarget.KB:
                # KB path — same as M1.
                cs = candidates(state, kb)
                if not cs:
                    return None
                idx = picker(cs, state)
                if idx is None:
                    return None
                new_state = resolve(state, cs[idx], gen)
                if new_state is None:
                    return None
                state = new_state
            else:
                # Dispatcher path (Z3, SYMPY, or REJECTED).
                result = dispatcher.dispatch(current, state.subst)

                from hlmr.dispatch import (
                    MultipleSolutions,
                    NoSolution,
                    OutsideFragment,
                    Underdetermined,
                    UniqueSolution,
                )

                if isinstance(result.outcome, NoSolution):
                    return None

                if isinstance(result.outcome, OutsideFragment):
                    # last_outside_fragment already set by dispatcher.dispatch()
                    return None

                if isinstance(result.outcome, Underdetermined):
                    sat = _saturate(state.subst)
                    return (sat, None)

                if isinstance(result.outcome, MultipleSolutions):
                    if solver_picker is None:
                        # No picker — can't choose; treat as no solution.
                        return None
                    solutions = result.outcome.solutions
                    chosen = solver_picker(solutions)
                    if chosen is None:
                        return None
                    binding = solutions[chosen]
                    step_to_append = result.outcome.steps[chosen]
                else:
                    # UniqueSolution (or InfinitelyManySolutions — treat same)
                    assert isinstance(result.outcome, UniqueSolution)
                    binding = result.outcome.binding
                    step_to_append = result.step  # set on UniqueSolution

                new_subst = compose(state.subst, binding)
                new_history = state.history + (step_to_append,)
                state = SLDState(
                    goals=state.goals[1:],
                    subst=new_subst,
                    history=new_history,
                )

    sat = _saturate(state.subst)

    # M1 underdetermined check: query metas must be grounded.
    first_goal = original_goals[0]
    query_metas = _query_meta_names(first_goal)
    if any(not _is_ground(apply_to_term(sat, Meta(n))) for n in query_metas):
        return (sat, None)
    # Extended underdetermined check: resolution-internal metas must be ground.
    if any(not _is_ground(v) for v in sat.values()):
        return (sat, None)

    # Determine render path.
    has_dispatcher_steps = any(
        isinstance(step, DispatcherResolvedStep)
        for step in state.history
    )
    if has_dispatcher_steps or is_tuple_goal:
        # Renderer extension (M2 Task C / Session 5) not yet available.
        # Return (sat, None) so callers that only need the substitution
        # can proceed; callers that need a proof must wait for Session 5.
        return (sat, None)

    # KB-only single-goal path: render and kernel-verify normally.
    proof = render(state, kb, first_goal)
    if not isinstance(check_proof(proof), Verified):
        raise RenderError("rendered proof rejected by kernel — renderer bug")
    return (sat, proof)
