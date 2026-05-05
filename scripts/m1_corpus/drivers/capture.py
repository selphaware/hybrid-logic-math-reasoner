"""Capture-avoidance stress corpus drivers."""
from __future__ import annotations

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB = _EXAMPLES / "capture_stress.pl"


def generate_capture_shared_xy() -> None:
    """capture_shared_xy.json — two clauses share X,Y; query chains through both."""
    kb = parse_file(_KB)
    query_str = "?- foo(?A, ?B)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0]))
    if result is None:
        raise RuntimeError("generate_capture_shared_xy: solver returned None")
    subst, proof = result
    save_fixture("capture_shared_xy", proof, query_str, subst, kb_path=_KB)


def generate_capture_meta_clash() -> None:
    """capture_meta_clash.json — clause var X vs query meta ?X; must stay distinct."""
    kb = parse_file(_KB)
    query_str = "?- knows(?X)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0]))
    if result is None:
        raise RuntimeError("generate_capture_meta_clash: solver returned None")
    subst, proof = result
    save_fixture("capture_meta_clash", proof, query_str, subst, kb_path=_KB)


def generate_capture_mutual_recursion() -> None:
    """capture_mutual_recursion.json — two predicates both using X,Y,Z; rename apart."""
    kb = parse_file(_KB)
    query_str = "?- even3(?X, ?Y, ?Z)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0, 0, 0]))
    if result is None:
        raise RuntimeError("generate_capture_mutual_recursion: solver returned None")
    subst, proof = result
    save_fixture("capture_mutual_recursion", proof, query_str, subst, kb_path=_KB)


def generate_all() -> None:
    generate_capture_shared_xy()
    generate_capture_meta_clash()
    generate_capture_mutual_recursion()
