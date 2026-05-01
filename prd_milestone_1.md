# HLMR Milestone 1 — Manual Solver with Unknowns

**Status:** Draft v1
**Supplements:** `prd.md` (canonical project spec, do not contradict)
**Last updated:** 2026-05-01
**Predecessor milestone:** M0 — see `prd_milestone_0.md`. M1 work
should not begin until M0 is complete and its test suite is green.

---

## 0. Pre-flight check — read this first, every session

**Before writing any code, state which Claude model you are running as.**
This PRD assigns work to specific models. Implementing the wrong section
in the wrong model produces work that has to be redone.

- **Claude Sonnet 4.6** — implements most of this milestone. Default.
- **Claude Opus 4.7** — required for design work on the SLD-to-ND renderer
  and for any decision that changes a module's public interface. See §11
  for the full breakdown.

If you are Sonnet 4.6 and you reach a section marked
`[REQUIRES OPUS 4.7 — DESIGN]`, **stop and ask the user to switch models
for that section**. Do not proceed by guessing the design.

If you are Opus 4.7 working on a `[SONNET 4.6 — IMPLEMENTATION]` section,
that's fine but wasteful — the user can downgrade once the design is
locked.

**Verify M0 is in place before starting M1:**

1. State your model.
2. Confirm `src/hlmr/kernel/` exists and contains `check.py`,
   `rules.py`, `scope.py`, `errors.py`.
3. Run the M0 test suite: `pytest`. All M0 tests must pass.
   If they don't, M1 work is blocked until M0 is fixed.
4. Read this entire document before writing any code.
5. Then propose the implementation order to the user.

**Do-not-invent rule.** Do not claim a command succeeded without
showing its output. Do not claim a test passed without running it.
Do not claim a module exists without listing the directory.

---

## 1. Executive summary

Milestone 1 turns the M0 kernel into a usable manual theorem prover
over a Prolog-style knowledge base, where queries may contain unknowns
and the system finds bindings under user direction.

The differentiating capability: the user states a goal containing
unknowns (e.g. `?- ancestor(?X, alice).`), the system holds open every
applicable clause in the knowledge base, the user picks which clause to
resolve against at each step, the unifier produces bindings, and the
final result is rendered as a Fitch-style natural-deduction proof
which the M0 kernel checks.

What this milestone does not do: arithmetic comparisons, automated
search, neural anything. Those are milestones 2 and 3. The first
demos are kinship relations, simple syllogisms, type-system puzzles,
Zebra-style logic puzzles. **No quadratics, no `<`, no `>`.** Math
problems with arithmetic constraints arrive in milestone 2 with Z3
and SymPy.

---

## 2. How M1 fits

| Milestone | Adds | Demoable on |
|---|---|---|
| **0** | kernel, IR, CLI checker | hand-built proofs verify |
| **1 (this)** | KB, unification, manual SLD, ND renderer, REPL, parser | kinship, Zebra, simple FOL |
| **2** | Z3 + SymPy + dispatcher | linear arithmetic, quadratics |
| **3** | search engine, optional learned suggester | benchmarks (FOLIO, ProofWriter) |

The kernel does not change in M1, with one tiny exception: a
defense-in-depth check at the top of `check_proof` rejects any proof
containing a `Meta` term (§5.3). The IR gains two things (metavariables
and Horn clauses) and the rest is built around it.

---

## 3. Scope

### 3.1 In scope

- First-order Horn clauses as the knowledge base format
- Metavariables (unknowns) of a single untyped category
- First-order Robinson unification with occurs check
- Manual SLD resolution: at each step, the user selects which clause to
  resolve the current goal against
- ND rendering: SLD traces become Fitch proofs the kernel verifies
- Terminal REPL with two interaction shapes per session: build the
  knowledge base, then issue queries
- Lark-based parser for clauses and goals
- JSONL session logging for the future training corpus

### 3.2 Out of scope

- Arithmetic predicates (`<`, `>`, `+`, `*`) — milestone 2
- Z3 or SymPy bridges — milestone 2
- Automated proof search / backtracking without user input — milestone 3
- HTML/JS frontend — deferred (terminal is sufficient for M1)
- Negation-as-failure or any non-Horn extension
- Cut (`!`) or other Prolog control flow
- Higher-order predicates
- Constraint logic programming
- Multi-file knowledge bases (M1 loads one file per session)

### 3.3 Demos that must work by end of M1

