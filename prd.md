# HLMR — Hybrid Logic-Math Reasoner

**Status:** Canonical project spec, v3
**Last updated:** 2026-05-04
**Per-milestone specs:** `prd_milestone_0.md`, `prd_milestone_1.md`, `prd_milestone_2.md`, future `prd_milestone_3.md`.

---

## 1. Executive summary

HLMR is a Python 3.12 theorem prover that finds proofs of logical and
mathematical goals over a user-supplied knowledge base. Goals may
contain unknowns. The system finds bindings via goal-directed search
(Prolog-style SLD resolution, optionally augmented with SMT and symbolic
algebra), renders the result as a Fitch-style natural-deduction proof,
and checks every proof through a small trusted kernel before reporting
success.

The system has two interaction modes against the same engine: a manual
mode where the user drives clause selection, and an automated mode where
the system searches. The kernel is invariant across modes and across
all milestones.

The first demos are kinship and Zebra-style logic puzzles. Math arrives
in milestone 2 with Z3 (linear arithmetic) and SymPy (symbolic algebra).
The end goal is a usable, sound, extensible reasoner with a growing
knowledge base of axiomatic content — not a frontier-grade general
mathematician.

---

## 2. Problem statement

The existing landscape is split unhelpfully:

- **Pure logic tools** (Pandora, Carnap, Logitext) handle natural
  deduction but no arithmetic and no goal-directed search.
- **Pure math tools** (SymPy, Mathematica, Wolfram Alpha) handle
  numbers but produce no inference trace.
- **Logic programming** (Prolog, λProlog) does goal-directed search
  but doesn't render proofs in a form a student or reviewer can audit
  step by step.
- **Frontier LLMs** do everything plausibly and nothing checkably.
  Soundness is not a property they have.

HLMR fills a specific gap: a single engine where (a) the user can write
domain knowledge as Horn clauses, (b) goals can contain unknowns, (c)
proofs are produced in a presentation-friendly ND format, and (d) every
proof is mechanically checked by a kernel that's small enough to audit.

The motivating example, demonstrable by milestone 2:

```
KB:
  prime(2). prime(3). prime(5). prime(7).

Query:
  ?- prime(?P), greater_than(?P, 2), less_than(?P, 6), not_equal(?P, 4).

Answer:
  ?P = 5.
  Proof: kernel-verified, with arithmetic-witness lines (one per
  inequality) and natural-deduction lines for the prime/1 lookup.
```

The KB contains the `prime/1` facts; the inequality predicates
(`greater_than`, `less_than`, `not_equal`) are not user-supplied
clauses but arithmetic constraints that the dispatcher routes to Z3.
The dispatcher is part of milestone 2.

Pure logic tools can't reason about the inequalities. Pure SMT tools
produce no proof. LLMs produce something that looks like a proof and
isn't checked. HLMR returns a witness *and* a kernel-checked
derivation.

---

## 3. What this is, and what it is not

This section exists because the project's framing has drifted toward
larger ambitions in conversation. Anchor here.

### 3.1 What this is

- A theorem prover for a **decidable, explicitly-bounded fragment** of
  first-order logic with equality, plus linear arithmetic and finite
  domains in milestone 2.
- A tool whose **knowledge base is hand-curated**. Adding new domain
  axioms is part of using the system. Domain libraries grow over time.
- A pedagogical tool. The first users are people learning logic,
  proof techniques, or constraint reasoning. Education is the primary
  market; research-grade automation is downstream.
- A system designed for **soundness**. False negatives (failing to find
  a proof that exists) are acceptable. False positives (claiming a
  proof when one is invalid) are catastrophic and the architecture
  exists to prevent them.

### 3.2 What this is not

- **Not an LLM**, and not trying to be one. There is no transformer.
  There is no training corpus in the foundation-model sense. There may,
  much later, be a small specialised model that re-ranks candidate
  clauses during automated search — but only if it earns its place
  empirically, and the system must work fully without it.
- **Not a complete formalisation of mathematics.** Gödel's incompleteness
  theorems guarantee no such system exists for any consistent theory
  strong enough to express arithmetic. The system proves theorems
  *within* whatever knowledge base has been encoded. It does not
  enumerate truth.
- **Not a Lean or Coq replacement.** Mathlib has spent a decade
  formalising mathematics; HLMR will not catch up. The scope is
  intentionally narrower.
- **Not a frontier benchmark contender.** MATH and GSM8K are explicitly
  not target benchmarks; they are dominated by LLMs and are the wrong
  shape for this system. Target benchmarks are listed in §10.
