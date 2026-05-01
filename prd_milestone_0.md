# HLMR Milestone 0 — Kernel and IR

**Status:** Draft v1
**Supplements:** `prd.md` (canonical project spec, do not contradict)
**Last updated:** 2026-05-01
**Repository state at M0 start:** specs only; no source code yet

---

## 0. Pre-flight check — read this first, every session

**Before writing any code, state which Claude model you are running as.**

- **Claude Sonnet 4.6** — implements all of M0. Default and recommended.
- **Claude Opus 4.7** — not required for M0. The design is fully
  specified below; Sonnet should implement directly.

If you are Sonnet 4.6 and you reach a section you cannot implement
from the spec, stop and ask the user — do not proceed by guessing.

**Verify environment before coding:**

1. State your model.
2. Confirm Python 3.12+: `env_hlmr\Scripts\python.exe --version`.
3. Confirm `prd.md` and `prd_milestone_0.md` are present at repo root.
4. Read this entire document before writing any code.
5. Then propose the implementation order to the user before starting.

**Do-not-invent rule.** Do not claim a command succeeded without
showing its output. Do not claim a test passed without running it.
Do not claim a module exists without listing the directory.

---

## 1. Executive summary

Milestone 0 delivers the trusted core: data types for formulas and
proofs, a function that decides whether a proof is valid, and a CLI
that runs that function on a JSON file.

No interactivity. No proof construction. No solving. No parsing. Pure
library plus thin CLI.

This is the foundation every later milestone builds on. The kernel
will not change between M0 and the end of V1, with one tiny exception
in M1 (a defense-in-depth `Meta` rejection). Every architectural
commitment in `prd.md` §4 either originates here or is enforced here.

---

## 2. How M0 fits

| Milestone | Adds | Status |
|---|---|---|
| **0 (this)** | Kernel, IR, CLI checker | This document |
| 1 | Manual solver, KB, unification, REPL | `prd_milestone_1.md` |
| 2 | Z3 + SymPy + dispatcher | spec to write |
| 3 | Automated search | spec to write |

Nothing depends on M0 being "polished" — it depends on M0 being
**correct**. A solid kernel that catches every misuse is more valuable
than a fast or pretty one. Performance work begins in M3 if at all.

---

## 3. Scope

### 3.1 In scope

- Term and formula classes for first-order logic with equality
- Capture-avoiding substitution
- Free-variable computation
- Fitch-style proofs as flat lists of lines tagged by box depth
- 22 inference rules (see §7)
- Eigenvariable side conditions on `forallI` and `existsE`
- Box scoping (accessibility, discharge)
- JSON serialisation with versioned schema
- Structured error types — typed, not strings
- CLI: `check` and `show` subcommands
- Test suites: soundness (valid proofs verify), unsoundness (invalid
  proofs fail with specific error types), substitution properties,
  JSON round-trips, kernel-isolation enforcement

### 3.2 Out of scope

- Metavariables / unknowns (M1)
- Parser, REPL, knowledge base (M1)
- Z3, SymPy, any external solver (M2)
- Tactics, search, rendering (M1+)
- Logging — M0 has no events to log; logging machinery arrives in M1
- Performance work
- Pretty Unicode formula rendering (ASCII only for M0)

### 3.3 What "done" looks like

The CLI verifies twelve example proofs in `proofs/m0/`, rejects three
deliberately broken ones with the right error types, and the test
suite runs green with the coverage targets in §9.

---

## 4. Architectural commitments scoped to M0

These are reproduced from `prd.md` §4 because they constrain M0
directly.

- **The kernel is the only trusted component.** The kernel directory
  contains `errors.py`, `scope.py`, `rules.py`, `check.py`. Everything
  is small, audit-friendly, and exhaustively tested.
- **Kernel imports only from `ir/` and stdlib.** Enforced by a
  `test_kernel_isolation.py` test that walks `kernel/*.py` source
  files and asserts the import set is a subset of `{ir, stdlib}`.
