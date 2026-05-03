from collections.abc import Callable

from hlmr.ir.formula import Atom, Equals
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.solve.render import RenderError, _saturate, render
from hlmr.solve.sld import (
    FreshNameGen,
    SLDState,
    SLDStep,
    candidates,
    resolve,
)
from hlmr.unify.substitution import Substitution

__all__ = [
    "FreshNameGen",
    "RenderError",
    "SLDState",
    "SLDStep",
    "candidates",
    "manual_solve",
    "render",
    "resolve",
]


def manual_solve(
    kb: KnowledgeBase,
    goal: Atom | Equals,
    picker: Callable[[list[Clause], SLDState], int | None],
) -> tuple[Substitution, Proof] | None:
    """Run manual SLD resolution with a user-supplied clause picker.

    Returns (saturated_subst, kernel_verified_proof) on success.
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
    proof = render(state, kb, goal)
    if not isinstance(check_proof(proof), Verified):
        raise RenderError("rendered proof rejected by kernel — renderer bug")
    return (_saturate(state.subst), proof)