- **Not a natural-language system.** The user types Prolog-flavoured
  syntax. NL parsing is, at best, a milestone 4+ extension.

If a feature request can only be justified by appeal to one of the
above framings, push back.

---

## 4. Architectural commitments

These are non-negotiable. Every milestone's design must respect them.

**The kernel is the only trusted component.** Search engines, unifiers,
SMT bridges, parsers, REPL UIs, future learned rankers — all of these
can have bugs without compromising soundness, *as long as every claimed
proof is run through the kernel*. The kernel is small enough to read
in a sitting and is exhaustively tested. It does not change casually.

**The IR is the single bus.** Every component reads and writes the same
formula and proof types. No component has its own private representation.
Every proof is JSON-serialisable.

**Construction and verification are separated.** Different milestones
vary *how* proofs are constructed (manual, SLD, automated search).
They do not vary *how proofs are checked*. The kernel is invariant.

**The supported fragment is explicit and decidable.** First-order logic
with equality, linear arithmetic over ℤ and ℚ, finite-domain constraints,
and symbolic algebraic equations dispatched to SymPy. Problems outside
this fragment are rejected with a clear message, never attempted
silently.

**Solver dispatch is explicit, not heuristic.** When an unknown needs
to be resolved, the dispatcher chooses among unification, Z3, and SymPy
by classification rule. The choice is logged. Disagreements between
solvers are bugs; the kernel arbitrates.

**Soundness over completeness.** Every reported "solved" result has a
kernel-verified proof. No exceptions.

**Logging from day one.** Every user step (manual mode) and every solver
step (automated mode) is logged with full state. This is the corpus
that may later inform learned components. Cheap to add now, expensive
to add later.

---

## 5. Repository structure

```
hlmr/
├── pyproject.toml
├── README.md
├── prd.md                         (this document — canonical)
├── prd_milestone_0.md             (M0 implementation spec — shipped)
├── prd_milestone_1.md             (M1 implementation spec — shipped)
├── prd_milestone_2.md             (M2 implementation spec)
├── prd_milestone_3.md             (M3 implementation spec — to write)
├── src/hlmr/
│   ├── ir/                        IR: formula, proof, justification, KB, meta
│   ├── kernel/                    Trusted core (M0)
│   ├── unify/                     M1
│   ├── solve/                     M1 (manual SLD), M3 (auto search)
│   ├── solvers/                   M2 (Z3, SymPy bridges)
│   ├── dispatch/                  M2 (constraint classification, routing)
│   ├── parse/                     M1 (Lark grammar, parser)
│   ├── repl/                      M1
│   ├── log/                       M1
│   ├── tactics/                   M3
│   └── cli.py
├── tests/                         (mirrors src/ structure)
├── proofs/                        Example proofs by milestone
├── examples/                      Example knowledge bases
├── benchmarks/                    Imported benchmark sets (M3)
└── corpus/                        Logged sessions (gitignored)
```

Hard structural rules:

- **`kernel/` imports only from `ir/` and stdlib.** Test-enforced from
  M0 (a dedicated `test_kernel_isolation.py` walks `kernel/*.py` and
  asserts no other imports).
- **No module replicates rule logic.** The kernel is the only place ND
  rule semantics are implemented.
- **`solvers/` is the only place Z3 and SymPy are imported.** Other
  modules go through its interface.

---

## 6. Scope (across all V1 milestones)

### 6.1 In scope for V1

- Propositional logic with all standard connectives (∧, ∨, ¬, →, ↔, ⊥)
- First-order logic with quantifiers (∀, ∃) over a single sort
- Equality reasoning (reflexivity, substitution)
- Linear arithmetic over ℤ and ℚ (M2)
- Finite-domain constraints (M2)
- Symbolic algebraic equations dispatched to SymPy (M2)
- Unknowns (metavariables), resolved by unification, Z3, or SymPy
- Fitch-style natural deduction with explicit assumption boxes
- Horn-clause knowledge bases
- Manual mode (user picks clauses) and automated mode (system searches)
- Terminal CLI/REPL

### 6.2 Out of scope for V1

- Non-linear real arithmetic (beyond what SymPy handles for specific
  algebraic equations)
- Calculus (limits, derivatives, integrals)
- Higher-order logic, dependent types
- Set theory beyond finite sets
- Induction over arbitrary inductive types (induction over ℕ may be
  added in M3 if it falls out of the search engine cheaply)
- Geometry, probability theory
- Multi-sort first-order logic (single sort suffices for M1–M3)
- Negation-as-failure or other non-classical extensions to Horn clauses
- Multi-user accounts, web hosting, persistent server infrastructure
- Static HTML/JS frontend (deferred indefinitely; terminal is sufficient)
- Training a foundation-scale neural model
- Natural-language input parsing

