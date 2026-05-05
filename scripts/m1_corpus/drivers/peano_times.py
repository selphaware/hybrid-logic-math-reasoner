"""Peano times corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB = _EXAMPLES / "peano_times.pl"


def generate_peano_times_2_2() -> None:
    """peano_times_2_2.json — times(2,2,?R), ?R=4."""
    kb = parse_file(_KB)
    query_str = "?- times(s(s(0)), s(s(0)), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0, 0, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_times_2_2: solver returned None")
    subst, proof = result
    save_fixture("peano_times_2_2", proof, query_str, subst, kb_path=_KB)


def generate_peano_times_2_3() -> None:
    """peano_times_2_3.json — times(2,3,?R), ?R=6."""
    kb = parse_file(_KB)
    query_str = "?- times(s(s(0)), s(s(s(0))), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0, 0, 1, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_times_2_3: solver returned None")
    subst, proof = result
    save_fixture("peano_times_2_3", proof, query_str, subst, kb_path=_KB)


def generate_peano_times_3_2() -> None:
    """peano_times_3_2.json — times(3,2,?R), ?R=6."""
    kb = parse_file(_KB)
    query_str = "?- times(s(s(s(0))), s(s(0)), ?R)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_times_3_2: solver returned None")
    subst, proof = result
    save_fixture("peano_times_3_2", proof, query_str, subst, kb_path=_KB)


def generate_all() -> None:
    generate_peano_times_2_2()
    generate_peano_times_2_3()
    generate_peano_times_3_2()
