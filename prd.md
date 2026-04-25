# Hybrid Logic-Math Reasoner (HLMR) — Product Requirements

**Status:** Draft v1
**Owner:** project lead
**Last updated:** 2026-04-25

---

## 1. Executive summary

HLMR is a Python 3.12 hybrid reasoning engine that proves logical and mathematical problems containing unknowns, and returns a single object: a kernel-checked natural-deduction proof in which any unknowns have been resolved by unification, SMT, or symbolic algebra.

The system is built in four phases. Each phase produces something usable on its own, each strictly extends its predecessor, and the soundness root — a small auditable proof kernel — is built first and never modified casually thereafter.

| Phase | Deliverable | Who constructs proofs |
|---|---|---|
| 0 | Kernel + IR + CLI proof checker | Nobody (just checks) |
| 1 | Manual ND tool (terminal REPL) | The user, by hand |
| 2 | ND with unknowns | User + unification/SMT engine |
| 3 | Tactic engine (automated reasoning) | The system, automatically |

Phase 3 may later be augmented by a learned step-suggester trained on proof corpora collected from phases 1 and 2. The neural component is auxiliary; the kernel is the root of trust.

The target benchmarks are FOLIO, ProofWriter, LogiQA, Zebra-style logic puzzles, and a custom hybrid logic-plus-arithmetic suite. Not MATH or GSM8K.

---

## 2. Problem statement

Existing tools split unhelpfully along one axis: pure logic tools (Pandora, Carnap, Logitext) handle natural deduction but no arithmetic; pure math tools (SymPy, Mathematica, Wolfram Alpha) handle numbers but no inference; LLMs do both unreliably with no checkable trace.

HLMR fills the gap: a single engine that handles **proofs containing unknowns**, where the unknowns may be categorical (resolved by unification) or numeric (resolved by SMT or algebra), and where the output is always a proof the kernel has checked.

Concrete example of the differentiating problem:

```
Premises:
  1. ∀x. (Prime(x) ∧ x > 2) → Odd(x)
  2. Prime(?p)
  3. ?p > 2
  4. ?p < 6
  5. ¬Odd(4)

Goal: find ?p
```

A pure logic tool can't reason about `>`. A pure SMT tool can find `?p ∈ {3, 5}` but produces no proof. HLMR returns: `?p = 3` or `?p = 5`, with a kernel-checked derivation showing why each is consistent and why `?p = 4` is not.

---

## 3. Architectural commitments

These are non-negotiable design decisions that shape every phase. Anything contradicting them is wrong by construction.

**The kernel is the only trusted component.** Everything else — UI, parser, unification engine, SMT bridge, tactic engine, future neural suggester — can be buggy without compromising soundness, *as long as every claimed proof is run through the kernel*. The kernel must be small enough to read in one sitting and exhaustively tested.

**The IR is the single bus between components.** Every module reads and writes the same formula and proof types. No module has its own private representation. Every proof is JSON-serialisable.

**Construction and verification are separated.** Different phases vary *how* proofs are built (by hand, by unification, by tactic search). They do not vary *how proofs are checked*. The kernel is invariant across phases.

**The supported fragment is decidable and explicit.** First-order logic with equality, linear arithmetic over ℤ and ℚ, finite-domain constraints. Problems outside this fragment are rejected with a clear message, never attempted silently.

**Solver dispatch is explicit.** When unknowns need to be solved, the dispatcher chooses among unification, Z3, and SymPy by rule, not by heuristic. The choice is logged. Disagreements between solvers are bugs, and the kernel arbitrates.

**Soundness over completeness.** The system may fail to prove things it could in principle prove. It must never claim to have proved something it has not. False negatives are acceptable; false positives are catastrophic.

**Logging from day one.** Every proof step the user takes (phases 1, 2) and every step the system takes (phase 3) is logged with full proof state. This corpus is the asset that enables a future neural suggester. Cheap to add now, expensive to add later.

---

## 4. Scope

### 4.1 In scope for V1 (across all four phases)

- Propositional logic with all standard connectives (∧, ∨, ¬, →, ↔, ⊥)
- First-order logic with quantifiers (∀, ∃) over a single sort initially
- Equality reasoning (reflexivity, substitution)
- Linear arithmetic over ℤ and ℚ
- Finite-domain constraints (variables ranging over enumerated sets)
- Unknowns (metavariables) of categorical and numeric types
- Fitch-style natural deduction with explicit assumption boxes
- Terminal-based interaction (CLI/REPL); HTML+JS static page is acceptable but not required

