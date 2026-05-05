"""Peano plus corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB = _EXAMPLES / "peano_plus.pl"


def generate_peano_plus_2_2() -> None:
    """peano_plus_2_2.json — plus(2,2,?R), ?R=4."""
    kb = parse_file(_KB)
    query_str = "?- plus(s(s(0)), s(s(0)), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_plus_2_2: solver returned None")
    subst, proof = result
    save_fixture("peano_plus_2_2", proof, query_str, subst, kb_path=_KB)


def generate_peano_plus_3_2() -> None:
    """peano_plus_3_2.json — plus(3,2,?R), ?R=5."""
    kb = parse_file(_KB)
    query_str = "?- plus(s(s(s(0))), s(s(0)), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_plus_3_2: solver returned None")
    subst, proof = result
    save_fixture("peano_plus_3_2", proof, query_str, subst, kb_path=_KB)


def generate_peano_plus_find_b() -> None:
    """peano_plus_find_b.json — plus(0,?B,3), ?B=3 (immediate via plus_1)."""
    kb = parse_file(_KB)
    query_str = "?- plus(0, ?B, s(s(s(0))))."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_peano_plus_find_b: solver returned None")
    subst, proof = result
    save_fixture("peano_plus_find_b", proof, query_str, subst, kb_path=_KB)


def generate_peano_plus_find_a() -> None:
    """peano_plus_find_a.json — plus(?A,2,4), ?A=2 (recursive descent)."""
    kb = parse_file(_KB)
    query_str = "?- plus(?A, s(s(0)), s(s(s(s(0)))))."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_plus_find_a: solver returned None")
    subst, proof = result
    save_fixture("peano_plus_find_a", proof, query_str, subst, kb_path=_KB)


def generate_peano_plus_5() -> None:
    """peano_plus_5.json — plus(1,4,?R), ?R=5."""
    kb = parse_file(_KB)
    query_str = "?- plus(s(0), s(s(s(s(0)))), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_plus_5: solver returned None")
    subst, proof = result
    save_fixture("peano_plus_5", proof, query_str, subst, kb_path=_KB)


def generate_all() -> None:
    generate_peano_plus_2_2()
    generate_peano_plus_3_2()
    generate_peano_plus_find_b()
    generate_peano_plus_find_a()
    generate_peano_plus_5()