- **The IR is the single bus.** Every other module — present and
  future — reads and writes the same formula and proof types defined
  in `ir/`.
- **No module replicates rule logic.** All ND rule semantics live in
  `kernel/rules.py`.
- **Soundness over completeness.** The kernel may be conservative —
  rejecting some proofs a more clever checker would accept — but it
  must never accept an invalid proof.

---

## 5. Module layout

```
src/hlmr/
├── __init__.py            Top-level exports
├── __main__.py            For `python -m hlmr`
├── cli.py                 argparse CLI: check, show
├── ir/
│   ├── __init__.py        Re-exports
│   ├── formula.py         Term, Var, Const, Func, Atom, Equals,
│                          Not, And, Or, Implies, Iff, Bot,
│                          ForAll, Exists; free_vars; subst
│   ├── justification.py   Premise, Assumption, RuleApp
│   ├── proof.py           ProofLine, Proof
│   └── serialise.py       to_json, from_json, schema v1
└── kernel/
    ├── __init__.py        Re-exports check_proof, RULES, error types
    ├── errors.py          Verified, CheckFailure, RuleError + subtypes
    ├── scope.py           is_accessible, is_box, current_depth
    ├── rules.py           22 rule checkers + RULES dict
    └── check.py           check_proof()
```

Tests:

```
tests/
├── test_substitution.py        free_vars, subst, capture-avoidance
├── test_serialise.py           JSON round-trips
├── test_kernel_sound.py        valid proofs verify
├── test_kernel_unsound.py      invalid proofs fail with specific errors
└── test_kernel_isolation.py    kernel imports nothing outside ir/+stdlib
```

Examples:

```
proofs/m0/
├── 01_modus_ponens.json
├── 02_imp_reflexive.json
├── 03_de_morgan.json
├── 04_contrapositive.json
├── 05_or_commutative.json
├── 06_double_negation.json
├── 07_forall_instantiate.json
├── 08_forall_rename.json
├── 09_exists_elim.json
├── 10_eq_subst.json
├── 11_eq_transitive.json
├── 12_ex_falso.json
├── 99_BAD_andI.json            Must FAIL with FormulaMismatch
├── 99_BAD_oos.json             Must FAIL with OutOfScope
└── 99_BAD_eigenvar.json        Must FAIL with EigenvarViolation
```

A small generator script `proofs/m0/generate.py` builds the JSON files
from Python — hand-writing JSON is tedious and error-prone.

---

## 6. IR specification

All term and formula classes are **frozen dataclasses** with structural
`__eq__` and `__hash__`. This is a soundness aid: formula equality is
referentially transparent.

### 6.1 Terms

```python
class Term: ...                          # base, no fields

@dataclass(frozen=True)
class Var(Term):
    name: str                            # logical variable, e.g. "x"

@dataclass(frozen=True)
class Const(Term):
    value: object                        # int, str, etc.

@dataclass(frozen=True)
class Func(Term):
    name: str
    args: tuple[Term, ...]               # uninterpreted function term
```

### 6.2 Formulas

```python
class Formula: ...                       # base

@dataclass(frozen=True)
class Atom(Formula):
    pred: str
    args: tuple[Term, ...] = ()          # nullary atom = propositional var

@dataclass(frozen=True)
class Equals(Formula):
    lhs: Term
    rhs: Term

@dataclass(frozen=True)
class Not(Formula):
    body: Formula

@dataclass(frozen=True)
class And(Formula):    left: Formula; right: Formula

@dataclass(frozen=True)
class Or(Formula):     left: Formula; right: Formula

@dataclass(frozen=True)
class Implies(Formula): left: Formula; right: Formula

@dataclass(frozen=True)
class Iff(Formula):    left: Formula; right: Formula

@dataclass(frozen=True)
class Bot(Formula): ...                  # falsum

@dataclass(frozen=True)
class ForAll(Formula): var: str; body: Formula

@dataclass(frozen=True)
class Exists(Formula): var: str; body: Formula
```