### 4.2 Out of scope for V1

The following are explicitly not goals. Designs that hint at supporting them later are fine; designs that require them now are wrong.

- Non-linear real arithmetic
- Calculus (limits, derivatives, integrals)
- Higher-order logic, dependent types
- Set theory beyond finite sets
- Induction over arbitrary inductive types (induction over ℕ may be added in phase 3 if cheap)
- Geometry diagrams
- Probability theory
- General theorem proving over Mathlib-scale libraries
- Training a large neural model
- AutoML / data-predictability reasoning
- Multi-user accounts, persistence beyond local files, web hosting

### 4.3 Target benchmarks

Listed in increasing order of difficulty. Phase 3 success is measured against these.

- **FOLIO** — first-order logic NL problems
- **ProofWriter** — multi-step rule reasoning
- **LogiQA** — logical reasoning multiple choice
- **Zebra-style puzzles** — finite-domain constraint satisfaction with logical clues
- **Custom hybrid suite** — problems combining FOL inference with linear arithmetic and unknowns, constructed in-house

Pure-arithmetic benchmarks (MATH, GSM8K) are explicitly excluded. They are dominated by frontier LLMs and are not where this system is differentiated.

---

## 5. Repository structure

```
hlmr/
├── pyproject.toml
├── README.md
├── PRD.md                         (this document)
├── src/
│   └── hlmr/
│       ├── __init__.py
│       ├── ir/                    Phase 0
│       │   ├── __init__.py
│       │   ├── formula.py         Formula classes + structural ops
│       │   ├── proof.py           Proof, ProofLine, scope/box tracking
│       │   ├── justification.py   Rule application records
│       │   └── serialise.py       JSON in/out
│       ├── kernel/                Phase 0
│       │   ├── __init__.py
│       │   ├── rules.py           One function per ND rule
│       │   ├── check.py           check_proof(), check_step()
│       │   └── errors.py          Structured rule-violation errors
│       ├── parse/                 Phase 1+
│       │   ├── __init__.py
│       │   └── formula_parser.py  Lark-based formula syntax parser
│       ├── repl/                  Phase 1
│       │   ├── __init__.py
│       │   └── interactive.py     Interactive proof-building REPL
│       ├── unify/                 Phase 2
│       │   ├── __init__.py
│       │   ├── metavar.py         Metavariable representation in IR
│       │   ├── unifier.py         First-order unification with occurs check
│       │   └── dispatch.py        Unification / Z3 / SymPy dispatcher
│       ├── solvers/               Phase 2
│       │   ├── __init__.py
│       │   ├── z3_bridge.py       IR → Z3, model extraction → IR
│       │   └── sympy_bridge.py    IR → SymPy, results → IR
│       ├── tactics/               Phase 3
│       │   ├── __init__.py
│       │   ├── tactic.py          Tactic interface
│       │   ├── prop.py            Propositional tactics
│       │   ├── fol.py             FOL tactics
│       │   ├── arith.py           Arithmetic tactics
│       │   └── search.py          Top-level search loop
│       ├── log/                   Phase 1+
│       │   ├── __init__.py
│       │   └── recorder.py        Proof-step event logging
│       └── cli.py                 Click/Typer entrypoint
├── tests/
│   ├── kernel/
│   ├── ir/
│   ├── parse/
│   ├── repl/
│   ├── unify/
│   ├── solvers/
│   └── tactics/
├── proofs/                        Sample/example proofs in JSON
├── benchmarks/                    Imported benchmark sets
└── corpus/                        Logged proof traces (gitignored)
```

Key constraints on this layout:

- The `kernel/` module imports only from `ir/`. It must have zero external dependencies. This is enforceable via a CI check.
- Every other module imports from `kernel/` and `ir/`, never replicates rule logic.
- `solvers/` is the only place where Z3 and SymPy are imported. Other modules go through `solvers/` interfaces.

---

## 6. Phase 0 — kernel and IR

### 6.1 Goal

Build the minimum trusted core: a data type for formulas, a data type for proofs, a function that decides whether a proof is valid, and a CLI that runs that function on a JSON file.

