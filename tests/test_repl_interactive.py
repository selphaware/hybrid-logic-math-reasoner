"""Integration tests for the REPL loop via prompt_toolkit PipeInput."""
from __future__ import annotations

import io
import json

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from hlmr.ir.serialise import from_json
from hlmr.kernel import check_proof
from hlmr.kernel.errors import Verified
from hlmr.repl import run_repl

# ---------------------------------------------------------------------------
# Helper: run REPL with scripted input
# ---------------------------------------------------------------------------


def _run(
    lines: list[str],
    tmp_path,
    no_log: bool = True,
) -> tuple[str, object]:
    """Feed *lines* to the REPL, return (stdout_text, recorder_log_path).

    Each element of *lines* is sent as one input line.  A ':quit' sentinel is
    appended automatically if the last line is not already ':quit', so every
    integration test exits via the normal :quit path and never relies on
    PipeInput EOF semantics (which are unreliable on Windows).
    Logs are written to a subdirectory of tmp_path.
    """
    buf = io.StringIO()
    corpus_dir = tmp_path / "corpus"

    # Safety: always exit via :quit so the loop never blocks on an empty pipe.
    if not lines or lines[-1].strip() != ":quit":
        lines = list(lines) + [":quit"]

    with create_pipe_input() as inp:
        for line in lines:
            inp.send_text(line + "\n")
        run_repl(
            no_log=no_log,
            _input=inp,
            _output=DummyOutput(),
            _stdout=buf,
            _corpus_dir=corpus_dir,
        )

    log_files = list(corpus_dir.glob("*.jsonl")) if corpus_dir.exists() else []
    log_path = log_files[0] if log_files else None
    return buf.getvalue(), log_path


def _read_events(log_path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text().splitlines() if line]


# ---------------------------------------------------------------------------
# Syllogism KB fixture
# ---------------------------------------------------------------------------

_SYLLOGISM_LINES = [
    "human(socrates).",
    "mortal(X) :- human(X).",
]

_KINSHIP_LINES = [
    "parent(alice, bob).",
    "parent(bob, carol).",
    "ancestor(X, Y) :- parent(X, Y).",
    "ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).",
]


# ---------------------------------------------------------------------------
# Basic lifecycle
# ---------------------------------------------------------------------------


def test_quit_exits_cleanly(tmp_path) -> None:
    out, _ = _run([":quit"], tmp_path)
    assert "Bye" in out


def test_eof_handling(tmp_path, monkeypatch) -> None:
    """EOFError from session.prompt() must cause a clean exit with 'Bye'.

    This is a unit test of the exception branch, not an integration test
    through PipeInput — PipeInput does not surface EOF as EOFError reliably
    when the pipe is simply exhausted.
    """

    class _FakeSession:
        def prompt(self, *args, **kwargs):
            raise EOFError()

    monkeypatch.setattr(
        "hlmr.repl.interactive.PromptSession",
        lambda *args, **kwargs: _FakeSession(),
    )

    buf = io.StringIO()
    run_repl(no_log=True, _stdout=buf, _corpus_dir=tmp_path / "corpus")
    assert "Bye" in buf.getvalue()


def test_help_output(tmp_path) -> None:
    out, _ = _run([":help", ":quit"], tmp_path)
    assert ":load" in out
    assert ":export" in out


def test_session_id_announced(tmp_path) -> None:
    out, _ = _run([":quit"], tmp_path)
    assert "session" in out.lower()


# ---------------------------------------------------------------------------
# KB phase: clause entry and :load
# ---------------------------------------------------------------------------


def test_inline_clause_added(tmp_path) -> None:
    out, _ = _run(["human(socrates).", ":show kb", ":quit"], tmp_path)
    assert "human(socrates)" in out


def test_load_kb_from_file(tmp_path) -> None:
    pl = tmp_path / "kb.pl"
    pl.write_text("human(socrates).\nmortal(X) :- human(X).\n", encoding="utf-8")
    out, _ = _run([f":load {pl}", ":show kb", ":quit"], tmp_path)
    assert "human(socrates)" in out
    assert "mortal" in out