### 6.3 What this means for the user

A user can:

- Write Prolog-flavoured Horn clauses and queries
- Drive proofs manually, picking clauses to resolve goals against
- (M2 onward) Mix logic with linear arithmetic and finite domains
- (M3 onward) Ask the system to search for proofs automatically
- Export every proof as JSON and replay it through the kernel

A user cannot:

- Type natural-language problems
- Get reasoning over non-linear or transcendental functions (beyond
  what SymPy does for specific cases the dispatcher routes)
- Get fast answers on problems outside the supported fragment — the
  system will reject them rather than guess

---

## 7. Milestones

### 7.1 Milestone overview

| Milestone | Status | Adds | Demo |
|---|---|---|---|
| **0** | **Shipped** (`prd_milestone_0.md`) | Kernel + IR + CLI proof checker | Hand-built proofs verify |
| **1** | **Shipped** (`prd_milestone_1.md`) | Horn-clause KB, unification, manual SLD, ND renderer, REPL, parser, logging | Kinship, Zebra, simple FOL |
| **2** | Spec written (`prd_milestone_2.md`) | Z3 + SymPy bridges, dispatcher, `arithEval` kernel rule | Linear arithmetic, quadratics |
| **3** | Spec to write | Automated search, optional learned ranker | FOLIO, ProofWriter, LogiQA |
| **4+** | Optional | Domain libraries (intro logic, basic number theory, etc.) | Domain-specific demos |

Each milestone is shippable on its own. Each strictly extends its
predecessor. The kernel changes exactly twice between M0 and M3
(in M1, the `Meta` rejection check; in M2, the `arithEval` ground
arithmetic rule).

### 7.2 Milestone 0 — kernel and IR

See `prd_milestone_0.md` for the full spec. Summary:

- 22 ND rules: `andI`, `andE_L`, `andE_R`, `orI_L`, `orI_R`, `orE`,
  `impI`, `impE`, `notI`, `notE`, `botE`, `iffI`, `iffE_L`, `iffE_R`,
  `reit`, `PBC`, `forallI`, `forallE`, `existsI`, `existsE`,
  `eqRefl`, `eqSubst`
- IR: frozen-dataclass terms and formulas, capture-avoiding substitution,
  Fitch-style proofs with box depth tracking, JSON serialisation with
  versioned schema
- Eigenvariable side conditions on `forallI` and `existsE`
- Box scoping with accessibility and discharge checks
- CLI: `python -m hlmr check <proof.json>` and `... show <proof.json>`
- Soundness regression suite; unsoundness regression suite; property
  tests for substitution and JSON round-trips
- `kernel/` imports only from `ir/` and stdlib (test-enforced from
  day one)

### 7.3 Milestone 1 — manual solver with unknowns

See `prd_milestone_1.md` for the full spec. Summary:

- IR additions: `Meta` term type, `Clause`, `KnowledgeBase`
- Modules: `unify/`, `solve/sld.py`, `solve/render.py`, `parse/`,
  `repl/`, `log/`
- Manual mode: user states a goal containing unknowns, system shows
  candidate clauses at each step, user picks
- Output: kernel-verified ND proof + final substitution
- Demos: kinship, syllogism, small Zebra puzzle, even-via-Peano
- One kernel change permitted: top-of-`check_proof` rejection of any
  formula containing a `Meta`

No arithmetic. No automated search.

### 7.4 Milestone 2 — arithmetic and dispatch

See `prd_milestone_2.md` for the full spec. Summary:

- Add Z3 and SymPy bridges in `solvers/`
- Add a dispatcher in `dispatch/` that classifies constraints and
  routes them: unification for first-order, Z3 for linear arithmetic
  and finite domains, SymPy for symbolic algebraic equations
- Add metavariable types: `Categorical`, `Integer`, `Rational`,
  `FiniteDomain(values)` — replacing M1's single untyped category
- Add one new kernel rule, `arithEval`, that verifies ground
  arithmetic atoms (e.g. `5 > 2`, `3 + 4 = 7`) by evaluation. This
  is the only kernel change in M2.
- Outcome classification: `UniqueSolution`, `MultipleSolutions`,
  `InfinitelyManySolutions`, `NoSolution`, `Underdetermined`,
  `OutsideFragment`
- Demos: the §2 motivating example; `x² - 5x + 6 = 0` returns
  `{2, 3}` with kernel-checked verification (witness checking, not
  exhaustiveness — see §11)