No interactivity. No proof construction. No solving. No parsing of natural language. Pure library plus thin CLI.

### 6.2 IR specification

**Formula classes** (in `ir/formula.py`):

- `Var(name: str)` — variable, e.g. `x`, `y`
- `Const(value)` — constant, including numeric literals
- `Function(name: str, args: tuple[Term, ...])` — uninterpreted function term
- `Atom(predicate: str, args: tuple[Term, ...])` — atomic formula
- `Equals(lhs: Term, rhs: Term)` — equality (special-cased for kernel)
- `And`, `Or`, `Implies`, `Iff` — binary connectives
- `Not` — unary negation
- `Bot` — falsum (⊥)
- `ForAll(var: str, body: Formula)`, `Exists(var: str, body: Formula)` — quantifiers

All formula classes are frozen dataclasses with structural `__eq__` and `__hash__`. Pretty-printing supports both ASCII (`->`, `&`, `|`, `~`, `forall`, `exists`) and Unicode (`→`, `∧`, `∨`, `¬`, `∀`, `∃`).

**Proof classes** (in `ir/proof.py`):

- `ProofLine(number: int, formula: Formula, justification: Justification, box_depth: int)`
- `Proof(lines: tuple[ProofLine, ...], goal: Formula | None)`

Boxes are tracked by depth and by start/end markers. The proof is a flat list; box structure is recovered by walking depth changes. This keeps serialisation trivial.

**Justification classes** (in `ir/justification.py`):

- `Premise()` — given as input
- `Assumption()` — opens a new box
- `RuleApplication(rule_name: str, refs: tuple[int, ...], extra: dict)` — references previous lines by number; `extra` carries rule-specific data (e.g. the witness term for ∃-elim)

**Serialisation** (in `ir/serialise.py`):

A JSON round-trip: `to_json(proof) -> str` and `from_json(s: str) -> Proof`. The format must be human-readable enough to hand-edit. Versioned schema (`"hlmr_proof_version": 1`).

### 6.3 Rules to implement

Sixteen rules total. Each is one function in `kernel/rules.py` with signature `check(line, proof, env) -> Result`.

**Propositional (10):**

| Rule | Notation | What it does |
|---|---|---|
| ∧-intro | `andI` | from P, Q derive P ∧ Q |
| ∧-elim-L | `andE_L` | from P ∧ Q derive P |
| ∧-elim-R | `andE_R` | from P ∧ Q derive Q |
| ∨-intro-L | `orI_L` | from P derive P ∨ Q |
| ∨-intro-R | `orI_R` | from Q derive P ∨ Q |
| ∨-elim | `orE` | case analysis on P ∨ Q |
| →-intro | `impI` | discharge assumption |
| →-elim | `impE` | modus ponens |
| ¬-intro | `notI` | from assumption P deriving ⊥, conclude ¬P |
| ⊥-elim | `botE` | ex falso quodlibet |

Plus reiteration (copy a line from an enclosing scope) and ↔-intro/elim (derived but useful enough to be primitive).

**First-order (4):**

| Rule | Notation | What it does |
|---|---|---|
| ∀-intro | `forallI` | with eigenvariable side condition |
| ∀-elim | `forallE` | instantiate at any term |
| ∃-intro | `existsI` | from P[t/x] derive ∃x. P |
| ∃-elim | `existsE` | with eigenvariable side condition |

**Equality (2):**

| Rule | Notation | What it does |
|---|---|---|
| =-refl | `eqRefl` | derive t = t for any t |
| =-subst | `eqSubst` | from t = u and P[t/x] derive P[u/x] |

Each rule function returns either `Verified` or a structured error like `WrongFormulaShape(expected, got)`, `OutOfScopeReference(line, current_depth)`, `EigenvariableViolation(var)`, etc. No string error messages — errors are typed.

### 6.4 Scope and side conditions

Box scoping must be enforced rigorously. A line at depth `d` may reference earlier lines only if those lines are at depth `≤ d` *and* every box they belong to is still open at the current line. The kernel verifies this on every rule application that takes references.

Eigenvariable conditions for ∀-intro and ∃-elim must be checked: the eigenvariable must not appear free in any premise, in any open assumption, or in the conclusion of the relevant introduction.

These are the easy-to-get-wrong corners. They must have dedicated tests.

### 6.5 CLI

```
hlmr check path/to/proof.json
```

