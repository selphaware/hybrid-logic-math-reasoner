"""Runnable M1 demo functions.

Each demo_<name>() function:
  - loads the corresponding examples/m1/<name>.pl knowledge base,
  - issues the canonical query using a deterministic picker,
  - writes the kernel-verified proof JSON to proofs/m1/<name>.json,
  - returns (saturated_subst, proof).

DEMOS registry maps names to callables; used by the CLI demo subcommand.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from hlmr.ir.kb import Clause
from hlmr.ir.proof import Proof
from hlmr.ir.serialise import to_json
from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import SLDState, manual_solve
from hlmr.unify.substitution import Substitution

# ---------------------------------------------------------------------------
# Paths (relative to the repo root, which is two levels up from this file)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples" / "m1"
_PROOFS = _REPO_ROOT / "proofs" / "m1"


# ---------------------------------------------------------------------------
# Deterministic picker factory
# ---------------------------------------------------------------------------


def _seq_picker(indices: list[int]) -> Callable[[list[Clause], SLDState], int | None]:
    """Return a picker that steps through a fixed sequence of 0-based indices."""
    it = iter(indices)
    return lambda cs, state: next(it, None)


# ---------------------------------------------------------------------------
# Demo runners
# ---------------------------------------------------------------------------


def demo_syllogism() -> tuple[Substitution, Proof]:
    """Demo 2: 'all humans are mortal; Socrates is human; therefore mortal.'

    Query: mortal(socrates).  No unknowns — direct ground proof.
    """
    kb = parse_file(_EXAMPLES / "syllogism.pl")
    goal = parse_query("?- mortal(socrates).")
    result = manual_solve(kb, goal, _seq_picker([0, 0]))
    if result is None:
        raise RuntimeError("demo_syllogism: solver returned None — unexpected")
    subst, proof = result
    _save_proof("syllogism", proof)
    return subst, proof


def demo_kinship() -> tuple[Substitution, Proof]:
    """Demo 1: recursive kinship KB; finds ancestor(?A, carol) = alice.

    Query: ancestor(?A, carol).  Witness: ?A = alice.
    """
    kb = parse_file(_EXAMPLES / "kinship.pl")
    goal = parse_query("?- ancestor(?A, carol).")
    result = manual_solve(kb, goal, _seq_picker([1, 0, 0, 1]))
    if result is None:
        raise RuntimeError("demo_kinship: solver returned None — unexpected")
    subst, proof = result
    _save_proof("kinship", proof)
    return subst, proof


def demo_finite_puzzle() -> tuple[Substitution, Proof]:
    """Demo 3: colour-chain finite puzzle; proves chain(red, green, blue).

    Query: chain(red, green, blue).  No unknowns — direct ground proof.
    """
    kb = parse_file(_EXAMPLES / "finite_puzzle.pl")
    goal = parse_query("?- chain(red, green, blue).")
    result = manual_solve(kb, goal, _seq_picker([0, 0, 0, 0, 1]))
    if result is None:
        raise RuntimeError("demo_finite_puzzle: solver returned None — unexpected")
    subst, proof = result
    _save_proof("finite_puzzle", proof)
    return subst, proof


def demo_peano_even() -> tuple[Substitution, Proof]:
    """Demo 4: Peano even predicate; proves even(s(s(s(s(0))))).

    Query: even(s(s(s(s(0))))).  No unknowns — structural induction proof.
    """
    kb = parse_file(_EXAMPLES / "peano_even.pl")
    goal = parse_query("?- even(s(s(s(s(0))))).")
    result = manual_solve(kb, goal, _seq_picker([1, 1, 0]))
    if result is None:
        raise RuntimeError("demo_peano_even: solver returned None — unexpected")
    subst, proof = result
    _save_proof("peano_even", proof)
    return subst, proof


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _save_proof(name: str, proof: Proof) -> None:
    _PROOFS.mkdir(parents=True, exist_ok=True)
    out = _PROOFS / f"{name}.json"
    out.write_text(to_json(proof) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEMOS: dict[str, Callable[[], tuple[Substitution, Proof]]] = {
    "syllogism": demo_syllogism,
    "kinship": demo_kinship,
    "finite_puzzle": demo_finite_puzzle,
    "peano_even": demo_peano_even,
}
