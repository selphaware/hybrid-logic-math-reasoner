# HLMR Session Log Schema — version 2

**Current version: 2.** v1 events remain readable; readers check
`hlmr_log_version` to distinguish v1 events from v2 events. v2 events
added in M2 (Session 4b) use `"event"` (not `"event_type"`) as the top-level
field name, and add dispatcher-specific events. v1 events are unaffected.

Every interactive REPL session and every benchmark run appends events to
`corpus/<session-id>.jsonl`. Each line is a self-contained JSON object.

Logs are gitignored. The schema is versioned; bump `hlmr_log_version` to `2`
and update this document whenever the schema changes in a backward-incompatible
way (field renamed, removed, or reinterpreted). Adding an optional field to a
new event type is compatible and does not require a version bump.

---

## Session ID

Format: `YYYY-MM-DDTHH-MM-SS_<8 hex chars>` (e.g., `2026-05-03T14-22-31_a3f2c1d4`).

Dashes replace colons so the string is safe as a filename on Windows. The 4-byte
random suffix prevents collisions between sessions started within the same second.

---

## Required top-level fields

Every event line contains these four fields:

| Field | Type | Description |
|-------|------|-------------|
| `hlmr_log_version` | int | Schema version — currently `1` |
| `timestamp` | str | UTC ISO 8601 (e.g., `2026-05-03T14:22:31.123456+00:00`) |
| `event_type` | str | One of the event types listed below |
| `session_id` | str | Identifies the session; identical across all events |

---

## Event types

### `kb_add`

Emitted once per clause when the user adds it to the knowledge base.

```json
{
  "hlmr_log_version": 1,
  "timestamp": "2026-05-03T14:22:31.000000+00:00",
  "event_type": "kb_add",
  "session_id": "2026-05-03T14-22-31_a3f2c1d4",
  "clause": {
    "name": "human_1",
    "head": {"_type": "Atom", "pred": "human", "args": [{"_type": "Const", "value": "socrates"}]},
    "body": []
  }
}
```

### `query_start`

Emitted when the user submits a new `?-` query.

```json
{
  "hlmr_log_version": 1,
  "timestamp": "2026-05-03T14:22:31.000000+00:00",
  "event_type": "query_start",
  "session_id": "2026-05-03T14-22-31_a3f2c1d4",
  "query": {"_type": "Atom", "pred": "mortal", "args": [{"_type": "Const", "value": "socrates"}]}
}
```

### `pick`

Emitted for each manual SLD resolution step (one per user choice).

```json
{
  "hlmr_log_version": 1,
  "timestamp": "2026-05-03T14:22:32.000000+00:00",
  "event_type": "pick",
  "session_id": "2026-05-03T14-22-31_a3f2c1d4",
  "state_before": <sld_state>,
  "state_after": <sld_state>,
  "candidate_index": 0,
  "clause_name": "mortal_1"
}
```

`<sld_state>` shape:

```json
{
  "goals": [<formula>, ...],
  "subst": {"?X_1": <term>, ...},
  "history": [
    {
      "goal_resolved": <formula>,
      "clause_name": "mortal_1",
      "unifier": {"?X_1": <term>, ...}
    }
  ]
}
```

### `query_end`

Emitted when a query terminates (any outcome).

| `outcome` value | Meaning |
|-----------------|---------|
| `"success"` | Query succeeded; proof was kernel-checked |
| `"abort"` | User cancelled the query |
| `"no_candidates"` | No matching clauses for the current goal |
| `"render_error"` | Renderer raised `RenderError` |

`final_subst` and `proof_hash` are present **only** when `outcome == "success"`.

```json
{
  "hlmr_log_version": 1,
  "timestamp": "2026-05-03T14:22:33.000000+00:00",
  "event_type": "query_end",
  "session_id": "2026-05-03T14-22-31_a3f2c1d4",
  "outcome": "success",
  "final_subst": {"?X": {"_type": "Const", "value": "alice"}},
  "proof_hash": "a3f2c1d4e5f6..."
}
```

`proof_hash` is the hex-encoded SHA-256 of the canonical proof JSON:
`json.dumps(_proof_to_dict(proof), sort_keys=True).encode("utf-8")`.

### `log_error`

Emitted in place of a failed event when a serialization error occurs inside
the logger. The session continues; only the failed event is replaced.