Outputs either `Verified` or a structured error pointing at the offending line and the reason. Exit code 0 for verified, 1 for failed, 2 for malformed input.

### 6.6 Tests

Three test suites, all required:

1. **Soundness suite.** A corpus of valid proofs that must check. Cover every rule. Cover nested boxes at depth ≥ 3. Cover eigenvariable corner cases.
2. **Unsoundness suite.** A corpus of *invalid* proofs that must fail with specific errors. Each test asserts the *type* of error, not just that it failed. This is the regression suite that protects soundness forever.
3. **Property tests.** Using Hypothesis: random valid proofs round-trip through JSON; checker is deterministic; random formula equality is reflexive/symmetric/transitive.

### 6.7 Definition of done for phase 0

- All 16 rules implemented and unit-tested.
- Soundness and unsoundness suites pass with ≥ 95% line coverage of `kernel/`.
- JSON round-trip tested with Hypothesis.
- `hlmr check` CLI works end-to-end on at least 20 hand-written example proofs in `proofs/`.
- `kernel/` has zero imports outside `ir/` and the standard library (CI-enforced).
- A short architectural note in `src/hlmr/kernel/README.md` explaining the kernel's contract for future contributors.

### 6.8 Dependencies introduced

- `pytest`, `hypothesis` (test only)
- Standard library only for `kernel/` and `ir/`

No Z3, no SymPy, no parser library yet.

---

## 7. Phase 1 — manual ND tool (terminal)

### 7.1 Goal

Make the kernel usable interactively. The user types rule applications at a REPL; the kernel checks each one live; the proof grows by one line at a time.

This is the Pandora-equivalent. Pedagogically it should feel like Pandora; structurally it is a thin REPL over the phase 0 kernel.

### 7.2 Interaction model

Construction-time checking, not post-hoc. Every rule application is checked immediately and rejected immediately if invalid. The user always sees a verified partial proof.

REPL commands (minimum set):

```
goal <formula>            set the goal
premise <formula>         add a premise
assume <formula>          open a new assumption box
discharge                 close current box (only valid if rule chosen needs it)
apply <rule> <args>       apply rule, e.g. apply andI 2 3
undo                      remove last line
show                      pretty-print current proof state
save <path>               write proof to JSON
load <path>               replace proof state from JSON
verify                    re-run kernel check on full proof (sanity)
help                      list commands and rules
quit
```

Pretty-printing shows a Fitch-style indented proof with line numbers, box bars, and the current goal. ASCII by default; `--unicode` flag for boxed Unicode rendering.

### 7.3 Formula parser

Phase 1 needs a parser for formulas typed at the prompt. Use Lark with an explicit grammar. Accept both ASCII and Unicode operators. No NL parsing yet.

Parser module: `parse/formula_parser.py`. Returns IR formula objects. Errors are user-friendly, not stack traces.

### 7.4 Logging

Every command the user runs is logged to `corpus/<session-id>.jsonl` with timestamp, command, resulting proof state hash, and (for `apply` commands) the rule, refs, and whether the kernel accepted it. This is the seed of the future training corpus. Logging is on by default; `--no-log` flag to disable.

### 7.5 Definition of done for phase 1

- REPL supports all commands listed in 7.2.
- A user can complete the standard intro-logic suite end-to-end: De Morgan's laws, contraposition, distributivity, basic FOL exercises, basic equality reasoning. At least 30 such exercises pass.
- Every step is kernel-checked. There is no path that constructs an unverified proof line.
- Logging produces well-formed JSONL.
- REPL has a help system and reasonable error messages.

### 7.6 Dependencies introduced

- `lark` (formula parser)
- `click` or `typer` (CLI scaffolding)
- `rich` (proof pretty-printing) — optional but nice

---

## 8. Phase 2 — natural deduction with unknowns

### 8.1 Goal

Allow proofs and premises to contain metavariables (unknowns). Add a unification/SMT/algebra layer that proposes values for those unknowns. Re-check the resulting fully-instantiated proof with the kernel.

The kernel does not change. It still only sees ground (instantiated) formulas. The new machinery sits beside it.

### 8.2 Metavariables in IR

Add a single new term type: `Meta(name: str, type: MetaType)` where `MetaType` ∈ `{Categorical, Integer, Rational, FiniteDomain(values)}`. The kernel rejects proofs containing un-resolved metavariables. The dispatcher's job is to resolve them, then hand the instantiated proof to the kernel.