ASCII pretty-printing only for M0. `repr` produces parser-readable
output (Unicode rendering is M1+).

### 6.3 Free variables and substitution

```python
def free_vars_term(t: Term) -> frozenset[str]: ...
def free_vars(f: Formula) -> frozenset[str]: ...

def subst_term(t: Term, var: str, replacement: Term) -> Term: ...
def subst(f: Formula, var: str, replacement: Term) -> Formula: ...
```

`subst` is **capture-avoiding**. If substituting a term into the body
of a quantifier would capture a free variable in `replacement`, the
quantifier's bound variable is renamed first via a `_fresh()` helper.
This is the foundation of FOL soundness — get it wrong and `forallE`
can produce nonsense.

Test cases that must pass:

- `subst(P(x), "x", Const(7)) == P(Const(7))`
- `subst(forall y. P(x,y), "x", Var("y"))` renames the bound `y`
  before substituting (avoids capture)
- `subst(forall x. P(x), "x", t) == forall x. P(x)` (bound var is
  shielded)

### 6.4 Justifications

```python
@dataclass(frozen=True)
class Premise: ...                       # depth-0 only

@dataclass(frozen=True)
class Assumption: ...                    # opens a box (depth+1)

@dataclass(frozen=True)
class RuleApp:
    rule: str                            # e.g. "andI", "forallE"
    line_refs: tuple[int, ...] = ()      # 1-indexed line numbers
    box_refs: tuple[tuple[int, int], ...] = ()   # (start, end) pairs
    extra: dict = field(default_factory=dict)    # rule-specific data

Justification = Premise | Assumption | RuleApp
```

**Eigenvariables for `forallI` and `existsE` go in `RuleApp.extra`,
not as a separate justification kind.** This keeps the IR small. The
checker reads `extra["eigenvar"]` and validates the freshness
condition.

### 6.5 Proof structure

```python
@dataclass(frozen=True)
class ProofLine:
    number: int                          # 1-indexed, must match position
    formula: Formula
    justification: Justification
    box_depth: int                       # 0 = top level

@dataclass(frozen=True)
class Proof:
    lines: tuple[ProofLine, ...]
    goal: Formula | None = None          # if set, last line must match

    def line(self, n: int) -> ProofLine: ...
    def prefix(self, n: int) -> "Proof": ...
```

Box structure is **recovered from depth changes**, not stored
explicitly. A line at depth `d+1` immediately after one at depth `d`
opens a box (must be an `Assumption`). A line at depth `d` after one
at depth `d+1` closes the box.

### 6.6 JSON serialisation

```python
SCHEMA_VERSION = 1

def to_json(p: Proof, indent: int = 2) -> str: ...
def from_json(s: str) -> Proof: ...
```

Schema is human-readable (intentional, for the prototype period).
Unknown schema versions are rejected with a clear error.

Term-valued and formula-valued entries in `RuleApp.extra` are wrapped
with a `_type` discriminator (`{"_type": "term", "value": ...}`) so
the deserialiser can reconstruct them.

---

## 7. Kernel specification

### 7.1 Errors

```python
@dataclass(frozen=True)
class Verified:
    @property
    def ok(self) -> bool: return True
    def __bool__(self) -> bool: return True

@dataclass(frozen=True)
class CheckFailure:
    line: int                            # 1-indexed offending line
    reason: "RuleError"
    @property
    def ok(self) -> bool: return False
    def __bool__(self) -> bool: return False

CheckResult = Verified | CheckFailure
```

`RuleError` is an exception base class. Subtypes — all frozen
dataclasses — are:

| Error | When raised |
|---|---|
| `UnknownRule` | `RuleApp.rule` is not in `RULES` |
| `WrongRefCount` | Line/box reference counts don't match the rule's signature |
| `WrongFormulaShape` | Conclusion or referenced line isn't the shape the rule expects |
| `FormulaMismatch` | Expected formula doesn't equal got formula |
| `OutOfScope` | A referenced line is in a discharged box |
| `BadBoxRef` | A `box_refs` pair is malformed or undischarged |
| `EigenvarViolation` | Eigenvariable freshness/escape condition fails |
| `MissingExtra` | Required `extra` field absent |
| `StructuralError` | Sequencing, depth, premise placement |
| `GoalMismatch` | `proof.goal` set but final line doesn't match |

**No string errors.** Each error carries structured data (which line,
which formula, which eigenvar) so tests can assert error type and
content without parsing messages.

### 7.2 Box scoping

```python
def is_accessible(m: int, n: int, proof: Proof) -> bool: ...
def is_box(start: int, end: int, proof: Proof) -> tuple[bool, str]: ...
def current_depth(proof: Proof) -> int: ...
```

Accessibility rule: line `m` is accessible from line `n` (with `m < n`)
iff for every line `k` with `m < k ≤ n`, `box_depth(k) >= box_depth(m)`.
Equivalently: `m`'s box is still open at `n`.

Box reference `(start, end)` is well-formed iff:

- `1 ≤ start ≤ end < n` (where `n` is the line using the reference)
- `box_depth(start) > 0`
- For all `k` in `[start, end]`, `box_depth(k) >= box_depth(start)`
- `proof.line(n).box_depth < proof.line(start).box_depth` (the box is
  discharged before line `n`)

### 7.3 Rules — the 22

For each rule below: `lines` is the count of `line_refs`, `boxes` the
count of `box_refs`, `extra` the required keys in `RuleApp.extra`.
`P, Q, R` are formulas; `t, u` are terms; `x, y` are variable names.

#### Propositional (16)

| Rule | lines | boxes | extra | What it does |
|---|---|---|---|---|
| `andI` | 2 | 0 | — | from `P, Q` derive `P & Q` |
| `andE_L` | 1 | 0 | — | from `P & Q` derive `P` |
| `andE_R` | 1 | 0 | — | from `P & Q` derive `Q` |
| `orI_L` | 1 | 0 | — | from `P` derive `P | Q` (`Q` from conclusion) |
| `orI_R` | 1 | 0 | — | from `Q` derive `P | Q` (`P` from conclusion) |
| `orE` | 1 | 2 | — | from `P|Q`, box `[P ⊢ R]`, box `[Q ⊢ R]` derive `R` |
| `impI` | 0 | 1 | — | from box `[P ⊢ Q]` derive `P -> Q` |
| `impE` | 2 | 0 | — | modus ponens: from `P -> Q, P` derive `Q` |
| `notI` | 0 | 1 | — | from box `[P ⊢ ⊥]` derive `~P` |
| `notE` | 2 | 0 | — | from `P, ~P` derive `⊥` |
| `botE` | 1 | 0 | — | from `⊥` derive any conclusion |
| `iffI` | 2 | 0 | — | from `P -> Q, Q -> P` derive `P <-> Q` |
| `iffE_L` | 2 | 0 | — | from `P <-> Q, P` derive `Q` |
| `iffE_R` | 2 | 0 | — | from `P <-> Q, Q` derive `P` |
| `reit` | 1 | 0 | — | reiterate (copy) a line from an enclosing scope |
| `PBC` | 0 | 1 | — | classical: from box `[~P ⊢ ⊥]` derive `P` |

#### First-order (4)

| Rule | lines | boxes | extra | What it does |
|---|---|---|---|---|
| `forallI` | 0 | 1 | `eigenvar: str` | from box `[ ⊢ P[a/x]]` derive `forall x. P` |
| `forallE` | 1 | 0 | `term: Term` | from `forall x. P` derive `P[t/x]` |
| `existsI` | 1 | 0 | `term: Term` | from `P[t/x]` derive `exists x. P` |
| `existsE` | 1 | 1 | `eigenvar: str` | from `exists x. P` and box `[P[a/x] ⊢ Q]` derive `Q` |