The repo includes runnable scripts for each. Failures here are blockers.

1. **Kinship.** KB encodes parent/grandparent/ancestor; query
   `?- ancestor(?X, alice).` returns each ancestor with a kernel-checked
   proof.
2. **Syllogism.** KB encodes "all men are mortal", "Socrates is a man";
   query `?- mortal(socrates).` returns a proof.
3. **Zebra-style finite puzzle.** KB encodes a small constraint puzzle
   (smaller than the canonical Einstein zebra puzzle — pick three or
   four constraints); query asks for the assignment of one variable.
4. **Inductive predicate over Peano naturals.** KB encodes `even(0).`
   and `even(s(s(N))) :- even(N).`; query `?- even(s(s(s(s(0))))).`
   returns a proof. (No real arithmetic — just successor structure.)

Demo 4 is the closest M1 gets to mathematics. It is honest about what
the system can do at this stage.

---

## 4. Architectural commitments (recap)

These are reproduced from `prd.md` because they constrain M1 directly.
Anything contradicting them is wrong by construction.

- **The kernel is the only trusted component.** SLD search, unification,
  and the renderer can all be buggy without compromising soundness, as
  long as the rendered proof is run through the kernel. The kernel
  does not change in M1 except for the `Meta` rejection in §5.3.
- **The IR is the single bus.** Metavariables and the knowledge base
  are added to the IR. Every other module reads and writes IR types.
- **Soundness over completeness.** SLD search may fail to find a proof
  the user expected. It must never produce a wrong one.
- **Logging from day one.** Every REPL command and every solver step
  is logged in JSONL. This is the corpus for milestone 3's optional
  learned suggester.

### 4.1 Non-functional commitments specific to M1

- **Python 3.12+.**
- **PEP 8** throughout. Use `ruff` locally.
- **Type hints required** on every public function and dataclass field.
  Modern syntax (`list[int]`, `X | Y`, no `Optional`/`List`/`Union` from
  `typing`).
- **Modular and shallow.** No deep wrapper hierarchies. If a class is
  one method that delegates to another class, delete the wrapper.
- **One file = one concept.** A module that is over ~400 lines is a
  signal to split it; over ~600 is a hard limit.
- **No surprise dependencies.** New runtime dependencies for M1 are
  exactly two: `lark` (parser) and `prompt_toolkit` (REPL). Anything
  else needs explicit user approval before adding.
- **No kernel changes** other than the §5.3 `Meta` rejection. Any
  proposed change to `src/hlmr/kernel/` requires asking the user
  first.

---

## 5. IR extensions

Two additions only. The rest of `ir/` is unchanged from M0.

### 5.1 Metavariables — `src/hlmr/ir/meta.py`

A new `Term` subclass:

```python
@dataclass(frozen=True)
class Meta(Term):
    """An unknown to be resolved by unification.

    Metavariables exist during search; the kernel never sees them in a
    valid proof. The renderer must apply the final substitution to
    produce a ground proof before kernel checking.
    """
    name: str  # by convention, starts with '?', e.g. '?X'
```

`free_vars_term` and `subst_term` in `formula.py` are extended to handle
`Meta`. `Meta` contributes nothing to free_vars (free vars are about
bound logical variables, not metavariables). Substitution of a logical
variable into a `Meta` is a no-op; substitution of a `Meta` is handled
by the unifier's substitution machinery (§7).

### 5.2 Knowledge base — `src/hlmr/ir/kb.py`

```python
@dataclass(frozen=True)
class Clause:
    """A definite Horn clause: head :- body_1, ..., body_n.

    A fact is a clause with empty body. The head and each body atom
    are positive literals (Atom or Equals). Variables in the clause
    are universally quantified at the clause level (renamed apart at
    each use).
    """
    name: str                          # for user reference, e.g. "ancestor_2"
    head: Atom | Equals
    body: tuple[Atom | Equals, ...]    # empty for facts


@dataclass(frozen=True)
class KnowledgeBase:
    clauses: tuple[Clause, ...]

    def matching(self, goal: Atom | Equals) -> tuple[Clause, ...]:
        """Clauses whose head's predicate symbol matches the goal's.
        Cheap pre-filter; full unification happens later."""
```

### 5.3 Kernel defense-in-depth (the only permitted M1 kernel change)

`check_proof` adds one check at the top: if any line's formula transitively
contains a `Meta` term, reject with a new `UnresolvedMeta` error. This
catches renderer bugs even if a `Meta` slips through. The check is six
lines and does not touch any rule logic.