### 8.3 Solver dispatch

Explicit policy, no heuristic guessing. In `unify/dispatch.py`:

1. Collect all constraints involving unknowns from the proof's premises, assumptions, and goal.
2. Classify each constraint:
   - Pure first-order with categorical metas → unification
   - Linear (in)equalities over ℤ or ℚ → Z3
   - Symbolic algebraic equations → SymPy
   - Mixed → decompose where possible; if not decomposable cleanly, fail with a clear "unsupported mixed constraint" message rather than guess.
3. Run the appropriate solver(s). Collect candidate values.
4. For each candidate assignment, instantiate the proof and run the kernel.
5. Return: the set of assignments that produce kernel-verified proofs, together with those proofs.

Solver disagreements (e.g. Z3 says SAT but the resulting instantiated proof fails the kernel) are bugs and should crash loudly during development. The kernel is the arbiter.

### 8.4 Unification module

First-order unification with occurs check. Standard Robinson algorithm. Scope-aware: a metavariable introduced inside a box may only be resolved using terms accessible from that scope.

Before implementing, spend a day reading λProlog and the "uniform proofs" results (Miller, Nadathur), and the Imperial logic group's papers on Prolog-in-Pandora (Broda, Hogger). The risk of informally inventing scoping rules is real and these papers cover the corner cases.

### 8.5 Z3 and SymPy bridges

- `solvers/z3_bridge.py`: IR → Z3 expression, Z3 model → IR term. Supports linear arithmetic, equalities, finite domains.
- `solvers/sympy_bridge.py`: IR → SymPy, solve(), back to IR. For algebraic simplification and equation solving.

Both bridges have round-trip property tests: `from_z3(to_z3(f)) == f` for every formula in the supported fragment.

### 8.6 Outcome classification

The dispatcher returns one of:

- `UniqueSolution(assignment, proof)`
- `MultipleSolutions(list[(assignment, proof)])` — finite enumeration only
- `InfinitelyManySolutions(parametric_form, sample_proof)`
- `NoSolution(why)` — with a contradiction proof when possible
- `Underdetermined(free_metas)`
- `OutsideFragment(reason)`

These map cleanly to the outcome taxonomy in the original notes (§11) and are user-visible in the REPL output.

### 8.7 REPL extensions

New commands:

```
meta <name> <type>        introduce a metavariable
solve                     run the dispatcher to resolve all unknowns
solutions                 list all assignments found
```

### 8.8 Definition of done for phase 2

- Metavariables work in formulas at all nesting levels.
- The "find ?p" example from §2 works end-to-end.
- A small benchmark of 20 hybrid logic+arithmetic problems passes.
- Outcome classification covers all six cases with tests.
- Bridge round-trip tests pass with Hypothesis.

### 8.9 Dependencies introduced

- `z3-solver`
- `sympy`

---

## 9. Phase 3 — tactic engine

### 9.1 Goal

Automate proof construction. The user states a goal; the system finds a proof.

Architectural choice: tactic engine, not classical proof search, not neural search. Tactics are hand-written high-level strategies that propose sequences of rule applications. The kernel still checks every step.

### 9.2 Tactic interface

```python
class Tactic(Protocol):
    name: str
    def apply(self, state: ProofState) -> Iterable[ProofState]:
        """Yield zero or more candidate next states. Each is kernel-verified
        because the underlying rule applications are checked at construction."""
```

### 9.3 Built-in tactics

Minimum set:

- `auto_prop` — propositional completeness via tableau or DPLL-style search, then reconstruct ND proof
- `intro` — apply introduction rules until no more apply (→-intro for implications, ∀-intro for universals, etc.)
- `assumption` — close goal if it matches an available premise/assumption
- `mp_search` — search for modus ponens chains using available premises
- `case` — case-split on a disjunction
- `contra` — proof by contradiction (assume ¬goal, derive ⊥)
- `omega` — linear arithmetic over ℤ via Z3, then reconstruct ND-style witness
- `linarith` — linear arithmetic over ℚ
- `decide_finite` — finite-domain enumeration

### 9.4 Search strategy

Top-level loop in `tactics/search.py`: iterative deepening over a tactic priority list, with a per-attempt time budget. Failed searches return a partial proof state and an explanation of what was tried.