The dispatcher is the high-risk module of M2 and warrants Opus
design. The `arithEval` rule crosses the kernel trust boundary and
also requires Opus design before implementation.

### 7.5 Milestone 3 — automated search

Tactic engine, not classical proof search. Hand-written tactics propose
sequences of rule applications and clause selections. Search is
iterative deepening over a tactic priority list, with a per-attempt
time budget. The kernel checks every state.

Optional: a small learned ranker for tactic priority, trained on the
corpus collected from M1 and M2. Gated on having ≥5,000 logged proof
steps. The system must work fully without it.

Benchmark target thresholds:

- Propositional intro-logic: ≥80%
- Curated FOL subset: ≥50%
- Zebra-style finite-domain: ≥70% within 30s each
- Hybrid logic-plus-linear-arithmetic: ≥60%

Every reported success has a kernel-verified proof.

### 7.6 Milestone 4+ (optional, deferred)

Domain libraries. Hand-encoded knowledge bases for intro logic, basic
number theory (over what M2 supports), finite group theory, simple
combinatorics. Each library is a directory of `.pl`-style clause
files and a curated set of demo queries. This is the part that takes
years and where Mathlib-style projects live; explicit scoping prevents
the project from collapsing into one of those.

---

## 8. Cross-cutting concerns

### 8.1 Non-functional commitments

- **Python 3.12+** throughout
- **PEP 8**, enforced via `ruff` (locally; CI deferred until needed)
- **Type hints** on every public function and dataclass field; modern
  syntax (`list[int]`, `X | Y`); no `Optional`/`List`/`Union` from
  `typing`
- **Modular and shallow.** Wrapper classes that delegate one method to
  another are forbidden. Modules over ~600 lines are split.
- **Runtime dependencies are listed and minimal.** M0: stdlib only
  for `kernel/` and `ir/`; `pytest` and `hypothesis` test-only.
  M1 adds: `lark`, `prompt_toolkit`. M2 adds: `z3-solver`, `sympy`.
  M3 may add `torch` if and only if the learned ranker is built.
  Anything else needs explicit approval.

### 8.2 Testing

- `pytest` for unit and integration
- `hypothesis` for property tests (round-trips, kernel determinism,
  unifier soundness)
- Coverage targets: ≥95% on `kernel/`, `unify/`, `solve/sld.py`;
  ≥85% on renderers and dispatcher; ≥70% on parsers and REPL
- The soundness regression suite is run before every commit (locally
  for now; CI later). An unsoundness regression is a merge-blocker.

### 8.3 Logging

Every interactive session and every benchmark run produces JSONL.
Schema is versioned and lives in `src/hlmr/log/schema.md`. Logs are
gitignored. A documented `hlmr export-corpus` command bundles them
for analysis or training.

### 8.4 Documentation

- Each module has a short README explaining its contract
- The kernel's contract is documented to a higher standard than other
  modules — it is the trust boundary
- A user-facing `docs/tutorial.md` walks through the REPL with worked
  examples by end of M1

### 8.5 Performance

Not an M0/M1/M2 concern. M3 introduces time budgets per tactic and
per overall proof attempt. No optimisation work before M3 unless
something is unusably slow.

### 8.6 Frontend

Terminal only for V1. If a UI becomes desirable, the chosen approach
is a static HTML+JS page that calls a small local Python server
exposing the kernel and dispatcher over JSON. Not part of any
milestone's definition of done.

---

## 9. Model selection (high level)

Per-milestone PRDs contain detailed model-selection guidance with
explicit gates. This section is the strategic summary.

**Default: Claude Sonnet 4.6.** Routine implementation, tests,
documentation, day-to-day coding inside an established module.

**Required: Claude Opus 4.7** for these specific kinds of task:

- **Module-boundary design.** Anything that introduces a new module
  or changes a module's public interface.
- **Renderer and translator design.** SLD-to-ND rendering (M1), proof
  reconstruction from SMT models (M2). These are bridges between
  representations and the corner cases hide soundness bugs.
- **Dispatcher design.** Constraint classification logic in M2.
  Getting it wrong manifests as silent unsoundness.
- **Search strategy design.** M3's tactic priorities and search
  invariants.
- **Knowledge-base axiomatisation.** When encoding domain content
  (M4+), the choice of axiomatisation matters and is research-flavoured.

**The pre-flight rule.** Every Claude Code session begins by stating
its model. If a session reaches a section gated on Opus while running
Sonnet, it stops and asks for a model switch rather than proceeding by
guessing.

The worst-case downside of using Sonnet for a task that wanted Opus is
not unsoundness — the kernel still catches that — but a design that
works for the obvious cases and breaks on the corner cases. Recoverable
but expensive.