This is the only kernel change permitted in M1. Anything else proposed
for `src/hlmr/kernel/` requires asking the user first.

A dedicated test (`test_kernel_unresolved_meta`) constructs a hand-built
proof containing a `Meta` and asserts the kernel rejects it with the
new error type.

---

## 6. New modules

```
src/hlmr/
├── ir/
│   ├── meta.py            NEW — Meta term (§5.1)
│   └── kb.py              NEW — Clause, KnowledgeBase (§5.2)
├── kernel/                UNCHANGED except for one Meta check (§5.3)
├── unify/                 NEW — §7
│   ├── __init__.py
│   ├── substitution.py    Substitution dict, apply, compose
│   └── unifier.py         Robinson with occurs check
├── solve/                 NEW — §8
│   ├── __init__.py
│   ├── sld.py             One SLD step: pick clause, unify, rename apart
│   └── render.py          SLD trace → Fitch proof  [REQUIRES OPUS 4.7 — DESIGN]
├── parse/                 NEW — §9
│   ├── __init__.py
│   ├── grammar.lark       Formula + clause grammar
│   └── parser.py          Lark wrapper, returns IR
├── repl/                  NEW — §10
│   ├── __init__.py
│   ├── commands.py        Command parser, command dispatch
│   └── interactive.py     Prompt loop, state management
└── log/                   NEW — §10.4
    ├── __init__.py
    └── recorder.py
```

Module-level model guidance:

| Module | Model | Rationale |
|---|---|---|
| `ir/meta.py`, `ir/kb.py` | **Sonnet 4.6** | Routine dataclasses |
| `unify/` | **Sonnet 4.6** | Robinson is in every textbook; tests catch bugs |
| `solve/sld.py` | **Sonnet 4.6** | Direct mechanical implementation |
| `solve/render.py` | **Opus 4.7 for design**, Sonnet for implementation | The hard one; see §8 |
| `parse/` | **Sonnet 4.6** | Lark grammar; well-trodden |
| `repl/` | **Sonnet 4.6** | UI plumbing |
| `log/` | **Sonnet 4.6** | Trivial |

---

## 7. Unification — `src/hlmr/unify/`

Standard first-order unification, Robinson algorithm, with occurs check.
No higher-order, no constraint extensions.

### 7.1 Substitution — `substitution.py`

```python
Substitution = dict[str, Term]   # meta name -> term

def apply_to_term(s: Substitution, t: Term) -> Term: ...
def apply_to_formula(s: Substitution, f: Formula) -> Formula: ...
def compose(s1: Substitution, s2: Substitution) -> Substitution: ...
```

Substitutions map metavariable names (not logical variable names) to
terms. The naming convention `?X` for metas keeps these visually
distinct from logical vars.

`apply_to_*` recursively replaces `Meta(name)` with `s[name]` wherever
encountered. It does **not** touch `Var` — bound logical variables are
not unification targets.

### 7.2 Unifier — `unifier.py`

```python
def unify(t1: Term, t2: Term,
          s: Substitution | None = None) -> Substitution | None:
    """Robinson unification. Returns extended substitution, or None
    if not unifiable. Performs occurs check."""

def unify_atoms(a1: Atom | Equals, a2: Atom | Equals,
                s: Substitution | None = None) -> Substitution | None:
    """Unify atoms (same predicate, same arity, args pairwise unify)."""
```

The occurs check is mandatory, not optional. Unification of `?X` with
`f(?X)` must fail. This is a soundness requirement — without it the
unifier produces infinite terms and the renderer goes into a loop.

### 7.3 Tests required

- Unify ground terms equal → empty substitution
- Unify ground terms unequal → None
- Unify `?X` with `t` → `{?X: t}`
- Unify `?X` with `?X` → empty
- Unify `?X` with `f(?X)` → None (occurs check)
- Unify `f(?X, a)` with `f(b, ?Y)` → `{?X: b, ?Y: a}`
- Hypothesis property: `apply(unify(s, t), s) == apply(unify(s, t), t)`
  whenever unification succeeds

---

## 8. Solver — `src/hlmr/solve/`

### 8.1 SLD step — `sld.py` `[SONNET 4.6 — IMPLEMENTATION]`

