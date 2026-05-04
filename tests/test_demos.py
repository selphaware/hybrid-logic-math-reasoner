"""Tests for src/hlmr/demos.py and the 'demo' CLI subcommand."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hlmr.ir.formula import Atom, Const, Func
from hlmr.ir.serialise import from_json
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified
from hlmr.demos import (
    DEMOS,
    demo_finite_puzzle,
    demo_kinship,
    demo_peano_even,
    demo_syllogism,
)

_PYTHON = sys.executable
_PROOFS_M1 = Path(__file__).parent.parent / "proofs" / "m1"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_PYTHON, "-m", "hlmr"] + list(args),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Helper: Peano successor term
# ---------------------------------------------------------------------------


def _s(n: int) -> Func | Const:
    t: Func | Const = Const(0)
    for _ in range(n):
        t = Func("s", (t,))
    return t


# ---------------------------------------------------------------------------
# Demo 2: syllogism
# ---------------------------------------------------------------------------


def test_syllogism_proof_verified() -> None:
    _, proof = demo_syllogism()
    assert check_proof(proof) == Verified()


def test_syllogism_final_line() -> None:
    _, proof = demo_syllogism()
    assert proof.lines[-1].formula == Atom("mortal", (Const("socrates"),))


def test_syllogism_json_written() -> None:
    demo_syllogism()
    path = _PROOFS_M1 / "syllogism.json"
    assert path.exists()
    proof = from_json(path.read_text(encoding="utf-8"))
    assert check_proof(proof) == Verified()


# ---------------------------------------------------------------------------
# Demo 1: kinship
# ---------------------------------------------------------------------------


def test_kinship_proof_verified() -> None:
    _, proof = demo_kinship()
    assert check_proof(proof) == Verified()


def test_kinship_final_line() -> None:
    _, proof = demo_kinship()
    assert proof.lines[-1].formula == Atom(
        "ancestor", (Const("alice"), Const("carol"))
    )


def test_kinship_witness() -> None:
    subst, _ = demo_kinship()
    assert subst.get("?A") == Const("alice")


def test_kinship_json_written() -> None:
    demo_kinship()
    path = _PROOFS_M1 / "kinship.json"
    assert path.exists()
    proof = from_json(path.read_text(encoding="utf-8"))
    assert check_proof(proof) == Verified()


# ---------------------------------------------------------------------------
# Demo 3: finite_puzzle
# ---------------------------------------------------------------------------


def test_finite_puzzle_proof_verified() -> None:
    _, proof = demo_finite_puzzle()
    assert check_proof(proof) == Verified()


def test_finite_puzzle_final_line() -> None:
    _, proof = demo_finite_puzzle()
    assert proof.lines[-1].formula == Atom(
        "chain", (Const("red"), Const("green"), Const("blue"))
    )


def test_finite_puzzle_json_written() -> None:
    demo_finite_puzzle()
    path = _PROOFS_M1 / "finite_puzzle.json"
    assert path.exists()
    proof = from_json(path.read_text(encoding="utf-8"))
    assert check_proof(proof) == Verified()


# ---------------------------------------------------------------------------
# Demo 4: peano_even
# ---------------------------------------------------------------------------


def test_peano_even_proof_verified() -> None:
    _, proof = demo_peano_even()
    assert check_proof(proof) == Verified()


def test_peano_even_final_line() -> None:
    _, proof = demo_peano_even()
    assert proof.lines[-1].formula == Atom("even", (_s(4),))


def test_peano_even_json_written() -> None:
    demo_peano_even()
    path = _PROOFS_M1 / "peano_even.json"
    assert path.exists()
    proof = from_json(path.read_text(encoding="utf-8"))
    assert check_proof(proof) == Verified()


# ---------------------------------------------------------------------------
# DEMOS registry
# ---------------------------------------------------------------------------


def test_demos_registry_has_all_four() -> None:
    assert set(DEMOS.keys()) == {"syllogism", "kinship", "finite_puzzle", "peano_even"}


def test_demos_registry_all_callable() -> None:
    for name, fn in DEMOS.items():
        assert callable(fn), f"{name} not callable"


# ---------------------------------------------------------------------------
# CLI: demo subcommand
# ---------------------------------------------------------------------------


def test_demo_cli_syllogism_exit_0() -> None:
    result = _run_cli("demo", "syllogism")
    assert result.returncode == 0
    assert "socrates" in result.stdout.lower()


def test_demo_cli_lists_demos_when_no_name() -> None:
    result = _run_cli("demo")
    assert result.returncode == 0
    assert "syllogism" in result.stdout
    assert "kinship" in result.stdout


def test_demo_cli_unknown_name_exits_1() -> None:
    result = _run_cli("demo", "nonexistent")
    assert result.returncode == 1
    assert "unknown demo" in result.stderr.lower() or "unknown demo" in result.stdout.lower()


def test_demo_cli_all_names_exit_0() -> None:
    for name in DEMOS:
        result = _run_cli("demo", name)
        assert result.returncode == 0, f"demo {name!r} failed: {result.stderr}"
