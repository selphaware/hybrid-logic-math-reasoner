from collections.abc import Callable

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
from hlmr.unify.substitution import Substitution, apply_to_term

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
    goal: Atom | Equals,
    picker: Callable[[list[Clause], SLDState], int | None],
) -> tuple[Substitution, Proof] | tuple[Substitution, None] | None:
    """Run manual SLD resolution with a user-supplied clause picker.

    Returns (saturated_subst, kernel_verified_proof) on success.
    Returns (saturated_subst, None) when SLD succeeds but at least one
    query meta is not grounded — the clause satisfied the query without
    binding the unknown to a concrete term (underdetermined).
    Returns None when no clause matches the current goal, picker returns
    None (user abort), or picker chose a clause whose head does not unify.
    Raises RenderError if the rendered proof is rejected by the kernel
    (indicates a renderer bug, not a user error).

    The returned substitution is fully saturated: all Meta chains are
    resolved to their terminal ground terms.
    """
    state = SLDState(goals=(goal,), subst={}, history=())
    gen = FreshNameGen()
    while state.goals:
        cs = candidates(state, kb)
        if not cs:
            return None
        idx = picker(cs, state)
        if idx is None:
            return None
        result = resolve(state, cs[idx], gen)
        if result is None:
            return None
        state = result

    sat = _saturate(state.subst)

    # Provisional M1 fix: detect underdetermined queries.
    # Universal-fact clauses (e.g. p(X).) satisfy p(?A) without binding ?A
    # to a concrete term.  The renderer cannot emit forallE without a ground
    # instantiation term.  Return (sat, None) so callers can distinguish this
    # from "no clause matched" (None).  The REPL prints a clear message.
    # M2 dispatcher design must decide whether to unify this with the
    # Underdetermined outcome or handle universal-fact proofs differently.
    # See proofs/m1/HARDENING_FINDINGS.md and prd_milestone_2.md §9/§15.
    query_metas = _query_meta_names(goal)
    if any(not _is_ground(apply_to_term(sat, Meta(n))) for n in query_metas):
        return (sat, None)

    proof = render(state, kb, goal)
    if not isinstance(check_proof(proof), Verified):
        raise RenderError("rendered proof rejected by kernel — renderer bug")
    return (sat, proof)
