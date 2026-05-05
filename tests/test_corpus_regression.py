"""Regression tests for the M1 proof corpus.

Each fixture in proofs/m1/*.json is:
  1. kernel-verified (check_proof returns Verified), and
  2. its final line matches the instantiated query recorded in the sidecar.

This is the primary regression target for M2's v1->v2 schema migration.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hlmr.ir.serialise import _formula_from_dict, from_json
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified

_PROOFS_DIR = Path(__file__).parent.parent / "proofs" / "m1"


def _fixture_pairs() -> list[tuple[Path, Path]]:
    pairs = []
    for jf in sorted(_PROOFS_DIR.glob("*.json")):
        if jf.name.endswith(".meta.json"):
            continue
        meta = jf.with_suffix("").with_suffix(".meta.json")
        if meta.exists():
            pairs.append((jf, meta))
    return pairs


@pytest.mark.parametrize(
    "proof_path,meta_path",
    _fixture_pairs(),
    ids=[p.stem for p, _ in _fixture_pairs()],
)
def test_corpus_fixture(proof_path: Path, meta_path: Path) -> None:
    proof_text = proof_path.read_text(encoding="utf-8")
    proof = from_json(proof_text)

    result = check_proof(proof)
    assert isinstance(result, Verified), (
        f"{proof_path.name}: kernel rejected proof at line {getattr(result, 'line', '?')}: "
        f"{getattr(result, 'reason', result)}"
    )

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    expected_final = _formula_from_dict(meta["final_formula"])
    actual_final = proof.lines[-1].formula
    assert actual_final == expected_final, (
        f"{proof_path.name}: final line mismatch\n"
        f"  expected: {expected_final!r}\n"
        f"  got:      {actual_final!r}"
    )