def test_load_nonexistent_file_shows_error(tmp_path) -> None:
    out, _ = _run([":load /does/not/exist.pl", ":quit"], tmp_path)
    assert "Error" in out or "error" in out


def test_show_kb_empty(tmp_path) -> None:
    out, _ = _run([":show kb", ":quit"], tmp_path)
    assert "empty" in out.lower()


def test_save_and_reload(tmp_path) -> None:
    saved = tmp_path / "saved.pl"
    out, _ = _run(
        ["human(socrates).", f":save {saved}", ":quit"],
        tmp_path,
    )
    assert saved.exists()
    text = saved.read_text(encoding="utf-8")
    assert "human(socrates)" in text


# ---------------------------------------------------------------------------
# Query phase: successful proof
# ---------------------------------------------------------------------------


def test_query_success_syllogism(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,       # add two clauses
            "?- mortal(socrates).",  # start query (auto-switches to query mode)
            "1",                     # pick mortal_1
            "1",                     # pick human_1
            ":quit",
        ],
        tmp_path,
    )
    assert "Solved" in out
    assert "kernel-verified" in out


def test_show_last_after_success(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",
            "1",
            ":show last",
            ":quit",
        ],
        tmp_path,
    )
    # render_fitch produces numbered lines
    assert "1." in out
    assert "Premise" in out


def test_export_proof_round_trip(tmp_path) -> None:
    export_path = tmp_path / "proof.json"
    _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",
            "1",
            f":export {export_path}",
            ":quit",
        ],
        tmp_path,
    )
    assert export_path.exists()
    proof = from_json(export_path.read_text(encoding="utf-8"))
    assert isinstance(check_proof(proof), Verified)


def test_show_last_before_any_query(tmp_path) -> None:
    out, _ = _run([":show last", ":quit"], tmp_path)
    assert "No proof" in out


def test_export_before_any_query(tmp_path) -> None:
    export_path = tmp_path / "proof.json"
    out, _ = _run([f":export {export_path}", ":quit"], tmp_path)
    assert "No proof" in out
    assert not export_path.exists()


# ---------------------------------------------------------------------------
# Query phase: back / abort / no_candidates
# ---------------------------------------------------------------------------


def test_back_reverts_pick(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",      # pick mortal_1 → goal: human(?X_1)
            "back",   # undo → goal restored: mortal(socrates)
            "1",      # pick mortal_1 again
            "1",      # pick human_1
            ":quit",
        ],
        tmp_path,
    )
    assert "Solved" in out
    assert "kernel-verified" in out


def test_back_at_start_shows_nothing_to_undo(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "back",    # nothing on the stack yet
            "1",       # pick mortal_1
            "1",       # pick human_1
            ":quit",
        ],
        tmp_path,
    )
    assert "Nothing to undo" in out
    assert "Solved" in out


def test_abort_leaves_last_proof_unchanged(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",
            "1",
            # Now last_proof is set. Run a second query and abort it.
            "?- mortal(socrates).",
            "abort",
            ":show last",   # should still show the first proof
            ":quit",
        ],
        tmp_path,
    )
    assert "Solved" in out            # from first query
    assert "Premise" in out           # from :show last


def test_no_candidates_message(tmp_path) -> None:
    out, _ = _run(
        [
            "human(socrates).",
            "?- mortal(socrates).",   # no mortal clauses in KB
            ":quit",
        ],
        tmp_path,
    )
    assert "No matching clauses" in out


def test_invalid_pick_index_shows_error(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "99",    # out of range
            "1",     # correct pick
            "1",
            ":quit",
        ],
        tmp_path,
    )
    assert "Choose 1" in out
    assert "Solved" in out


def test_candidates_redisplays(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "candidates",  # re-display
            "1",
            "1",
            ":quit",
        ],
        tmp_path,
    )
    # Candidates section appears at least twice
    assert out.count("Candidates:") >= 2


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