**Eigenvariable side conditions** for `forallI`:

- `eigenvar` must not appear free in any earlier accessible line
  (lines `1..start-1` accessible from line `start` of the box).
- `eigenvar` must not appear free in the body of the universal
  (otherwise the substitution didn't capture all occurrences and the
  rule is unsound).
- The end-of-box formula must equal `subst(body, x, Var(eigenvar))`.

**Eigenvariable side conditions** for `existsE`:

- `eigenvar` must not appear free in the existential being eliminated.
- `eigenvar` must not appear free in any earlier accessible line.
- `eigenvar` must not appear free in the conclusion (the eigenvar
  cannot escape its scope).
- The first line of the box must equal `subst(body, x, Var(eigenvar))`.

#### Equality (2)

| Rule | lines | boxes | extra | What it does |
|---|---|---|---|---|
| `eqRefl` | 0 | 0 | — | derive `t = t` for any term `t` |
| `eqSubst` | 2 | 0 | `var: str, template: Formula` | from `t = u, P[t/x]` derive `P[u/x]` |

For `eqSubst`, `template` is `P[x]` (a formula containing free `x`),
and the rule checks that:

- The first reference is `Equals(t, u)`.
- The second reference equals `subst(template, var, t)`.
- The conclusion equals `subst(template, var, u)`.

### 7.4 `check_proof`

```python
def check_proof(proof: Proof) -> CheckResult: ...
```

Algorithm:

1. **Sanity checks first.** Empty proof rejected. Line numbers must
   be sequential `1..N`. Box depth must be non-negative and increase
   by at most 1 per line. Premises must be at depth 0. Depth increases
   only at `Assumption` lines.
2. **Per-line checking.** For each line:
   - `Premise` and `Assumption`: no further check.
   - `RuleApp`: look up rule in `RULES` dict; call its checker; if it
     returns a `RuleError`, return `CheckFailure(line.number, error)`.
3. **Final state.** Proof must end at depth 0 (every box discharged).
4. **Goal check.** If `proof.goal` is set, the final line's formula
   must equal it.

Return `Verified()` iff all checks pass.

---

## 8. CLI

```
python -m hlmr check <path/to/proof.json>
python -m hlmr show  <path/to/proof.json>
```

`check`: prints `verified (N lines)` on success, structured failure
on rejection. Exit codes: 0 verified, 1 rejected, 2 malformed input.

`show`: pretty-prints the proof in Fitch style with indented box bars,
line numbers, and justification annotations. ASCII only.

Implementation: `argparse` with subparsers. Single file, `cli.py`.

---

## 9. Testing

### 9.1 Required suites

- `test_substitution.py` — free variables, capture avoidance, mutation
  safety. Hypothesis property tests for `free_vars(subst(f, x, t))`.
- `test_serialise.py` — JSON round-trip for all formula and proof
  shapes. Schema version mismatch rejected.
- `test_kernel_sound.py` — at least one valid proof per rule;
  end-to-end derivations (De Morgan, contrapositive, etc.).
- `test_kernel_unsound.py` — at least one invalid proof per common
  failure mode, asserting **the type of error** raised.
- `test_kernel_isolation.py` — walks `src/hlmr/kernel/*.py`, parses
  imports with `ast`, asserts every imported module is either stdlib
  or under `hlmr.ir`.

### 9.2 Coverage targets

- `kernel/`: ≥95%
- `ir/`: ≥85%
- `cli.py`: ≥70% (smoke-tested via `subprocess`, not unit-tested in depth)

### 9.3 Property tests with Hypothesis

- Random formula round-trips through JSON
- `subst` is identity when the substituted variable is not free
- `subst(subst(f, x, y), y, x) == f` when `y` not free in `f`
- `check_proof` is deterministic (same proof, same result)

---

## 10. Definition of done

M0 is done when **all** of these hold:

