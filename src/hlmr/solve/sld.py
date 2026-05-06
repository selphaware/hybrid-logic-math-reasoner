from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from hlmr.dispatch import RouteTarget
from hlmr.ir.formula import Atom, Equals, Func, Meta, Term, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.unify.substitution import Substitution, apply_to_formula
from hlmr.unify.unifier import unify_atoms


class FreshNameGen:
    """Session-scoped counter that produces unique fresh Meta names.

    Pass instances explicitly into resolve(); do not use a module-level
    singleton.  Two independent FreshNameGen instances have independent
    counters — useful for isolated tests.
    """

    def __init__(self) -> None:
        self._n: int = 0

    def fresh(self, base: str) -> str:
        """Return the next fresh name, e.g. 'X_1', 'X_2', ... for base 'X'."""
        self._n += 1
        return f"{base}_{self._n}"


@dataclass(frozen=True)
class ClauseResolvedStep:
    """An SLD step resolved by unifying the goal with a KB clause (M1 shape, renamed)."""

    goal_resolved: Atom | Equals          # goal after applying accumulated subst
    clause_used: Clause                   # clause as it appears in the KB
    clause_renamed: Clause                # clause with variables renamed apart
    unifier: Substitution = field(hash=False)  # accumulated subst after this step


@dataclass(frozen=True)
class DispatcherResolvedStep:
    """An SLD step resolved by the M2 dispatcher (arithmetic/solver path).

    Added in M2 — the dispatcher session populates these; M1 paths only
    ever produce ClauseResolvedStep.
    """

    goal_resolved: Atom | Equals          # post-substitution; may still contain metas
    ground_atom: Atom | Equals            # post-binding, fully ground arithEval target
    route: RouteTarget                    # Z3 or SYMPY (never KB or REJECTED)
    binding_added: Substitution = field(hash=False)  # what the solver added to subst
    solver_summary: str = ""              # for logging; not load-bearing


# Discriminated union of all SLD step variants.
# M1 callers construct only ClauseResolvedStep; M2 adds DispatcherResolvedStep.
# Pattern-match on the variant to dispatch; do not use isinstance chains.
SLDStep = ClauseResolvedStep | DispatcherResolvedStep


@dataclass(frozen=True)
class SLDState:
    """Current point in SLD resolution: remaining goals + accumulated substitution."""

    goals: tuple[Atom | Equals, ...]
    subst: Substitution = field(hash=False)
    history: tuple[ClauseResolvedStep | DispatcherResolvedStep, ...]


# ---------------------------------------------------------------------------
# Clause renaming helpers
# ---------------------------------------------------------------------------


def _vars_in_order(clause: Clause) -> list[str]:
    """Collect Var names from a clause in left-to-right appearance order, deduplicated.

    Deterministic ordering ensures predictable fresh-name assignment in tests.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def visit_term(t: Term) -> None:
        match t:
            case Var(name=name):
                if name not in seen:
                    seen.add(name)
                    ordered.append(name)
            case Func(args=args):
                for a in args:
                    visit_term(a)

    def visit_atom(a: Atom | Equals) -> None:
        match a:
            case Atom(args=args):
                for t in args:
                    visit_term(t)
            case Equals(lhs=lhs, rhs=rhs):
                visit_term(lhs)
                visit_term(rhs)

    visit_atom(clause.head)
    for lit in clause.body:
        visit_atom(lit)
    return ordered


def _rename_term(t: Term, var_map: dict[str, str]) -> Term:
    match t:
        case Var(name=name):
            return Meta(var_map[name])
        case Func(name=fname, args=args):
            new_args = tuple(_rename_term(a, var_map) for a in args)
            if new_args == args:
                return t
            return Func(fname, new_args)
        case _:
            return t  # Const or Meta — not renaming targets


def _rename_atom(a: Atom | Equals, var_map: dict[str, str]) -> Atom | Equals:
    match a:
        case Atom(pred=pred, args=args):
            new_args = tuple(_rename_term(t, var_map) for t in args)
            if new_args == args:
                return a
            return Atom(pred, new_args)
        case Equals(lhs=lhs, rhs=rhs):
            new_lhs = _rename_term(lhs, var_map)
            new_rhs = _rename_term(rhs, var_map)
            if new_lhs is lhs and new_rhs is rhs:
                return a
            return Equals(new_lhs, new_rhs)
        case _:  # pragma: no cover  # unreachable; Atom | Equals is closed
            raise TypeError(f"Unknown atom type: {type(a)}")


def _rename_clause(clause: Clause, gen: FreshNameGen) -> Clause:
    """Rename all Vars in clause to fresh Metas, lifting clause-level ∀ to search unknowns.

    This does two things at once: renames apart (each clause use gets unique
    Meta names so multiple uses of the same clause don't share variables) and
    lifts (Var is not a unification target; Meta is — renaming makes clause
    variables unifiable during SLD search).

    Same Var name across head and body gets the same fresh Meta.
    All-constant clauses (no Vars) are returned as the same object.
    """
    var_names = _vars_in_order(clause)
    if not var_names:
        return clause
    var_map: dict[str, str] = {name: "?" + gen.fresh(name) for name in var_names}
    new_head = _rename_atom(clause.head, var_map)
    new_body = tuple(_rename_atom(lit, var_map) for lit in clause.body)
    return Clause(clause.name, new_head, new_body)


# ---------------------------------------------------------------------------
# SLD step functions
# ---------------------------------------------------------------------------


def candidates(state: SLDState, kb: KnowledgeBase) -> list[Clause]:
    """Clauses whose head predicate key matches the first goal.

    Returns an empty list if there are no remaining goals.  Order matches
    the KB (determines REPL display order, so callers should not re-sort).
    """
    if not state.goals:
        return []
    return list(kb.matching(state.goals[0]))


def resolve(
    state: SLDState, clause: Clause, gen: FreshNameGen
) -> SLDState | None:
    """Apply one SLD resolution step using the given clause.

    Renames the clause apart, applies the accumulated substitution to the
    first goal (so prior bindings are visible), then unifies.  Returns the
    new state on success or None if there are no goals or unification fails.

    The accumulated substitution is threaded through unify_atoms so all
    prior bindings are respected.
    """
    if not state.goals:
        return None

    goal = state.goals[0]
    goal_applied = cast(Atom | Equals, apply_to_formula(state.subst, goal))

    renamed = _rename_clause(clause, gen)

    new_subst = unify_atoms(goal_applied, renamed.head, state.subst)
    if new_subst is None:
        return None

    new_goals = renamed.body + state.goals[1:]
    step = ClauseResolvedStep(
        goal_resolved=goal_applied,
        clause_used=clause,
        clause_renamed=renamed,
        unifier=new_subst,
    )
    return SLDState(new_goals, new_subst, state.history + (step,))
