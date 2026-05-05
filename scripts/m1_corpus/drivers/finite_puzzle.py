"""Finite puzzle corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB_ORIG = _EXAMPLES / "finite_puzzle.pl"
_KB_4VAR = _EXAMPLES / "finite_puzzle_4var.pl"


def generate_finite_puzzle() -> None:
    """finite_puzzle.json — original demo: chain(red, green, blue)."""
    kb = parse_file(_KB_ORIG)
    query_str = "?- chain(red, green, blue)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0, 0, 1]))
    if result is None:
        raise RuntimeError("generate_finite_puzzle: solver returned None")
    subst, proof = result
    save_fixture("finite_puzzle", proof, query_str, subst, kb_path=_KB_ORIG)


def generate_finite_puzzle_4var() -> None:
    """finite_puzzle_4var.json — ring4(a,b,c,d), 4-variable 5-constraint puzzle."""
    kb = parse_file(_KB_4VAR)
    query_str = "?- ring4(a, b, c, d)."
    goal = parse_query(query_str)
    # ring4_1(0), adj(0), left_of_1(0), adj(0), left_of_2(1), adj(0), left_of_3(2), adj(0), left_of_4(3)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0, 0, 1, 0, 2, 0, 3]))
    if result is None:
        raise RuntimeError("generate_finite_puzzle_4var: solver returned None")
    subst, proof = result
    save_fixture("finite_puzzle_4var", proof, query_str, subst, kb_path=_KB_4VAR)


def generate_all() -> None:
    generate_finite_puzzle()
    generate_finite_puzzle_4var()
