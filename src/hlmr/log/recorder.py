from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from hlmr.ir.formula import Atom, Equals
from hlmr.ir.kb import Clause
from hlmr.ir.proof import Proof
from hlmr.ir.serialise import _formula_to_dict, _proof_to_dict, _term_to_dict
from hlmr.solve.sld import SLDState
from hlmr.unify.substitution import Substitution

LOG_VERSION = 1
LOG_VERSION_V2 = 2


# ---------------------------------------------------------------------------
# Private serialization helpers
# ---------------------------------------------------------------------------


def _clause_to_dict(clause: Clause) -> dict:
    return {
        "name": clause.name,
        "head": _formula_to_dict(clause.head),
        "body": [_formula_to_dict(b) for b in clause.body],
    }


def _subst_to_dict(s: Substitution) -> dict:
    return {k: _term_to_dict(v) for k, v in s.items()}


def _sld_state_to_dict(state: SLDState) -> dict:
    from hlmr.solve.sld import ClauseResolvedStep, DispatcherResolvedStep

    def _step_to_dict(step) -> dict:
        if isinstance(step, ClauseResolvedStep):
            return {
                "kind": "clause",
                "goal_resolved": _formula_to_dict(step.goal_resolved),
                "clause_name": step.clause_used.name,
                "unifier": _subst_to_dict(step.unifier),
            }
        # DispatcherResolvedStep
        return {
            "kind": "dispatcher",
            "goal_resolved": _formula_to_dict(step.goal_resolved),
            "route": step.route.value,
            "solver_summary": step.solver_summary,
        }

    return {
        "goals": [_formula_to_dict(g) for g in state.goals],
        "subst": _subst_to_dict(state.subst),
        "history": [_step_to_dict(step) for step in state.history],
    }


def _make_session_id() -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
    return f"{ts}_{secrets.token_hex(4)}"


# ---------------------------------------------------------------------------
# SessionRecorder
# ---------------------------------------------------------------------------


class SessionRecorder:
    """Records session events to a JSONL file.

    Path is ``corpus/<session-id>.jsonl`` by default. Construct with
    ``enabled=False`` to disable logging entirely: no file is created and
    all methods become no-ops.
    """

    def __init__(
        self,
        enabled: bool = True,
        corpus_dir: Path | str = "corpus",
    ) -> None:
        self._enabled = enabled
        self._session_id = _make_session_id()
        self._log_path: Path | None = None
        self._file = None
        if enabled:
            dir_path = Path(corpus_dir)
            dir_path.mkdir(parents=True, exist_ok=True)
            self._log_path = dir_path / f"{self._session_id}.jsonl"
            self._file = self._log_path.open("a", encoding="utf-8")

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    # ------------------------------------------------------------------
    # Internal write helpers
    # ------------------------------------------------------------------

    def _base(self, event_type: str) -> dict:
        return {
            "hlmr_log_version": LOG_VERSION,
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "session_id": self._session_id,
        }

    def _write_line(self, d: dict) -> None:
        assert self._file is not None
        self._file.write(json.dumps(d) + "\n")
        self._file.flush()

    def _log_error(self, err: Exception) -> None:
        """Write a log_error event. Silently swallows any further exception."""
        try:
            self._write_line({**self._base("log_error"), "error": str(err)})
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public event methods
    # ------------------------------------------------------------------

    def kb_add(self, clause: Clause) -> None:
        if not self._enabled:
            return
        try:
            self._write_line({**self._base("kb_add"), "clause": _clause_to_dict(clause)})
        except Exception as e:
            self._log_error(e)

    def query_start(self, query: Atom | Equals) -> None:
        if not self._enabled:
            return
        try:
            self._write_line({**self._base("query_start"), "query": _formula_to_dict(query)})
        except Exception as e:
            self._log_error(e)

    def pick(
        self,
        state_before: SLDState,
        state_after: SLDState,
        candidate_index: int,
        clause_name: str,
    ) -> None:
        if not self._enabled:
            return
        try:
            self._write_line(
                {
                    **self._base("pick"),
                    "state_before": _sld_state_to_dict(state_before),
                    "state_after": _sld_state_to_dict(state_after),
                    "candidate_index": candidate_index,
                    "clause_name": clause_name,
                }
            )
        except Exception as e:
            self._log_error(e)

    def query_end(
        self,
        outcome: str,
        final_subst: Substitution | None = None,
        proof: Proof | None = None,
    ) -> None:
        if not self._enabled:
            return
        try:
            record = {**self._base("query_end"), "outcome": outcome}
            if outcome == "success" and final_subst is not None and proof is not None:
                record["final_subst"] = _subst_to_dict(final_subst)
                canonical = json.dumps(_proof_to_dict(proof), sort_keys=True)
                record["proof_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
            self._write_line(record)
        except Exception as e:
            self._log_error(e)

    def _write_v2_event(self, event_type: str, payload: dict) -> None:
        """Write a v2-schema event (DISPATCH_DESIGN.md §10)."""
        if not self._enabled:
            return
        assert self._file is not None
        record = {
            "hlmr_log_version": LOG_VERSION_V2,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event_type,
            "session_id": self._session_id,
        }
        record.update(payload)
        self._write_line(record)

    def close(self) -> None:
        """Flush and close the log file. Idempotent."""
        if self._file is not None:
            self._file.close()
            self._file = None
