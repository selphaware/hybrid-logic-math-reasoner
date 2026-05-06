# HLMR — Hybrid Logic-Math Reasoner

**Status:** Canonical project spec, v4
**Last updated:** 2026-05-06
**Per-milestone specs:** `prd_milestone_0.md`, `prd_milestone_1.md`, `prd_milestone_2.md`, future `prd_milestone_3.md` and beyond.
**Strategic direction:** `docs/strategic_direction.md` (theory-growth long-term vision; informs M3 onwards).

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

The longer-term direction, beginning at M3, is a **proof-checked theory
growth engine**: starting from a small axiom seed, the system generates
typed candidate conjectures, filters and counterexample-tests them,
attempts proof using the M0–M2 machinery, and admits only kernel-checked
results back into a growing reusable theorem library. Search may be
creative; verification remains strict. The full vision is described in
`docs/strategic_direction.md`; this document defines the architectural
commitments, milestone structure, and scope that make it possible.

The end goal is a usable, sound, extensible reasoner with a growing
verified theorem library — not a frontier-grade general mathematician,
not a Mathlib clone.

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
- A tool whose **knowledge base is hand-curated at its seed**. Adding
  new domain axioms is part of using the system. From M3 onwards, the
  system can also grow its library by generating, counterexample-testing,
  and proving its own conjectures — but only kernel-checked theorems
  are admitted, never anything that hasn't passed the trusted checker.
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
  clauses or conjectures during search — but only if it earns its place
  empirically, and the system must work fully without it.
- **Not a complete formalisation of mathematics.** Gödel's incompleteness
  theorems guarantee no such system exists for any consistent theory
  strong enough to express arithmetic. The system proves theorems
  *within* whatever knowledge base has been encoded or has been grown
  by the theory-growth loop. It does not enumerate truth.
- **Not a Lean or Coq replacement.** Mathlib has spent a decade
  formalising mathematics; HLMR will not catch up. The scope is
  intentionally narrower — bounded domain libraries grown from small
  axiom seeds.
- **Not a frontier benchmark contender.** MATH and GSM8K are explicitly
  not target benchmarks; they are dominated by LLMs and are the wrong
  shape for this system. Target metrics are described in §10.
- **Not a natural-language system.** The user types Prolog-flavoured
  syntax. NL parsing is, at best, a far-future extension.

If a feature request can only be justified by appeal to one of the
above framings, push back.

---

## 4. Architectural commitments

These are non-negotiable. Every milestone's design must respect them.

**The kernel is the only trusted component.** Search engines, unifiers,
SMT bridges, parsers, REPL UIs, conjecture generators, future learned
rankers — all of these can have bugs without compromising soundness,
*as long as every claimed proof is run through the kernel*. The kernel
is small enough to read in a sitting and is exhaustively tested. It
does not change casually.

**The IR is the single bus.** Every component reads and writes the same
formula and proof types. No component has its own private representation.
Every proof is JSON-serialisable.

**Construction and verification are separated.** Different milestones
vary *how* proofs are constructed (manual, SLD, dispatched solving,
automated search, conjecture-driven). They do not vary *how proofs are
checked*. The kernel is invariant.

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
kernel-verified proof. No exceptions. From M3 onwards, every theorem
admitted to the library has a kernel-verified proof. No theorem is
ever stored as merely "believed."

