"""Kinship corpus drivers — generates kinship.json and kinship_*. json fixtures."""
from __future__ import annotations

from pathlib import Path

from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import manual_solve

from m1_corpus.common import _EXAMPLES, save_fixture, seq_picker

_KB_ORIG = _EXAMPLES / "kinship.pl"
_KB_EXT = _EXAMPLES / "kinship_extended.pl"


def generate_kinship() -> None:
    """kinship.json — original demo: ancestor(?A, carol) -> ?A=alice."""
    kb = parse_file(_KB_ORIG)
    query_str = "?- ancestor(?A, carol)."
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, seq_picker([1, 0, 0, 1]))
    if result is None:
        raise RuntimeError("generate_kinship: solver returned None")
    subst, proof = result
    save_fixture("kinship", proof, query_str, subst, kb_path=_KB_ORIG)


def generate_kinship_deep() -> None:
    """kinship_deep.json — ancestor(?X, alice) -> ?X=carol, SLD depth 4."""
    kb = parse_file(_KB_EXT)
    query_str = "?- ancestor(?X, alice)."
    goal = parse_query(query_str)
    # Picker: ancestor_2(1), parent(carol,mid1)(0), ancestor_1(0), parent(mid1,alice)(1)
    result = manual_solve(kb, goal, seq_picker([1, 0, 0, 1]))
    if result is None:
        raise RuntimeError("generate_kinship_deep: solver returned None")
    subst, proof = result
    save_fixture("kinship_deep", proof, query_str, subst, kb_path=_KB_EXT)


def generate_kinship_first_child() -> None:
    """kinship_first_child.json — parent(alice, ?Y) -> ?Y=bob."""
    kb = parse_file(_KB_EXT)
    query_str = "?- parent(alice, ?Y)."
    goal = parse_query(query_str)
    # Candidates=[parent_1..8]; parent_3=parent(alice,bob) is at index 2
    result = manual_solve(kb, goal, seq_picker([2]))
    if result is None:
        raise RuntimeError("generate_kinship_first_child: solver returned None")
    subst, proof = result
    save_fixture("kinship_first_child", proof, query_str, subst, kb_path=_KB_EXT)


def generate_kinship_two_metas() -> None:
    """kinship_two_metas.json — ancestor(?X, ?Y) -> first pair ?X=carol, ?Y=mid1."""
    kb = parse_file(_KB_EXT)
    query_str = "?- ancestor(?X, ?Y)."
    goal = parse_query(query_str)
    # ancestor_1(0), parent_1=parent(carol,mid1)(0)
    result = manual_solve(kb, goal, seq_picker([0, 0]))
    if result is None:
        raise RuntimeError("generate_kinship_two_metas: solver returned None")
    subst, proof = result
    save_fixture("kinship_two_metas", proof, query_str, subst, kb_path=_KB_EXT)


def generate_kinship_chain6() -> None:
    """kinship_chain6.json — ancestor(?Top, leaf6) -> ?Top=alice, SLD depth 12."""
    kb = parse_file(_KB_EXT)
    query_str = "?- ancestor(?Top, leaf6)."
    goal = parse_query(query_str)
    # Pattern: [anc2, parent_i, anc2, parent_{i+1}, ..., anc1, parent_8]
    # alice(idx2)->bob(3)->carol2(4)->dave(5)->eve(6)->fred(7)->leaf6 via anc1+parent8
    result = manual_solve(
        kb, goal, seq_picker([1, 2, 1, 3, 1, 4, 1, 5, 1, 6, 0, 7])
    )
    if result is None:
        raise RuntimeError("generate_kinship_chain6: solver returned None")
    subst, proof = result
    save_fixture("kinship_chain6", proof, query_str, subst, kb_path=_KB_EXT)


def generate_all() -> None:
    generate_kinship()
    generate_kinship_deep()
    generate_kinship_first_child()
    generate_kinship_two_metas()
    generate_kinship_chain6()