def test_explicit_query_mode_transition(tmp_path) -> None:
    out, _ = _run(
        [
            *_SYLLOGISM_LINES,
            ":query",
            "?- mortal(socrates).",
            "1",
            "1",
            ":edit",
            ":show kb",
            ":quit",
        ],
        tmp_path,
    )
    assert "Solved" in out
    assert "mortal" in out   # :show kb


def test_pick_outside_query_shows_error(tmp_path) -> None:
    out, _ = _run(
        [
            ":query",
            "1",        # pick with no active query
            ":quit",
        ],
        tmp_path,
    )
    assert "only valid during a query" in out


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_no_log_suppresses_file(tmp_path) -> None:
    _run([":quit"], tmp_path, no_log=True)
    corpus_dir = tmp_path / "corpus"
    assert not corpus_dir.exists() or list(corpus_dir.glob("*.jsonl")) == []


def test_logging_enabled_creates_file(tmp_path) -> None:
    _, log_path = _run(["human(socrates).", ":quit"], tmp_path, no_log=False)
    assert log_path is not None
    assert log_path.exists()


def test_all_four_event_types_logged(tmp_path) -> None:
    _, log_path = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",
            "1",
            ":quit",
        ],
        tmp_path,
        no_log=False,
    )
    assert log_path is not None
    events = _read_events(log_path)
    types = {e["event_type"] for e in events}
    assert "kb_add" in types
    assert "query_start" in types
    assert "pick" in types
    assert "query_end" in types


def test_query_end_success_logged(tmp_path) -> None:
    _, log_path = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",
            "1",
            ":quit",
        ],
        tmp_path,
        no_log=False,
    )
    events = _read_events(log_path)
    end_events = [e for e in events if e["event_type"] == "query_end"]
    assert len(end_events) == 1
    assert end_events[0]["outcome"] == "success"
    assert "proof_hash" in end_events[0]
    assert "final_subst" in end_events[0]


def test_abort_query_end_logged(tmp_path) -> None:
    _, log_path = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "abort",
            ":quit",
        ],
        tmp_path,
        no_log=False,
    )
    events = _read_events(log_path)
    end_events = [e for e in events if e["event_type"] == "query_end"]
    assert len(end_events) == 1
    assert end_events[0]["outcome"] == "abort"


# ---------------------------------------------------------------------------
# Kernel-reject defence-in-depth
# ---------------------------------------------------------------------------


def test_kernel_reject_defense(tmp_path, monkeypatch) -> None:
    """If check_proof rejects the rendered proof, the REPL must:
    - print a clear error message,
    - log query_end with outcome='render_error',
    - return to the top-level prompt without crashing,
    - NOT update last_proof.
    """
    from hlmr.kernel.errors import CheckFailure, StructuralError

    fake_failure = CheckFailure(line=1, reason=StructuralError("injected kernel rejection"))
    monkeypatch.setattr("hlmr.repl.interactive.check_proof", lambda _proof: fake_failure)

    corpus_dir = tmp_path / "corpus"
    out, log_path = _run(
        [
            *_SYLLOGISM_LINES,
            "?- mortal(socrates).",
            "1",   # pick mortal_1 → goal: human(socrates)
            "1",   # pick human_1 → goals empty → render → check_proof returns failure
            ":show last",   # must say "No proof" — last_proof must not have been set
            ":quit",
        ],
        tmp_path,
        no_log=False,
    )

    # 1. User-visible error message
    assert "kernel rejected" in out.lower()

    # 2. REPL did not crash — it reached :show last
    assert "No proof" in out

    # 3. last_proof was not updated
    assert "Premise" not in out   # render_fitch output would contain "Premise"

    # 4. Log records render_error outcome
    assert log_path is not None
    events = _read_events(log_path)
    end_events = [e for e in events if e["event_type"] == "query_end"]
    assert len(end_events) == 1
    assert end_events[0]["outcome"] == "render_error"
