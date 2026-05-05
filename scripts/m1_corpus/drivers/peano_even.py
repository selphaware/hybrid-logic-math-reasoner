"""Peano even corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB = _EXAMPLES / "peano_even.pl"


def generate_peano_even() -> None:
    """peano_even.json — original demo: even(s(s(s(s(0)))))."""
    kb = parse_file(_KB)
    query_str = "?- even(s(s(s(s(0)))))."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_even: solver returned None")
    subst, proof = result
    save_fixture("peano_even", proof, query_str, subst, kb_path=_KB)


def generate_peano_even_6() -> None:
    """peano_even_6.json — even(s^6(0)), SLD depth 3."""
    kb = parse_file(_KB)
    query_str = "?- even(s(s(s(s(s(s(0)))))))."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_even_6: solver returned None")
    subst, proof = result
    save_fixture("peano_even_6", proof, query_str, subst, kb_path=_KB)


def generate_peano_even_8() -> None:
    """peano_even_8.json — even(s^8(0)), SLD depth 4."""
    kb = parse_file(_KB)
    query_str = "?- even(s(s(s(s(s(s(s(s(0)))))))))."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_even_8: solver returned None")
    subst, proof = result
    save_fixture("peano_even_8", proof, query_str, subst, kb_path=_KB)


def generate_peano_even_find_first() -> None:
    """peano_even_find_first.json — even(?N), first witness ?N=0."""
    kb = parse_file(_KB)
    query_str = "?- even(?N)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_peano_even_find_first: solver returned None")
    subst, proof = result
    save_fixture("peano_even_find_first", proof, query_str, subst, kb_path=_KB)


def generate_all() -> None:
    generate_peano_even()
    generate_peano_even_6()
    generate_peano_even_8()
    generate_peano_even_find_first()