Soundness invariant: search may fail to find a proof, but every state it returns is kernel-verified.

### 9.5 Optional: learned suggester

If by phase 3 there is enough corpus from phases 1 and 2 (target: ≥ 5,000 proof steps), train a small transformer (target: ≤ 100M parameters) that takes a proof state and predicts the next tactic to try. Insert it as a priority-reorderer in the search loop.

This is optional and gated on corpus size. The system must work fully without it.

### 9.6 Benchmark harness

`benchmarks/` directory contains importers for FOLIO, ProofWriter, LogiQA, and Zebra puzzles. A `hlmr bench <suite>` command runs the system over each problem and reports verified-correctness rate, average solve time, and failure breakdown.

### 9.7 Definition of done for phase 3

- Auto-proves ≥ 80% of an intro-logic propositional suite.
- Auto-proves ≥ 50% of a curated FOL subset.
- Solves ≥ 70% of Zebra-style finite-domain puzzles within 30 seconds each.
- Hybrid suite (logic + linear arithmetic with unknowns): target ≥ 60%.
- Every reported "solved" problem has a kernel-verified proof. No exceptions.

### 9.8 Dependencies introduced

- Possibly `torch` and `transformers` if the learned suggester is built
- Otherwise none beyond phase 2

---

## 10. Cross-cutting concerns

### 10.1 Testing strategy

- `pytest` for unit and integration tests
- `hypothesis` for property tests, especially round-trips and kernel determinism
- Coverage target: ≥ 95% on `kernel/`, ≥ 85% on `ir/`, ≥ 70% on others
- CI runs the soundness suite on every commit; an unsoundness regression blocks merge

### 10.2 Logging and corpus

Every interactive session and every benchmark run produces a JSONL log of proof events. The schema is versioned and lives in `src/hlmr/log/schema.md`. Logs are gitignored but a documented "export corpus" command bundles them for training use.

### 10.3 Performance

Not a phase 0, 1, or 2 concern. Phase 3 introduces time budgets per tactic and per overall proof attempt. No performance work before phase 3 unless something is unusably slow.

### 10.4 Documentation

- Each module has a short README explaining its contract.
- The kernel's contract is documented to a higher standard than other modules — it is the trust boundary.
- A user-facing `docs/tutorial.md` walks through the REPL with worked examples by phase 1's end.

### 10.5 Frontend (deferred / optional)

If a UI becomes desirable, the chosen approach is a static HTML+JS page that calls a small local Python server exposing the kernel and dispatcher over JSON. Not required for any phase's definition of done. Listed here so it doesn't get reinvented later.

---

## 11. Decisions deferred

These need answers before the phase that uses them, but not now.

| Decision | Latest deadline |
|---|---|
| Typed vs untyped first-order terms | Before phase 2 |
| Eigenvariable representation in serialised proofs | Before phase 0 ships |
| λProlog-style higher-order patterns vs first-order unification only | Before phase 2 |
| Whether to support ↔ as primitive or derived | Before phase 0 ships |
| Concrete textual proof format for phase 1 (in addition to JSON) | Before phase 1 ships |
| Whether to support induction over ℕ in phase 3 | Before phase 3 |
| Which corpus size triggers the learned suggester | During phase 3 |

---

## 12. Risks

**Kernel soundness bug.** Mitigation: unsoundness regression suite, tiny kernel surface, no kernel changes without code review.

**Scope creep into non-linear arithmetic or higher-order logic.** Mitigation: the "outside fragment" outcome is first-class and the parser/dispatcher actively rejects.

**Unification scoping bugs in phase 2.** Mitigation: read the literature first, dedicated test suite for nested-box unknowns.

**Z3/SymPy disagreement with the kernel.** Mitigation: kernel is the arbiter; disagreements crash during development; bridge round-trip property tests.

**Phase 3 over-promises.** Mitigation: the learned suggester is optional; tactic engine is the deliverable; benchmarks have explicit success thresholds rather than "as well as possible."

**Corpus collection forgotten until too late.** Mitigation: logging is built into phase 1 from day one, not added later.

---

## 13. Project instruction recap

The Claude Project instructions encode the architectural commitments above. Any plan that contradicts them — training a large neural model, competing on MATH/GSM8K, promising general theorem proving, treating non-kernel output as trusted — should be pushed back on.