**Logging from day one.** Every user step (manual mode), every solver
step (automated mode), and every conjecture decision (theory-growth
mode, M3+) is logged with full state. This is the corpus that may
later inform learned components. Cheap to add now, expensive to add
later.

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
├── docs/
│   └── strategic_direction.md     (theory-growth long-term vision)
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
│   ├── theory/                    M3 (theorem library, signatures)
│   ├── conjecture/                M3 (typed templates, generation, filters)
│   ├── countermodel/              M3 (finite enumeration, Z3 model search)
│   ├── search/                    M3 (tactics, proof search, lemma mining)
│   ├── growth/                    M3 (loop orchestration, reports, policy)
│   └── cli.py
├── tests/                         (mirrors src/ structure)
├── proofs/                        Example proofs by milestone
├── examples/                      Example knowledge bases and theory seeds
├── benchmarks/                    Imported benchmark sets
└── corpus/                        Logged sessions (gitignored)
```

Hard structural rules:

- **`kernel/` imports only from `ir/` and stdlib.** Test-enforced from
  M0 (a dedicated `test_kernel_isolation.py` walks `kernel/*.py` and
  asserts no other imports).
- **No module replicates rule logic.** The kernel is the only place ND
  rule semantics are implemented.
- **`solvers/` is the only place Z3 and SymPy are imported.** Other
  modules go through its interface. (M3's `countermodel/` uses the
  M2 Z3 bridge for finite-model search rather than importing Z3
  directly.)
- **`theory/`, `conjecture/`, `countermodel/`, `search/`, and `growth/`
  may construct candidate proofs but never verify them.** Only the
  kernel produces verified status.

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
- A theory-growth loop (M3+) that generates, filters, counterexample-tests,
  proves, and admits theorems — preserving the soundness invariant that
  only kernel-checked proofs create new theorems
- Lightweight sort tags on predicate arguments (M3) so the conjecture
  generator can reject ill-typed candidates; full multi-sort logic
  remains a design question for M4 (§12)

### 6.2 Out of scope for V1

- Non-linear real arithmetic (beyond what SymPy handles for specific
  algebraic equations)
- Calculus (limits, derivatives, integrals)
- Higher-order logic, dependent types
- Set theory beyond finite sets
- Induction over arbitrary inductive types (induction over ℕ may be
  added later if it falls out of M3's search engine cheaply, or
  deferred to a number-theory domain milestone)
- Probability theory
- Multi-user accounts, web hosting, persistent server infrastructure
- Static HTML/JS frontend (deferred indefinitely; terminal is sufficient)
- Training a foundation-scale neural model
- Natural-language input parsing
- Proof reconstruction from external SMT proof calculi (witness-checking
  via the kernel replaces this)

### 6.3 What this means for the user

A user can:

- Write Prolog-flavoured Horn clauses and queries
- Drive proofs manually, picking clauses to resolve goals against
- (M2 onward) Mix logic with linear arithmetic and finite domains
- (M3 onward) Ask the system to search for proofs automatically
- (M3 onward) Provide a small theory seed and ask the system to grow
  a theorem library from it, with every admitted theorem
  kernel-checked
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
| **2** | Spec written, in progress (`prd_milestone_2.md`) | Z3 + SymPy bridges, dispatcher, `arithEval` kernel rule, typed metavariables, six-outcome classification | Linear arithmetic, quadratics, the §2 prime example |
| **3** | Spec to write | Theory library with metadata, sort-tagged predicates, typed conjecture generation, countermodel search, automated proof search with library reuse, growth loop orchestration | Equivalence-relation theory grown from three axioms; library reuse demonstrated |
| **4** | Planned | Second growth domain plus full multi-sort decision (lightweight tags or real multi-sort IR) | Partial-order theory grown from `≤` axioms |
| **5** | Planned | First multi-sort domain (`Point`, `Line`); incidence/betweenness/collinearity | Toy geometry library, 10–20 kernel-checked theorems |
| **6+** | Optional, deferred | Additional theory seeds run through the M3 engine: monoids/groups, simple number theory over M2's arithmetic, finite-domain combinatorics, formal-geometry sub-tracks | Domain-specific demos |

Each milestone is shippable on its own. Each strictly extends its
predecessor. The kernel has changed twice between M0 and M2 (in M1,
the `Meta` rejection check; in M2, the `arithEval` ground arithmetic
rule). Any further kernel change after M2 requires explicit design
review per §4.

The geometry roadmap from `docs/strategic_direction.md` §8 (G0–G6)
lives inside M5 and M6+ as a sub-track, not as numbered top-level
milestones.

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

### 7.5 Milestone 3 — theory growth POC (equivalence relations)

The long-term vision in `docs/strategic_direction.md` becomes
demonstrable here, in the smallest domain that can exercise the full
loop: equivalence relations over a single sort.

What M3 adds:

- **`theory/`** — theory signatures (sorts, predicate signatures,
  axioms, definitions), a theorem library that records each admitted
  theorem with its statement, dependencies, proof hash, and status
  (`kernel_checked`, `refuted_by_countermodel`, `open`,
  `failed_proof_attempt`, `duplicate`, `trivial_rejected`,
  `outside_fragment`).
- **`conjecture/`** — a template engine for typed conjecture
  generation (symmetry shape, transitivity shape, converse,
  contrapositive, recombination of existing theorems, mutation),
  filters for triviality, duplicate-modulo-renaming canonicalisation,
  type/binding checks, depth and variable-count budgets.
- **`countermodel/`** — finite-model enumeration for cheap refutation;
  Z3 model search via the M2 bridge for larger finite domains.
  Refuted conjectures are recorded with the witness, never silently
  discarded.
- **`search/`** — automated proof search using the M1 SLD engine as
  a backend, driven by a tactic priority list, with iterative
  deepening and per-attempt time budgets. Premise selection
  surfaces a small candidate set from the library by predicate-symbol
  overlap and usefulness score. Lemma mining: when a proof attempt
  fails at a known gap (`have P, need Q`), generate `P → Q` as a
  sub-conjecture, prove it if possible, and retry.
- **`growth/`** — the central loop from `docs/strategic_direction.md`
  §5 that orchestrates generation → filter → counterexample → prove →
  kernel-check → admit → re-rank.
- **IR additions** — lightweight sort tags on predicate arguments so
  the conjecture filter can reject ill-typed candidates. No full
  multi-sort logic at this stage; that decision is parked for M4.
- **Optional learned ranker** — a small specialised model for
  conjecture or premise ranking, gated on having ≥5,000 logged
  growth-loop steps. The system must work fully without it.

What M3 does *not* add:

- Real multi-sort logic (M4 design question).
- Domain content beyond the equivalence-relations seed.
- Geometry, number theory, group theory (M5+).
- Any extension to the kernel-trust surface — search and conjecture
  generation are construction, never verification.

The hard problem in M3 is not soundness (the kernel handles that) and
not completeness (false negatives are acceptable). The hard problem
is **growth-loop productivity**: keeping the conjecture/proof loop
generating useful theorems rather than noise. This is treated as the
central design challenge and demands explicit Opus design passes for
both halves of search (conjecture generation, proof search) and for
the theorem-library schema before implementation begins.

Demo: starting from the three equivalence-relation axioms, generate
≥5 non-trivial theorems, kernel-check them, store them with
dependencies, and demonstrate that at least one later proof uses an
earlier generated theorem. Average proof length should drop measurably
once lemma reuse kicks in. The full success criteria are listed in
`docs/strategic_direction.md` §12.

### 7.6 Milestone 4 — second growth domain, multi-sort decision

Generalises M3 to partial orders, the second domain in
`docs/strategic_direction.md` §7. The mathematical content
(antisymmetry consequences, chain properties, infimum/supremum
structure where it exists) is straightforward; the architectural
content is the **multi-sort decision**.

The lightweight sort-tag layer added in M3 is enough for partial
orders alone, but M5's geometry has truly distinct sorts (`Point`
versus `Line`) and forces the question. M4 either commits to "tags
forever" with whatever workarounds geometry needs, or extends the
IR with first-class multi-sort logic. This is an Opus-design
milestone.

Demo: grow a partial-order theory library from the `≤` axioms;
demonstrate cross-domain reuse where possible (e.g. equivalence and
partial-order theorems sharing a transitivity infrastructure).

### 7.7 Milestone 5 — toy geometry

First domain that genuinely requires multi-sort logic: `Point`,
`Line`, with predicates like `incident`, `between`, `collinear`,
`neq`. Axioms are kept tiny (the "G0/G1" stage of the geometry
roadmap in `docs/strategic_direction.md` §8). No mixing of informal
Euclid with formal Hilbert/Tarski axioms — pick one formal system
and stick to it.

Demo: 10–20 kernel-checked theorems grown from a small geometry
seed, including some non-obvious recombinations.

### 7.8 Milestone 6+ (optional, deferred)

Additional theory seeds run through the M3 engine. Each is
primarily content work (axiomatisation, demo curation) rather than
architecture work, since the engine exists by then. Candidates from
`docs/strategic_direction.md` §13:

- Monoids and groups
- Simple number theory built on M2's arithmetic and `arithEval`
- Finite-domain combinatorics
- Further geometry sub-tracks (G2–G6: congruence, triangles,
  parallel lines, formal Hilbert/Tarski subset)
- Domain-specific reasoning libraries

This is the part where Mathlib-style projects live. Explicit scoping
prevents the project from collapsing into one. M6+ milestones are
shipped one at a time, each as a small deliverable.

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
  M3 adds nothing required (countermodel search reuses M2's Z3
  bridge); may add `torch` only if and only if the optional learned
  ranker is built. Anything else needs explicit approval.

### 8.2 Testing

- `pytest` for unit and integration
- `hypothesis` for property tests (round-trips, kernel determinism,
  unifier soundness, conjecture-canonicalisation idempotence)
- Coverage targets: ≥95% on `kernel/`, `unify/`, `solve/sld.py`;
  ≥85% on renderers, dispatcher, and `theory/library`; ≥70% on
  parsers, REPL, and conjecture generators
- The soundness regression suite is run before every commit (locally
  for now; CI later). An unsoundness regression is a merge-blocker.
- M3 adds a soundness backstop test: a hand-built malicious search
  module returning bogus proofs is caught by the kernel, mirroring
  M0's `99_BAD_*` proofs and M1's renderer kernel-rejection test.

### 8.3 Logging

Every interactive session, every benchmark run, and every
theory-growth run produces JSONL. Schema is versioned and lives in
`src/hlmr/log/schema.md`. Logs are gitignored. A documented
`hlmr export-corpus` command bundles them for analysis or training.
M3 extends the schema with conjecture decisions (generation template,
filter results, countermodel result, proof attempt result, kernel-check
result, final status); schema bumps to v3.

### 8.4 Documentation

- Each module has a short README explaining its contract
- The kernel's contract is documented to a higher standard than other
  modules — it is the trust boundary
- A user-facing `docs/tutorial.md` walks through the REPL with worked
  examples by end of M1
- `docs/strategic_direction.md` is the standing reference for the
  theory-growth vision; M3+ designs cite it

### 8.5 Performance

Not an M0/M1/M2 concern. M3 introduces time budgets per tactic, per
proof attempt, and per growth-loop iteration. No optimisation work
before M3 unless something is unusably slow.

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
- **Search strategy design.** M3's tactic priorities, proof-search
  invariants, and lemma-mining policies.
- **Conjecture generation design.** M3's template engine, filters, and
  canonicalisation. A bad generator floods the loop with garbage; a
  too-restrictive one starves it.
- **Theorem library schema.** M3's library record format, dependency
  tracking, and usefulness scoring. Locked in once and expensive to
  change later.
- **Multi-sort decision.** M4's decision between lightweight tags and
  full multi-sort IR.
- **Knowledge-base axiomatisation.** When encoding domain content
  (M5+), the choice of axiomatisation matters and is research-flavoured.

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

## 10. Target metrics

The relevant measure of success changes shape between milestones.

For M0 through M2, the metrics are pass/fail on demonstrable
capability:

- M0: every soundness-regression and unsoundness-regression test passes.
- M1: each of the four demos (kinship, syllogism, finite puzzle, Peano
  even) produces a kernel-verified proof from the parser through the
  REPL.
- M2: each of the four demos (the §2 prime example, the quadratic, the
  linear system, the `OutsideFragment` rejection) produces a
  kernel-verified proof or an honest rejection. Multi-goal queries
  parse correctly. The soundness regression suite remains green.

For M3 and beyond, the metric is **library growth quality**, not
benchmark question-answering accuracy. The previous draft of this
PRD listed FOLIO, ProofWriter, and LogiQA as M3 targets; those are
question-answering benchmarks and are the wrong shape for a
theory-growth engine.

The M3 success criteria (full version in
`docs/strategic_direction.md` §12):

- A small theory seed loads correctly.
- Typed conjectures are generated within depth and variable budgets.
- Invalid, trivial, and duplicate conjectures are filtered with
  measurable rejection rates.
- False conjectures are rejected by countermodel search or proof
  failure rather than admitted.
- True conjectures are proved and kernel-checked.
- Proved theorems are stored with dependencies and proof hashes.
- A later proof uses an earlier generated theorem (the critical
  growth signal).
- A growth report shows library expansion over time, with average
  proof length dropping measurably once reusable lemmas accumulate.

For M4–M6+, the same growth-quality metrics apply, with each new
domain expected to demonstrate at least one cross-domain reuse where
the structure permits (e.g. transitivity infrastructure shared
between equivalence and partial-order theories).

Pure-arithmetic benchmarks (MATH, GSM8K) remain explicitly excluded.

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
in M1's definition of done, not retrofitted later. M3 extends the
schema rather than rebuilding it.

**Growth-loop unproductivity (M3+).** The conjecture generator emits
syntactically valid but uninteresting candidates; the loop fills the
library with junk theorems; usefulness scores fail to surface the few
genuinely useful ones; lemma mining floods the queue. Mitigation: M3
treats this as the central design problem rather than an
implementation detail. The growth report is designed before the loop
is built; usefulness metrics are required from day one; depth and
variable budgets are first-class controls; the equivalence-relations
POC is small enough that productivity failures are visible
immediately.

**Domain libraries devour the project's time.** Mitigation: M5+ are
optional and deferred. M3 (the engine) is the V1 deliverable beyond
M2. Hand-axiomatising new theory seeds is content work, deliberately
shipped one domain at a time.

**Model misuse during implementation.** Sonnet implements a section
that wanted Opus design and silently produces a flawed module.
Mitigation: per-milestone PRDs put model gates at the top, with
explicit "stop and ask" instructions.

---

## 12. Decisions deferred

These need answers before the milestone that uses them, but not now.

| Decision | Latest deadline |
|---|---|
| Sort layer scope: lightweight argument-position tags for M3, vs full multi-sort IR | Before M4 |
| Tactic interface: protocol, ABC, or plain function | Before M3 |
| Theorem library record schema (dependencies, proof hash, status, usefulness score) | During M3 design pass |
| Conjecture template format and extension mechanism | During M3 design pass |
| Premise selection algorithm (predicate-symbol overlap, indexed lookup, learned) | During M3 |
| Lemma-mining trigger policy (every failed proof, depth-gated, score-gated) | During M3 |
| Growth-report metric set (what counts as "growth") | Before M3 implementation |
| Whether to support induction over ℕ | Whenever a number-theory domain is taken on (likely M6+) |
| Whether the corpus is large enough to warrant the learned ranker | Late M3 |
| Multi-sort IR design (if M4 chooses full multi-sort) | During M4 |
| Domain library structure and curation policy | Before M5 |
| Whether to add a CI provider (GitHub Actions, etc.) | Before M3 implementation |

---

## 13. Document conventions

- `prd.md` (this document) is canonical at the strategic level. It
  changes infrequently and only with deliberate review.
- `prd_milestone_<n>.md` is the implementation spec for milestone *n*.
  It is written near the start of work on that milestone and is the
  document Claude Code should read before implementing.
- `docs/strategic_direction.md` is the standing reference for the
  theory-growth long-term vision. Per-milestone PRDs from M3 onwards
  cite it for context but defer to this document for architectural
  commitments.
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
an explicit fragment boundary that includes linear arithmetic via SMT
and symbolic algebra via SymPy, and from M3 onwards a theory-growth
loop that builds a verified library on top of that foundation.

The framing has explicitly been kept narrow. The project is not a
general mathematician, not an LLM, not a complete formalisation system.
It is a focused, sound, extensible reasoner with a bounded
theory-growth ambition.