M0 in particular is pure Sonnet territory. Fitch-style ND is in every
undergraduate textbook; the spec in `prd_milestone_0.md` is detailed
enough that Sonnet implements directly without design assistance.

---

## 10. Target benchmarks

Listed in increasing difficulty. M3 success is measured against these.

- **FOLIO** — first-order logic NL problems. Adapted to HLMR's
  Prolog-style input.
- **ProofWriter** — multi-step rule reasoning.
- **LogiQA** — logical-reasoning multiple choice.
- **Zebra-style puzzles** — finite-domain constraint satisfaction.
- **Custom hybrid suite** — problems combining FOL inference with
  linear arithmetic and unknowns. Constructed in-house, ~50 problems
  by end of M2.

Pure-arithmetic benchmarks (MATH, GSM8K) are explicitly excluded.
They are LLM-dominated and the wrong shape for this system.

---

## 11. Risks

**Kernel soundness bug.** Mitigation: unsoundness regression suite,
tiny kernel surface, no kernel changes without code review.

**Renderer produces kernel-passing but logically wrong proofs.** The
kernel checks individual rule applications but not theorem identity.
Mitigation: per-demo end-to-end tests assert the final line of the
rendered proof matches the instantiated query. The Opus design step
for the renderer (M1) is the upstream defence.

**Solver disagreement with the kernel** (Z3 says SAT but the
instantiated proof fails to check). Mitigation: kernel is arbiter;
disagreements crash during development, not in production. Bridge
round-trip property tests.

**Dispatcher misclassifies constraints**, sending a non-linear problem
to Z3 and getting a confident wrong answer. Mitigation: classification
is conservative — anything ambiguous is rejected as `OutsideFragment`
rather than guessed. Property tests cover the boundary cases.

**Scope creep into non-linear arithmetic, set theory, calculus.**
Mitigation: the `OutsideFragment` outcome is first-class. The dispatcher
actively rejects.

**SymPy "solved" but exhaustiveness unproven.** Mitigation: the system
distinguishes "found these witnesses, kernel-verified each one" from
"proved these are the only witnesses." The latter requires axioms in
the KB and goes through the proof system; the former is an honest
weaker claim. Documentation makes this distinction explicit.

**Corpus collection forgotten until too late.** Mitigation: logging is
in M1's definition of done, not retrofitted later.

**Domain libraries devour the project's time.** Mitigation: M4+ is
optional and deferred. M1–M3 are the V1 deliverable. Expanding the
domain library is a separate project that uses the V1 system.

**Model misuse during implementation.** Sonnet implements a section
that wanted Opus design and silently produces a flawed module.
Mitigation: per-milestone PRDs put model gates at the top, with
explicit "stop and ask" instructions.

---

## 12. Decisions deferred

These need answers before the milestone that uses them, but not now.

| Decision | Latest deadline |
|---|---|
| Typed vs untyped first-order terms | Before M2 |
| λProlog-style higher-order patterns vs first-order unification only | Before M2 |
| Whether the dispatcher should be a single classifier or a chain of specialists | Before M2 |
| How to render M2's SymPy-derived witnesses as ND lines | Before M2 |
| Tactic interface: protocol, ABC, or plain function | Before M3 |
| Whether to support induction over ℕ in M3 | During M3 |
| Whether the corpus is large enough to warrant the learned ranker | Late M3 |
| Domain library structure and curation policy | Before M4 |
| Whether to add a CI provider (GitHub Actions, etc.) | Before merging M1 |

---

## 13. Document conventions

- `prd.md` (this document) is canonical at the strategic level. It
  changes infrequently and only with deliberate review.
- `prd_milestone_<n>.md` is the implementation spec for milestone *n*.
  It is written near the start of work on that milestone and is the
  document Claude Code should read before implementing.
- Per-milestone PRDs may not contradict this document. If a per-milestone
  PRD wants to change something at the strategic level, this document
  is updated first.
- Both kinds of document include explicit model-selection guidance.

---

## 14. Provenance and credit

The project's intellectual roots are in Pandora-style natural deduction
tools (Imperial College) and λProlog-style proof-as-search systems.
The differentiating contribution is the integration: Prolog-style
goal-directed search over a user-curated knowledge base, presenting its
output as Fitch ND, with a small kernel as the only trusted component,
and an explicit fragment boundary that includes linear arithmetic via
SMT and symbolic algebra via SymPy.

The framing has explicitly been kept narrow. The project is not a
general mathematician, not an LLM, not a complete formalisation system.
It is a focused, sound, extensible reasoner.
