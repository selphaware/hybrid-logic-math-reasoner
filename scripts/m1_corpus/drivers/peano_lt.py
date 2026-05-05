"""Peano lt corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB = _EXAMPLES / "peano_lt.pl"


def generate_peano_lt_2_4() -> None:
    """peano_lt_2_4.json — lt(2,4), proven via two recursive steps."""
    kb = parse_file(_KB)
    query_str = "?- lt(s(s(0)), s(s(s(s(0)))))."
    goal = parse_query(query_str)
    # lt_2(1), lt_2(1), lt_1(0)
    result = manual_solve(kb, goal, seq_picker([1, 1, 0]))
    if result is None:
        raise RuntimeError("generate_peano_lt_2_4: solver returned None")
    subst, proof = result
    save_fixture("peano_lt_2_4", proof, query_str, subst, kb_path=_KB)


def generate_peano_lt_find() -> None:
    """peano_lt_find.json — lt(?X, s(s(s(0)))), first witness ?X=0."""
    kb = parse_file(_KB)
    query_str = "?- lt(?X, s(s(s(0))))."
    goal = parse_query(query_str)
    # lt_1 matches immediately: lt(0, s(Y)) with Y=s(s(0))
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_peano_lt_find: solver returned None")
    subst, proof = result
    save_fixture("peano_lt_find", proof, query_str, subst, kb_path=_KB)


def generate_all() -> None:
    generate_peano_lt_2_4()
    generate_peano_lt_find()
