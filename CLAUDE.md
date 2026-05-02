# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

**The repo currently contains specs only — no source code yet.** `src/`,
`tests/`, `proofs/` etc. described below are the planned layout from the
PRDs; they will be created during M0 implementation. Do not assume any
file under `src/hlmr/` exists until you have listed the directory.

## The PRDs are the source of truth

Three documents drive all work and must be read before implementation:

- `prd.md` — canonical strategic spec. Changes infrequently. Per-milestone
  PRDs may not contradict it.
- `prd_milestone_0.md` — M0 implementation spec (kernel + IR + CLI checker).
- `prd_milestone_1.md` — M1 implementation spec (KB, unification, manual
  SLD, ND renderer, parser, REPL, logging).

Each per-milestone PRD has a §0 "Pre-flight check" the agent must follow
verbatim at session start: state model, verify environment, read the
whole PRD, propose order. Do not skip these.

## Architectural commitments (load-bearing — see `prd.md` §4)

These constrain every milestone. Violating them is wrong by construction:

- **The kernel is the only trusted component.** Search engines, unifiers,
  SMT bridges, renderers, parsers, REPL UIs can all be buggy without
  compromising soundness — provided every claimed proof is run through
  the kernel before being reported as success.
- **Kernel isolation.** `src/hlmr/kernel/*.py` imports only from
  `src/hlmr/ir/` and stdlib. Test-enforced (`test_kernel_isolation.py`)
  from M0 onward.
- **The IR is the single bus.** Every module reads/writes the formula
  and proof types in `src/hlmr/ir/`. No private representations.
- **No module replicates rule logic.** All 22 ND rule semantics live
  only in `kernel/rules.py`.
- **No kernel changes** beyond what each PRD explicitly permits. M1
  permits exactly one: a top-of-`check_proof` rejection of any formula
  containing a `Meta` term. Anything else requires asking the user first.
- Any proposed change to `src/hlmr/kernel/` (other than the documented
  M1 `Meta` rejection) requires asking the user first — do not edit
  kernel files unilaterally, including for refactors.
- **`solvers/` (M2+) is the only place Z3 and SymPy are imported.**
- **Soundness over completeness.** False negatives are acceptable;
  false positives are catastrophic.

## Model-selection gates (read before starting any task)

The PRDs assign work to specific Claude models. Implementing the wrong
section in the wrong model produces work that has to be redone.

- **Sonnet 4.6** is the default and handles all of M0, plus most of M1
  (IR additions, `unify/`, `solve/sld.py`, parser, REPL, logging, tests,
  demos, docs).
- **Opus 4.7 is required** for: module-boundary design, the SLD-to-ND
  renderer design (M1 `solve/render.py` — Opus produces
  `solve/RENDER_DESIGN.md` first; Sonnet then implements against it),
  the dispatcher (M2), search-strategy design (M3), and any IR change
  beyond the two M1 additions (`Meta`, `KnowledgeBase`).

If you are Sonnet and hit a section marked `[REQUIRES OPUS 4.7 — DESIGN]`,
**stop and ask the user to switch models** rather than guessing.

## The do-not-invent rule

Reproduced from each milestone PRD §0 because it is enforced project-wide:

- Do not claim a command succeeded without showing its output.
- Do not claim a test passed without running it.
- Do not claim a module exists without listing the directory.

## Environment (Windows / PowerShell)

A Python 3.12.13 venv lives at `env_hlmr/`. Activate or invoke directly:

```powershell
# Activate (PowerShell)
.\env_hlmr\Scripts\Activate.ps1

# Or call the interpreter without activating (works across separate
# Bash tool calls, which do not share shell state)
.\env_hlmr\Scripts\python.exe -m pytest
.\env_hlmr\Scripts\python.exe -m hlmr check proofs\m0\03_de_morgan.json
```

Once `pyproject.toml` exists, install in editable mode with test deps:

```powershell
pip install -e ".[test]"
```

Runtime dependencies are tightly bounded: M0 stdlib-only; M1 adds `lark`
and `prompt_toolkit`; M2 adds `z3-solver` and `sympy`; M3 may add `torch`
only if the optional learned ranker is built. **Adding any other runtime
dependency requires explicit user approval.**

## Common commands (once source exists)

```powershell
# Run the test suite
pytest

# Lint
ruff check src/hlmr

# Run a specific test file
pytest tests/test_kernel_sound.py

# Single test
pytest tests/test_kernel_sound.py::test_modus_ponens

# Check a proof
python -m hlmr check proofs\m0\03_de_morgan.json

# Pretty-print a proof in Fitch style
python -m hlmr show proofs\m0\03_de_morgan.json

# (M1) Open the REPL
python -m hlmr repl

# (M1) Run a demo
python -m hlmr demo syllogism

# Regenerate example proofs (M0)
python proofs\m0\generate.py
```

## Coding standards

- Python 3.12+ throughout.
- Modern type hints: `list[int]`, `X | Y`. Do **not** import
  `Optional`/`List`/`Union` from `typing`.
- Type hints required on every public function and dataclass field.
- IR data carriers are **frozen dataclasses** with structural `__eq__`
  / `__hash__` — formula equality must be referentially transparent
  (this is a soundness aid).
- ASCII-only formula rendering through M1; Unicode is M2+.
- Modular and shallow. Wrapper classes that delegate one method to
  another are forbidden. Modules over ~400 lines signal a split;
  ~600 is a hard limit.
- Errors are typed (frozen dataclasses), not strings. Tests assert
  the error class, not message text.

## Testing expectations

- Soundness regression suite (valid proofs verify) and **unsoundness
  regression suite** (invalid proofs fail with the correct error type)
  both run before every commit. An unsoundness regression is a
  merge-blocker.
- Coverage: ≥95% on `kernel/`, `unify/`, `solve/sld.py`; ≥85% on
  renderers, dispatcher, IR; ≥70% on parsers, REPL, CLI.
- `hypothesis` for property tests: JSON round-trips, capture-avoiding
  `subst`, `check_proof` determinism, unifier `apply(unify(s,t),s) ==
  apply(unify(s,t),t)`.
- `test_kernel_isolation.py` is a guardrail — it walks `kernel/*.py`,
  parses imports with `ast`, and asserts every import is stdlib,
  under `hlmr.ir`, or intra-kernel (`hlmr.kernel.*`). The invariant
  is: kernel never imports from untrusted modules (`hlmr.unify`,
  `hlmr.solve`, `hlmr.parse`, etc.). Never add untrusted modules to
  the allow-list.

## Logging

Every interactive REPL session and every benchmark run writes JSONL to
`corpus/<session-id>.jsonl` with a versioned schema (`hlmr_log_version`).
Logs are gitignored. Logging is in M1's definition of done — it is
not retrofittable later cheaply.