```json
{
  "hlmr_log_version": 1,
  "timestamp": "2026-05-03T14:22:31.000000+00:00",
  "event_type": "log_error",
  "session_id": "2026-05-03T14-22-31_a3f2c1d4",
  "error": "some error message"
}
```

---

## v2 events (M2 dispatcher, Session 4b+)

v2 events use `"event"` as the field name (not `"event_type"`), and carry
`"hlmr_log_version": 2`. They are emitted via `SessionRecorder._write_v2_event()`.

### `dispatch_classify`

Emitted by `Dispatcher.dispatch()` after every classification decision.

```json
{
  "hlmr_log_version": 2,
  "timestamp": "...",
  "event": "dispatch_classify",
  "session_id": "...",
  "goal": "<str repr of Atom|Equals>",
  "decision": {
    "target": "kb" | "z3" | "sympy" | "rejected",
    "reason": "transcendental" | "contested_convention" | ... | null,
    "detail": "<free-form string>"
  }
}
```

### `dispatch_route`

Emitted by `_dispatch_z3` / `_dispatch_sympy` just before calling the bridge.

```json
{
  "hlmr_log_version": 2,
  "event": "dispatch_route",
  "goal": "<str>",
  "target": "z3" | "sympy",
  "timeout_ms": 5000
}
```

### `solver_call`

Emitted after a bridge call completes; records elapsed time.

```json
{
  "hlmr_log_version": 2,
  "event": "solver_call",
  "solver": "z3" | "sympy",
  "constraints": "<stringified>",
  "elapsed_ms": 12
}
```

### `solver_result`

Emitted paired with `solver_call`; names the result kind.

```json
{
  "hlmr_log_version": 2,
  "event": "solver_result",
  "solver": "z3" | "sympy",
  "result_kind": "Z3Sat" | "Z3Unsat" | "Z3Unknown" | "Z3Timeout"
               | "SymPyFiniteRoots" | "SymPyNoRealRoots"
               | "SymPyConditionSet" | "SymPyError",
  "summary": "<short opaque summary>"
}
```

### `verify_arith`

Emitted by `_verify_arith_ground` after every kernel round-trip.

```json
{
  "hlmr_log_version": 2,
  "event": "verify_arith",
  "ground_atom": "<str>",
  "result": "ok" | "evaluation_false" | "malformed_arithmetic"
}
```

### `dispatch_outcome`

Emitted as the final verdict of `Dispatcher.dispatch()`.

```json
{
  "hlmr_log_version": 2,
  "event": "dispatch_outcome",
  "outcome_kind": "UniqueSolution" | "MultipleSolutions"
                | "InfinitelyManySolutions" | "NoSolution"
                | "Underdetermined" | "OutsideFragment",
  "binding": {"?X": "5", ...} | null,
  "free_metas": ["?X", "?Y"] | null,
  "outside_fragment_reason": "transcendental" | ... | null
}
```

### `contested_rejection`

Emitted when a solver witness is dropped as Case 2 (contested convention).

```json
{
  "hlmr_log_version": 2,
  "event": "contested_rejection",
  "ground_atom": "<str>",
  "route": "sympy" | "z3",
  "binding": {"?X": "0"}
}
```

---

## v1/v2 backward compatibility

- v1 events use `event_type` key; v2 events use `event` key.
- Readers can distinguish by checking which key is present.
- `hlmr_log_version` is always present and authoritative.
- v1 events in a mixed log file remain valid v1 events; readers that only
  understand v1 may skip v2 events without loss of information.

---

## Formula and term encoding

Formula and term objects use the same `_type`-discriminated encoding as the
proof JSON format (see `ir/serialise.py`).

**Term `_type` values:** `Var`, `Const`, `Func`, `Meta`.

**Formula `_type` values:** `Atom`, `Equals`, `And`, `Or`, `Implies`, `Iff`,
`Not`, `Bot`, `ForAll`, `Exists`.

Example term encoding:

| IR object | JSON |
|-----------|------|
| `Const("alice")` | `{"_type": "Const", "value": "alice"}` |
| `Var("X")` | `{"_type": "Var", "name": "X"}` |
| `Meta("?X_1")` | `{"_type": "Meta", "name": "?X_1"}` |
| `Func("s", (Const(0),))` | `{"_type": "Func", "name": "s", "args": [{"_type": "Const", "value": 0}]}` |
