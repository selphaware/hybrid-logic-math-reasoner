"""Tests for src/hlmr/log/recorder.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from hlmr.ir.formula import Atom, Const, Meta, Var
from hlmr.ir.justification import Premise
from hlmr.ir.kb import Clause
from hlmr.ir.proof import Proof, ProofLine
from hlmr.ir.serialise import _formula_from_dict, _term_from_dict
from hlmr.log import SessionRecorder
from hlmr.solve.sld import SLDState, SLDStep

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SOCRATES = Const("socrates")
ALICE = Const("alice")

# human(socrates).
_HUMAN_SOCRATES = Clause("human_1", Atom("human", (SOCRATES,)), ())

# mortal(X) :- human(X).
_MORTAL_X = Clause(
    "mortal_1",
    Atom("mortal", (Var("X"),)),
    (Atom("human", (Var("X"),)),),
)

# Query: mortal(socrates)
_QUERY = Atom("mortal", (SOCRATES,))

# SLD state before any step: one goal, empty subst, no history
_STATE_0 = SLDState(goals=(_QUERY,), subst={}, history=())

# After renaming mortal_1: mortal(?X_1) :- human(?X_1).
_META_X1 = Meta("?X_1")
_MORTAL_RENAMED = Clause(
    "mortal_1",
    Atom("mortal", (_META_X1,)),
    (Atom("human", (_META_X1,)),),
)

# After one resolution step: {?X_1: socrates}, goal = human(socrates)
_SUBST_1: dict[str, Const] = {"?X_1": SOCRATES}
_STEP_1 = SLDStep(
    goal_resolved=_QUERY,
    clause_used=_MORTAL_X,
    clause_renamed=_MORTAL_RENAMED,
    unifier=_SUBST_1,
)
_STATE_1 = SLDState(
    goals=(Atom("human", (_META_X1,)),),
    subst=_SUBST_1,
    history=(_STEP_1,),
)


def _simple_proof(goal: Atom) -> Proof:
    """Minimal valid-looking Proof (one Premise line) for testing."""
    return Proof(
        lines=(ProofLine(number=1, formula=goal, justification=Premise(), box_depth=0),),
        goal=goal,
    )


def _read_lines(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _clause_from_event_dict(d: dict) -> Clause:
    """Test-only round-trip helper: reconstruct a Clause from a kb_add event's 'clause' field."""
    return Clause(
        name=d["name"],
        head=_formula_from_dict(d["head"]),
        body=tuple(_formula_from_dict(b) for b in d["body"]),
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


def test_enabled_creates_file(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    assert rec.log_path is not None
    assert rec.log_path.exists()
    assert rec.log_path.parent == tmp_path
    assert rec.session_id in rec.log_path.name
    rec.close()


def test_disabled_no_file(tmp_path) -> None:
    rec = SessionRecorder(enabled=False, corpus_dir=tmp_path)
    assert rec.log_path is None
    # No .jsonl files should be created
    assert list(tmp_path.glob("*.jsonl")) == []


def test_corpus_dir_override(tmp_path) -> None:
    sub = tmp_path / "custom_corpus"
    rec = SessionRecorder(corpus_dir=sub)
    assert rec.log_path is not None
    assert rec.log_path.parent == sub
    assert sub.exists()
    rec.close()


# ---------------------------------------------------------------------------
# Event recording tests
# ---------------------------------------------------------------------------


def test_kb_add_shape(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.kb_add(_HUMAN_SOCRATES)
    rec.close()

    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    ev = lines[0]
    assert ev["event_type"] == "kb_add"
    assert "clause" in ev

    # Round-trip: clause deserializes back to the original
    recovered = _clause_from_event_dict(ev["clause"])
    assert recovered == _HUMAN_SOCRATES


def test_query_start_shape(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.query_start(_QUERY)
    rec.close()

    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    ev = lines[0]
    assert ev["event_type"] == "query_start"
    assert "query" in ev

    recovered = _formula_from_dict(ev["query"])
    assert recovered == _QUERY


def test_pick_shape(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.pick(_STATE_0, _STATE_1, 0, "mortal_1")
    rec.close()

    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    ev = lines[0]
    assert ev["event_type"] == "pick"
    assert ev["candidate_index"] == 0
    assert ev["clause_name"] == "mortal_1"

    # state_before: one goal (mortal(socrates)), empty subst, no history
    sb = ev["state_before"]
    assert len(sb["goals"]) == 1
    assert sb["goals"][0]["_type"] == "Atom"
    assert sb["goals"][0]["pred"] == "mortal"
    assert sb["subst"] == {}
    assert sb["history"] == []

    # state_after: one goal (human(?X_1)), subst has ?X_1, one history step
    sa = ev["state_after"]
    assert len(sa["goals"]) == 1
    assert sa["goals"][0]["pred"] == "human"
    assert "?X_1" in sa["subst"]
    recovered_term = _term_from_dict(sa["subst"]["?X_1"])
    assert recovered_term == SOCRATES
    assert len(sa["history"]) == 1
    assert sa["history"][0]["clause_name"] == "mortal_1"
    assert "goal_resolved" in sa["history"][0]
    assert "unifier" in sa["history"][0]


def test_query_end_success_includes_subst_and_hash(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    proof = _simple_proof(_QUERY)
    subst = {"?X": ALICE}
    rec.query_end("success", final_subst=subst, proof=proof)
    rec.close()

    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    ev = lines[0]
    assert ev["event_type"] == "query_end"
    assert ev["outcome"] == "success"
    assert "final_subst" in ev
    assert "proof_hash" in ev
    assert "?X" in ev["final_subst"]
    recovered_term = _term_from_dict(ev["final_subst"]["?X"])
    assert recovered_term == ALICE
    # proof_hash is a 64-char hex SHA-256
    assert len(ev["proof_hash"]) == 64


def test_query_end_abort_omits_optional_fields(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.query_end("abort")
    rec.close()

    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    ev = lines[0]
    assert ev["event_type"] == "query_end"
    assert ev["outcome"] == "abort"
    assert "final_subst" not in ev
    assert "proof_hash" not in ev


# ---------------------------------------------------------------------------
# Schema correctness tests
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {"hlmr_log_version", "timestamp", "event_type", "session_id"}


def test_required_top_level_keys(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.kb_add(_HUMAN_SOCRATES)
    rec.query_start(_QUERY)
    rec.pick(_STATE_0, _STATE_1, 0, "mortal_1")
    rec.query_end("success", final_subst={}, proof=_simple_proof(_QUERY))
    rec.query_end("abort")
    rec.close()

    for ev in _read_lines(rec.log_path):
        missing = REQUIRED_KEYS - ev.keys()
        assert not missing, f"Event missing keys {missing}: {ev['event_type']}"
        assert ev["hlmr_log_version"] == 1


def test_session_id_consistent(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.kb_add(_HUMAN_SOCRATES)
    rec.query_start(_QUERY)
    rec.query_end("abort")
    rec.close()

    lines = _read_lines(rec.log_path)
    ids = {ev["session_id"] for ev in lines}
    assert len(ids) == 1
    assert list(ids)[0] == rec.session_id


def test_timestamp_parseable(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.kb_add(_HUMAN_SOCRATES)
    rec.close()

    ev = _read_lines(rec.log_path)[0]
    # Should parse without raising
    dt = datetime.fromisoformat(ev["timestamp"])
    assert dt.tzinfo is not None  # must be UTC-aware


# ---------------------------------------------------------------------------
# Robustness tests
# ---------------------------------------------------------------------------


def test_close_idempotent(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)
    rec.close()
    rec.close()  # second close must not raise


def test_disabled_no_io(tmp_path) -> None:
    rec = SessionRecorder(enabled=False, corpus_dir=tmp_path)
    # All methods should be no-ops and return None
    assert rec.kb_add(_HUMAN_SOCRATES) is None
    assert rec.query_start(_QUERY) is None
    assert rec.pick(_STATE_0, _STATE_1, 0, "mortal_1") is None
    assert rec.query_end("abort") is None
    assert rec.close() is None
    # No files created in corpus_dir
    assert list(tmp_path.glob("*.jsonl")) == []


def test_concurrent_distinct_session_ids(tmp_path) -> None:
    r1 = SessionRecorder(corpus_dir=tmp_path)
    r2 = SessionRecorder(corpus_dir=tmp_path)
    assert r1.session_id != r2.session_id
    r1.close()
    r2.close()


def test_serialization_error_emits_log_error_and_session_continues(tmp_path) -> None:
    rec = SessionRecorder(corpus_dir=tmp_path)

    with patch("hlmr.log.recorder._clause_to_dict", side_effect=RuntimeError("serialization boom")):
        rec.kb_add(_HUMAN_SOCRATES)  # should NOT raise

    # The failed event should produce a log_error line
    lines = _read_lines(rec.log_path)
    assert len(lines) == 1
    assert lines[0]["event_type"] == "log_error"
    assert "serialization boom" in lines[0]["error"]

    # Subsequent events still record normally
    rec.kb_add(_HUMAN_SOCRATES)
    lines = _read_lines(rec.log_path)
    assert len(lines) == 2
    assert lines[1]["event_type"] == "kb_add"

    rec.close()