1. All twelve example proofs in `proofs/m0/` verify with exit code 0.
2. All three `99_BAD_*` proofs are rejected with the documented error
   types (test asserts the error class, not just failure).
3. The full test suite passes. Coverage targets in §9.2 met.
4. `test_kernel_isolation.py` passes — kernel imports nothing outside
   `ir/` and stdlib.
5. `python -m hlmr check <proof.json>` and `python -m hlmr show <proof.json>`
   work end-to-end on Windows.
6. README at repo root explains: how to install, how to run a check,
   how to run the test suite, where the PRDs live.
7. `pyproject.toml` is present with: package name `hlmr`, Python 3.12+,
   stdlib-only runtime deps, `pytest` and `hypothesis` as test extras.
8. `ruff` runs clean on `src/hlmr/`.

---

## 11. Model selection

M0 is implementable entirely in **Sonnet 4.6**. The spec is detailed
enough; Fitch ND is well-trodden; the test suite catches errors.

Opus 4.7 is **not required** for any M0 module. If Sonnet is unable
to implement a section from the spec, the right response is to ask
the user for clarification — not to switch models or guess.

---

## 12. Risks

**Capture-avoiding substitution implemented as plain substitution.**
Manifests as `forallE` deriving nonsense with quantified terms.
Mitigation: dedicated test `test_subst_avoids_capture`.

**Eigenvariable freshness check forgotten or weakened.** Manifests as
the kernel accepting "from `P(a)` derive `forall x. P(x)`" when `a`
appears earlier. Mitigation: dedicated unsoundness tests for each
side condition.

**Box scoping bugs allowing references into discharged boxes.**
Mitigation: explicit `is_accessible` function with its own tests, plus
`test_kernel_unsound.py::test_reference_into_discharged_box`.

**Goal check skipped when `proof.goal` is set.** Mitigation:
`test_goal_mismatch` in the unsoundness suite.

**Kernel imports a non-`ir` module by accident.** Mitigation:
`test_kernel_isolation.py` runs in CI and on every commit.

**JSON schema breakage going forward.** Mitigation: versioned schema;
deserialiser rejects unknown versions explicitly.

---

## 13. Quick reference (Windows / PowerShell)

Initial setup (run once after the source is in place):

```powershell
# Activate the existing venv
.\env_hlmr\Scripts\Activate.ps1

# Confirm Python version
python --version    # expects 3.12+

# Install the package in editable mode with test deps
pip install -e ".[test]"
```

Day-to-day:

```powershell
# Run the test suite
pytest

# Lint
ruff check src/hlmr

# Check a proof
python -m hlmr check proofs\m0\03_de_morgan.json

# Show a proof
python -m hlmr show proofs\m0\03_de_morgan.json

# Regenerate the example proofs
python proofs\m0\generate.py
```

Without venv activation (e.g. across separate Bash tool calls):

```powershell
.\env_hlmr\Scripts\python.exe -m pytest
.\env_hlmr\Scripts\python.exe -m hlmr check proofs\m0\03_de_morgan.json
```

---

## 14. Implementation order (suggested)

A workable build order, smallest-thing-first:

1. `pyproject.toml` and minimal package skeleton (`src/hlmr/__init__.py`
   exports nothing yet).
2. `ir/formula.py` — terms, formulas, `free_vars`, `subst`. Tests for
   substitution before anything else.
3. `ir/justification.py`, `ir/proof.py` — data carriers, no logic.
4. `ir/serialise.py` — JSON round-trip with tests.
5. `kernel/errors.py` — error types.
6. `kernel/scope.py` — `is_accessible`, `is_box`.
7. `kernel/rules.py` — implement rules in groups, with tests:
   propositional first, then FOL, then equality.
8. `kernel/check.py` — top-level driver.
9. `cli.py`, `__main__.py` — CLI and entry point.
10. `proofs/m0/generate.py` — example builder.
11. `test_kernel_isolation.py` — last, as a guardrail.
12. README at repo root.

After each step, run the existing tests. Don't move on until they're
green.
