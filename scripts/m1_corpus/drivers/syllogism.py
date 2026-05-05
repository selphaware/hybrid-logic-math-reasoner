"""Syllogism corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB_ORIG = _EXAMPLES / "syllogism.pl"
_KB_CHAINED = _EXAMPLES / "syllogism_chained.pl"
_KB_ANDE = _EXAMPLES / "syllogism_andE.pl"


def generate_syllogism() -> None:
    """syllogism.json — original demo: mortal(socrates)."""
    kb = parse_file(_KB_ORIG)
    query_str = "?- mortal(socrates)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0]))
    if result is None:
        raise RuntimeError("generate_syllogism: solver returned None")
    subst, proof = result
    save_fixture("syllogism", proof, query_str, subst, kb_path=_KB_ORIG)


def generate_syllogism_chained() -> None:
    """syllogism_chained.json — temporal(socrates) via 3-step chain."""
    kb = parse_file(_KB_CHAINED)
    query_str = "?- temporal(socrates)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0]))
    if result is None:
        raise RuntimeError("generate_syllogism_chained: solver returned None")
    subst, proof = result
    save_fixture("syllogism_chained", proof, query_str, subst, kb_path=_KB_CHAINED)


def generate_syllogism_andE() -> None:
    """syllogism_andE.json — athlete(socrates) via 2-body rule (andI path)."""
    kb = parse_file(_KB_ANDE)
    query_str = "?- athlete(socrates)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0]))
    if result is None:
        raise RuntimeError("generate_syllogism_andE: solver returned None")
    subst, proof = result
    save_fixture("syllogism_andE", proof, query_str, subst, kb_path=_KB_ANDE)


def generate_all() -> None:
    generate_syllogism()
    generate_syllogism_chained()
    generate_syllogism_andE()
