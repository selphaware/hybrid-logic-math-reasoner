"""Edge-case corpus drivers (inline KBs, no .pl file)."""
from __future__ import annotations

from hlmr.parse.parser import parse_kb, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import save_fixture, seq_picker

_SINGLE_FACT_SRC = "truth(a)."
_QUERY_IS_FACT_SRC = "fact_pred(a).\nrule_pred(X) :- fact_pred(X)."
_ALL_META_SRC = "triple(a, b, c)."


def generate_edge_single_fact() -> None:
    """edge_single_fact.json — KB=one fact, query=that fact; minimal valid proof."""
    kb = parse_kb(_SINGLE_FACT_SRC)
    query_str = "?- truth(a)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_edge_single_fact: solver returned None")
    subst, proof = result
    save_fixture("edge_single_fact", proof, query_str, subst, kb_source=_SINGLE_FACT_SRC)


def generate_edge_query_is_fact() -> None:
    """edge_query_is_fact.json — KB has facts+rules; query matches fact; rules unused."""
    kb = parse_kb(_QUERY_IS_FACT_SRC)
    query_str = "?- fact_pred(a)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_edge_query_is_fact: solver returned None")
    subst, proof = result
    save_fixture("edge_query_is_fact", proof, query_str, subst, kb_source=_QUERY_IS_FACT_SRC)


def generate_edge_all_meta() -> None:
    """edge_all_meta.json — all query args are metas; all bind from one fact."""
    kb = parse_kb(_ALL_META_SRC)
    query_str = "?- triple(?A, ?B, ?C)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([0]))
    if result is None:
        raise RuntimeError("generate_edge_all_meta: solver returned None")
    subst, proof = result
    save_fixture("edge_all_meta", proof, query_str, subst, kb_source=_ALL_META_SRC)


def generate_all() -> None:
    generate_edge_single_fact()
    generate_edge_query_is_fact()
    generate_edge_all_meta()
