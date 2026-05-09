"""Runnable demo functions for M1 and M2.

Each demo_<name>() function:
  - issues the canonical query using a deterministic picker,
  - writes the kernel-verified proof JSON to proofs/<milestone>/<name>.json,
  - returns (saturated_subst, proof) or (None, None) for rejection demos.

DEMOS registry maps names to callables; used by the CLI demo subcommand.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
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
_PROOFS_M2 = _REPO_ROOT / "proofs" / "m2"


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


def _save_proof_m2(name: str, proof: Proof) -> None:
    _PROOFS_M2.mkdir(parents=True, exist_ok=True)
    out = _PROOFS_M2 / f"{name}.json"
    out.write_text(to_json(proof) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# M2 demo runners
# ---------------------------------------------------------------------------


def demo_prime_search() -> tuple[Substitution | None, Proof | None]:
    """M2 Demo 1: §2 prime example — mixed KB + Z3 arithmetic.

    KB: prime(2), prime(3), prime(5), prime(7).
    Query: prime(?P), ?P > 2, ?P < 6, ?P != 4.
    Answer: ?P = 5 with kernel-verified proof.
    """
    from hlmr.dispatch.route import Dispatcher
    from hlmr.kernel.check import check_proof
    from hlmr.kernel.errors import Verified

    try:
        from hlmr.solvers.z3_bridge import Z3Bridge
        from hlmr.solvers.sympy_bridge import SymPyBridge
    except ImportError as e:
        raise RuntimeError(f"demo_prime_search requires z3-solver and sympy: {e}") from e

    primes = [2, 3, 5, 7]
    kb = KnowledgeBase(
        clauses=tuple(
            Clause(f"prime_{p}", Atom("prime", (Const(p),)), ()) for p in primes
        )
    )
    d = Dispatcher(z3_bridge=Z3Bridge(), sympy_bridge=SymPyBridge(), kb=kb)
    goals = (
        Atom("prime", (Meta("?P"),)),
        Atom(">", (Meta("?P"), Const(2))),
        Atom("<", (Meta("?P"), Const(6))),
        Atom("!=", (Meta("?P"), Const(4))),
    )

    def _pick_prime_5(cs: list, state: SLDState) -> int | None:
        for i, c in enumerate(cs):
            match c.head:
                case Atom(pred="prime", args=(Const(value=5),)):
                    return i
        return None

    result = manual_solve(kb, goals, _pick_prime_5, dispatcher=d)
    if result is None:
        raise RuntimeError("demo_prime_search: solver returned None — unexpected")
    subst, proof = result
    if proof is None:
        raise RuntimeError("demo_prime_search: no proof rendered — unexpected")
    if not isinstance(check_proof(proof), Verified):
        raise RuntimeError("demo_prime_search: proof rejected by kernel")
    _save_proof_m2("prime_search", proof)
    return subst, proof


def demo_quadratic() -> tuple[Substitution | None, Proof | None]:
    """M2 Demo 2: quadratic — SymPy symbolic algebra.

    Query: root_of(?X, x^2 - 5x + 6).
    Answer: ?X = 2 (deterministic; index 0 of {2, 3} from SymPy).
    """
    from hlmr.dispatch.route import Dispatcher
    from hlmr.ir.kb import KnowledgeBase
    from hlmr.kernel.check import check_proof
    from hlmr.kernel.errors import Verified

    try:
        from hlmr.solvers.z3_bridge import Z3Bridge
        from hlmr.solvers.sympy_bridge import SymPyBridge
    except ImportError as e:
        raise RuntimeError(f"demo_quadratic requires z3-solver and sympy: {e}") from e

    empty_kb = KnowledgeBase(clauses=())
    d = Dispatcher(z3_bridge=Z3Bridge(), sympy_bridge=SymPyBridge(), kb=empty_kb)

    poly = Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )
    goal = Atom("root_of", (Meta("?X"), poly))

    def _first_picker(cs: list, state: SLDState) -> int | None:
        return 0 if cs else None

    result = manual_solve(
        empty_kb,
        goal,
        _first_picker,
        dispatcher=d,
        solver_picker=lambda sols: 0,  # deterministic: always pick first root
    )
    if result is None:
        raise RuntimeError("demo_quadratic: solver returned None — unexpected")
    subst, proof = result
    if proof is None:
        raise RuntimeError("demo_quadratic: no proof rendered — unexpected")
    if not isinstance(check_proof(proof), Verified):
        raise RuntimeError("demo_quadratic: proof rejected by kernel")
    _save_proof_m2("quadratic", proof)
    return subst, proof


def demo_linear_system() -> tuple[Substitution | None, Proof | None]:
    """M2 Demo 3: linear system — Z3 constraint solving.

    Query: ?X = 2, ?X + ?Y = 10.  (goal-by-goal-determinate form)
    Answer: ?X = 2, ?Y = 8 with kernel-verified proof.
    """
    from hlmr.dispatch.route import Dispatcher
    from hlmr.ir.kb import KnowledgeBase
    from hlmr.kernel.check import check_proof
    from hlmr.kernel.errors import Verified

    try:
        from hlmr.solvers.z3_bridge import Z3Bridge
        from hlmr.solvers.sympy_bridge import SymPyBridge
    except ImportError as e:
        raise RuntimeError(f"demo_linear_system requires z3-solver and sympy: {e}") from e

    empty_kb = KnowledgeBase(clauses=())
    d = Dispatcher(z3_bridge=Z3Bridge(), sympy_bridge=SymPyBridge(), kb=empty_kb)

    goals = (
        Equals(Meta("?X"), Const(2)),
        Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
    )

    def _first_picker(cs: list, state: SLDState) -> int | None:
        return 0 if cs else None

    result = manual_solve(empty_kb, goals, _first_picker, dispatcher=d)
    if result is None:
        raise RuntimeError("demo_linear_system: solver returned None — unexpected")
    subst, proof = result
    if proof is None:
        raise RuntimeError("demo_linear_system: no proof rendered — unexpected")
    if not isinstance(check_proof(proof), Verified):
        raise RuntimeError("demo_linear_system: proof rejected by kernel")
    _save_proof_m2("linear_system", proof)
    return subst, proof


def demo_outside_fragment() -> tuple[None, None]:
    """M2 Demo 4: OutsideFragment — honest transcendental rejection.

    Query: root_of(?X, 2^x).
    Answer: OutsideFragment(TRANSCENDENTAL) — no proof produced.
    """
    from hlmr.dispatch import OutsideFragmentReason
    from hlmr.dispatch.route import Dispatcher
    from hlmr.ir.kb import KnowledgeBase

    try:
        from hlmr.solvers.z3_bridge import Z3Bridge
        from hlmr.solvers.sympy_bridge import SymPyBridge
    except ImportError as e:
        raise RuntimeError(f"demo_outside_fragment requires z3-solver and sympy: {e}") from e

    empty_kb = KnowledgeBase(clauses=())
    d = Dispatcher(z3_bridge=Z3Bridge(), sympy_bridge=SymPyBridge(), kb=empty_kb)

    goal = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))

    def _first_picker(cs: list, state: SLDState) -> int | None:
        return 0 if cs else None

    result = manual_solve(empty_kb, goal, _first_picker, dispatcher=d)
    if result is not None:
        raise RuntimeError("demo_outside_fragment: expected None (OutsideFragment), got result")
    assert d.last_outside_fragment is not None
    assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL
    return None, None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEMOS: dict[str, Callable[[], tuple[Substitution | None, Proof | None]]] = {
    "syllogism": demo_syllogism,
    "kinship": demo_kinship,
    "finite_puzzle": demo_finite_puzzle,
    "peano_even": demo_peano_even,
    "prime_search": demo_prime_search,
    "quadratic": demo_quadratic,
    "linear_system": demo_linear_system,
    "outside_fragment": demo_outside_fragment,
}
