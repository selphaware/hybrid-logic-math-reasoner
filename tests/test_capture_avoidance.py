"""Integration tests for capture-avoidance using the corpus fixtures.

For each capture_* fixture, re-run manual_solve with the same picker and
assert the returned substitution matches what the sidecar recorded.

If the renamer is broken, the substitution will be subtly wrong (e.g.
two metas bind to the same constant when they shouldn't), causing a
mismatch against the sidecar witness even if the proof still kernel-verifies.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from hlmr.ir.kb import Clause
from hlmr.ir.serialise import _term_from_dict
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified
from hlmr.parse.parser import parse_file, parse_query
from hlmr.solve import SLDState, manual_solve

_EXAMPLES = Path(__file__).parent.parent / "examples" / "m1"
_PROOFS = Path(__file__).parent.parent / "proofs" / "m1"


def _seq_picker(indices: list[int]) -> Callable[[list[Clause], SLDState], int | None]:
    it = iter(indices)
    return lambda cs, state: next(it, None)


_FIXTURES = [
    ("capture_shared_xy", "?- foo(?A, ?B).", "capture_stress.pl", [0, 0, 0]),
    ("capture_meta_clash", "?- knows(?X).", "capture_stress.pl", [0, 0]),
    ("capture_mutual_recursion", "?- even3(?X, ?Y, ?Z).", "capture_stress.pl", [0, 0, 0]),
]


@pytest.mark.parametrize(
    "fixture_name,query_str,kb_file,picker",
    _FIXTURES,
    ids=[f[0] for f in _FIXTURES],
)
def test_capture_avoidance(
    fixture_name: str,
    query_str: str,
    kb_file: str,
    picker: list[int],
) -> None:
    kb = parse_file(_EXAMPLES / kb_file)
    goal = parse_query(query_str)
    result = manual_solve(kb, goal, _seq_picker(picker))
    assert result is not None, f"{fixture_name}: manual_solve returned None"
    sat_subst, proof = result

    meta = json.loads((_PROOFS / f"{fixture_name}.meta.json").read_text(encoding="utf-8"))
    expected_witness: dict = meta["expected_witness"]

    for meta_name, expected_dict in expected_witness.items():
        assert meta_name in sat_subst, (
            f"{fixture_name}: {meta_name!r} missing from returned substitution"
        )
        expected_term = _term_from_dict(expected_dict)
        actual_term = sat_subst[meta_name]
        assert actual_term == expected_term, (
            f"{fixture_name}: {meta_name}={actual_term!r} != expected {expected_term!r}\n"
            f"Full subst keys: {list(sat_subst)}"
        )

    result2 = check_proof(proof)
    assert isinstance(result2, Verified), (
        f"{fixture_name}: proof failed kernel check: {result2}"
    )
    assert proof.lines[-1].formula == proof.goal, (
        f"{fixture_name}: final line != proof goal"
    )
