"""Serialisation round-trip tests for the M1 proof corpus.

For each proof in proofs/m1/: load -> re-serialise -> reload -> compare.
The comparison is structural (IR equality), not byte-level.

Catches: serialiser non-idempotency, dict/list drift, schema-version bugs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hlmr.ir.serialise import from_json, to_json

_PROOFS_DIR = Path(__file__).parent.parent / "proofs" / "m1"


def _proof_files() -> list[Path]:
    return sorted(
        jf for jf in _PROOFS_DIR.glob("*.json") if not jf.name.endswith(".meta.json")
    )


@pytest.mark.parametrize(
    "proof_path",
    _proof_files(),
    ids=[p.stem for p in _proof_files()],
)
def test_round_trip(proof_path: Path) -> None:
    text1 = proof_path.read_text(encoding="utf-8")
    proof1 = from_json(text1)

    text2 = to_json(proof1)
    proof2 = from_json(text2)

    assert proof1 == proof2, (
        f"{proof_path.name}: round-trip produced structurally different proof"
    )