```python
@dataclass(frozen=True)
class SLDState:
    """A point in SLD resolution: outstanding goals + accumulated subst."""
    goals: tuple[Atom | Equals, ...]
    subst: Substitution
    history: tuple[SLDStep, ...]   # for rendering


@dataclass(frozen=True)
class SLDStep:
    """One resolution step taken."""
    goal_resolved: Atom | Equals       # the goal we attacked
    clause_used: Clause
    clause_renamed: Clause             # variables renamed apart
    unifier: Substitution              # mgu of goal and renamed head


def candidates(state: SLDState, kb: KnowledgeBase) -> list[Clause]:
    """Clauses whose head can unify with the first goal of state."""

def resolve(state: SLDState, clause: Clause) -> SLDState | None:
    """Apply one SLD step using the chosen clause. None if no unification."""
```

SLD is left-to-right on goals (standard Prolog convention). Variable
renaming-apart at each clause use is essential — `member(X, [X|_])`
called twice must use different `X`s.

### 8.2 Rendering — `render.py` `[REQUIRES OPUS 4.7 — DESIGN]`

This is the gnarly module. Read this entire section before starting.

**The contract.** Given a successful `SLDState` (empty goals), the KB,
and the original query: produce a `Proof` (defined in `ir/proof.py`)
that:

1. Has each clause used as a premise, in ND form. A Horn clause
   `h(X) :- b1(X), b2(X)` becomes `∀X. (b1(X) ∧ b2(X)) → h(X)`. A fact
   `h(a)` is just `h(a)` as a premise.
2. Reproduces each SLD step using `forallE`, `andE_L`/`andE_R` (to split
   the body), and `impE`. The order matches a depth-first walk of the
   SLD tree.
3. Concludes with the instantiated query goal as the final line.
4. Contains no `Meta` terms (the final substitution has been fully
   applied).

**Why this needs Opus design.** The straight-line case (one clause,
one step) is mechanical. The complications:

- A clause body has multiple goals; each one becomes its own subproof
  before we can `impE` to derive the head. The proof's box structure
  needs to interleave these correctly.
- Renaming-apart introduces eigenvariables that need to be tracked so
  later `forallI` (if any) is sound. M1 doesn't introduce `forallI`
  — every quantifier is eliminated by `forallE` at some point — but
  the renamings still need bookkeeping.
- The user's chosen order may produce a proof that *checks* but reads
  poorly (e.g. introduces premises far from where they're used). The
  design needs to decide whether to optimise for readability or accept
  the kernel-correct but verbose form.

**Recommended Opus task before any code:** produce a worked example.
Take demo 2 (the syllogism), trace SLD by hand, write out the resulting
Fitch proof line by line on paper, then derive the rendering algorithm
from that example. Once the algorithm is on paper and we agree it's
correct, Sonnet implements it.

**The Opus deliverable** is `src/hlmr/solve/RENDER_DESIGN.md`
containing:

- A worked example for each demo (1 through 4 in §3.3), traced by hand
- The general algorithm derived from the examples
- A list of edge cases (empty body, multiple bodies, repeated vars,
  recursive clauses) and how the algorithm handles each
- The output type signature and module API

**Test strategy for the renderer.** Every demo proof, plus property
tests: take a small KB and a successful SLD trace, render, check with
the kernel — if the kernel rejects, the renderer is wrong. Hypothesis
can generate small KBs and goals for fuzz testing.

### 8.3 Public API

```python
def manual_solve(kb: KnowledgeBase, goal: Atom | Equals,
                 picker: Callable[[list[Clause], SLDState], int]
                 ) -> tuple[Substitution, Proof] | None:
    """Run manual SLD with a callback for clause selection. Returns the
    binding for any metas in the goal, plus a kernel-checked proof,
    or None if the user gives up or no clauses match."""
```

The picker is the REPL callback. Decoupling solve from REPL means
solve is unit-testable with a programmatic picker.

---

## 9. Parser — `src/hlmr/parse/` `[SONNET 4.6 — IMPLEMENTATION]`

### 9.1 Surface syntax

A small Prolog-flavoured syntax. ASCII only for M1; Unicode is M2+.

```
% comments start with %

% Facts
human(socrates).
parent(alice, bob).

% Rules
mortal(X) :- human(X).
ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).

% Queries (in REPL)
?- mortal(socrates).
?- ancestor(?X, alice).
```

Naming conventions, enforced by the parser:

- `lowercase_with_underscores` and digits → predicate names, function
  names, and constants (Prolog-style atoms — but to avoid the term
  collision with our IR's `Atom`, refer to them as **constants** in
  prose).
- `Uppercase` or `_underscore_lead` → logical variables (universally
  quantified at clause level)
- `?Uppercase` → metavariables (only valid in queries, not in clauses)

### 9.2 Output

The parser emits IR objects directly: `Clause` for clauses, `Atom`/`Equals`
for goals. No intermediate AST.

### 9.3 Errors

Parse errors include line and column from Lark. They are user-facing,
not stack traces.

### 9.4 Tests

- Round-trip: every fixture clause parses → round-trip via repr → reparses
  to equal IR
- Hypothesis-generated random clauses (constrained to valid syntax)

---

## 10. REPL — `src/hlmr/repl/` `[SONNET 4.6 — IMPLEMENTATION]`

### 10.1 Interaction model

Two phases per session:

1. **KB phase.** The user types clauses (or `:load file.pl`). Each
   clause is parsed and added to the KB. Errors don't exit; the user
   retries.
2. **Query phase.** The user issues `?- goal.` queries. For each query,
   the system enters manual SLD: shows the current goal, lists
   candidate clauses with numbers, asks the user to pick.

Phase transitions are explicit (`:query` and `:edit`). The user can
return from query phase to KB phase to add more clauses.

### 10.2 Commands

```
:help                       list commands
:load <path>                load a clause file into KB
:save <path>                save current KB to file
:show kb                    pretty-print the KB
:show last                  pretty-print the last successful proof
:export <path>              save last proof to JSON
:quit                       exit

% In KB phase, any line ending in `.` is a clause to add.

% In query phase:
?- goal.                    start a new query
pick <n>                    select candidate clause n
candidates                  re-show candidates
back                        undo last pick
abort                       give up on current query
```

`prompt_toolkit` provides command history, multi-line editing, and
syntax-aware completion.

### 10.3 Output during a query

```
?- ancestor(?X, alice).

Goal 1/1: ancestor(?X, alice)

Candidate clauses:
  1. ancestor(X, Y) :- parent(X, Y).             (rule, ancestor_1)
  2. ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).  (rule, ancestor_2)

> pick 1

Substitution: { ?X -> X_1, alice -> Y_1 }
... (continues)

Solved with: ?X = bob
Proof: 7 lines, kernel-verified.
Type `:show last` to display, `:export proof.json` to save.
```

### 10.4 Logging — `src/hlmr/log/recorder.py`

Every event in the session goes to `corpus/<session-id>.jsonl`:

- `kb_add`: clause added, with parsed form
- `query_start`: query, parsed form
- `pick`: SLD step taken, with state before and after
- `query_end`: result (success/abort), final substitution if any, proof
  hash if successful

The schema is versioned (`"hlmr_log_version": 1`) and lives in
`src/hlmr/log/schema.md`. Logs are gitignored. The session id is a
timestamp + random suffix, so concurrent sessions don't collide.

This is the future training corpus. It is much cheaper to add now than
to retrofit later.

---

## 11. Model selection guide — read before each session

Claude Code receives a model identifier at startup. Before any
implementation work, **state which model you are** and check this
table.

### 11.1 Sonnet 4.6 — default for implementation

Sonnet handles all of:
- IR additions (`meta.py`, `kb.py`)
- Unification module (`unify/`)
- SLD step (`solve/sld.py`)
- Renderer **implementation** once Opus has produced the design doc
- Parser (`parse/`)
- REPL (`repl/`)
- Logging (`log/`)
- All test suites
- All demo scripts
- Documentation and READMEs

If working on any of the above and the spec is clear, proceed in Sonnet.

### 11.2 Opus 4.7 — required for these specific tasks

**Task A: SLD-to-ND renderer design.** Before any code in
`solve/render.py`, Opus produces a design document
(`solve/RENDER_DESIGN.md`) containing:
- A worked example for each demo (1 through 4 in §3.3), traced by hand
- The general algorithm derived from the examples
- A list of edge cases (empty body, multiple bodies, repeated vars,
  recursive clauses) and how the algorithm handles each
- The output type signature and module API

Sonnet then implements against the design.

**Task B: Any new module boundary.** If during implementation a new
module turns out to be needed (something not in §6), Opus decides
whether it belongs and where. This is a one-prompt sanity check, not a
full session.

**Task C: Any IR change beyond §5.** The IR is the bus between modules;
breaking it requires care. If anything beyond `Meta` and `KB` needs
adding, escalate to Opus.

### 11.3 What to do at a model boundary

If you are Sonnet and you hit `[REQUIRES OPUS 4.7 — DESIGN]`:

> "This section is marked as requiring Opus 4.7 for design. I am
> Sonnet 4.6. Please switch models for this section, or override this
> requirement explicitly in your next message."

Then stop. Do not proceed by guessing.

If you are Opus and you finish a design task, hand off:

> "Design complete in `<path>`. Implementation can proceed in Sonnet 4.6."

---

## 12. Definition of done

M1 is done when **all** of these hold:

1. All four demos in §3.3 run end-to-end. Each produces a kernel-verified
   proof. The proofs are saved as JSON in `proofs/m1/`.
2. The full test suite passes: M0 tests still green, plus new tests
   for `unify/`, `solve/`, `parse/`, `repl/`, `log/`. Coverage targets:
   ≥95% on `unify/` and `solve/sld.py`, ≥85% on the renderer, ≥70% on
   `parse/` and `repl/`.
3. The kernel still has zero imports outside `ir/` and stdlib.
   `test_kernel_isolation.py` still passes.
4. `python -m hlmr repl` opens an interactive session that can build a
   KB, accept queries, and produce verified proofs.
5. Every REPL session logs to JSONL with the schema in §10.4.
6. README in the repo root reflects M1: install, run demos, run REPL,
   pointer to PRD.
7. The `99_BAD_*` demonstration proofs from M0 still fail with the
   same errors. The kernel's defense-in-depth `Meta` check has its own
   test (a hand-built proof containing a Meta is rejected).

---

## 13. Risks

**Renderer bugs that produce kernel-passing but logically wrong proofs.**
Mitigation: the kernel only checks individual rule applications, not
the overall theorem. So a renderer could prove the wrong thing, in
principle. Dedicated tests assert that for each demo, the *final line*
of the rendered proof matches the *instantiated query*. This is the
cheap end-to-end soundness check.

**Variable capture during clause renaming.** A clause variable
accidentally clashes with a meta or another clause variable. Mitigation:
fresh-name generator with a session-wide counter; every renaming-apart
goes through it. Dedicated tests with adversarial variable names.

**Occurs-check forgotten or short-circuited.** Soundness loss. Mitigation:
unit test `unify(?X, f(?X))` returns None. Property test with random
nested terms.

**REPL state corruption.** User picks a clause that doesn't apply and
the SLD state goes into an invalid state. Mitigation: `resolve` is a
pure function returning `SLDState | None`; the REPL only commits the
new state on success.

**Logger turned off accidentally and corpus is lost.** Mitigation:
logging defaults to on; the `--no-log` flag exists but isn't the
default; the log path is announced when the REPL starts.

**Model misuse — Sonnet implements the renderer without Opus design.**
Result: probably works for demo 2 (the easy one) and quietly breaks on
demo 3. Mitigation: §0 and §11 are at the top of this PRD specifically
to make this hard to do accidentally.

---

## 14. Out of scope, for the avoidance of doubt

- Numeric `<`, `>`, `+`, `*`, `=:=` and friends. (M2.)
- Z3, SymPy, any SMT solver. (M2.)
- Negation, cut, `findall`, `assert`/`retract`. (Not planned.)
- Automated search without a human picking clauses. (M3.)
- Backtracking through the user's previous picks via the engine. The
  user can `back`; the engine doesn't enumerate alternatives on its
  own. (M3.)
- Static HTML/JS frontend. (Deferred indefinitely; terminal is fine.)
- Proof export formats other than JSON and the existing `:show` text
  rendering.
- Any neural component, training, or model-serving infrastructure.

---

## 15. Quick reference — what the user actually does (Windows / PowerShell)

```powershell
# Activate venv (already created)
.\env_hlmr\Scripts\Activate.ps1

# Install (M0 already in place; M1 adds two deps)
pip install -e ".[test]"

# Run a demo
python -m hlmr demo syllogism

# Open the REPL
python -m hlmr repl

# In the REPL:
> :load examples/kinship.pl
Loaded 5 clauses.
> :query
> ?- ancestor(?X, alice).
[manual solve session]
Solved: ?X = bob.
> :export proof.json
Wrote proof.json (12 lines, kernel-verified).
> :quit
```

That is the full M1 user experience. Nothing more, nothing less.
