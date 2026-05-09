# HLMR — Hybrid Logic-Math Reasoner

A Python 3.12 theorem prover that finds proofs of logical and mathematical
goals over a user-supplied knowledge base, renders every result as a
Fitch-style natural-deduction proof, and verifies it through a small
trusted kernel before reporting success.

**Status:** M0 and M1 shipped. M2 (arithmetic + dispatcher) is mid-flight
— spec frozen, all three Opus 4.7 design docs approved, Sonnet
implementation up next. M3 (theory-growth POC) is spec-to-write.

---

## What HLMR is for

HLMR fills a specific gap in the existing landscape:

- **Pure logic tools** (Pandora, Carnap, Logitext) handle natural deduction
  but no arithmetic and no goal-directed search.
- **Pure math tools** (SymPy, Mathematica, Wolfram Alpha) handle numbers
  but produce no inference trace.
- **Logic programming** (Prolog, λProlog) does goal-directed search but
  doesn't render proofs in a form a student or reviewer can audit step
  by step.
- **Frontier LLMs** do everything plausibly and nothing checkably.
  Soundness is not a property they have.

HLMR is a single engine where (a) the user writes domain knowledge as
Horn clauses, (b) goals can contain unknowns, (c) proofs come out in a
presentation-friendly ND format, and (d) every proof is mechanically
checked by a kernel small enough to audit.

### The main goals, in order

1. **Soundness through a small trusted kernel.** The kernel implements the
   23 ND rules (22 in M0–M1 plus `arithEval` in M2) and nothing else. It
   imports only `ir/` and stdlib — test-enforced from M0. Search modules,
   solvers, dispatchers, and (later) conjecture generators may construct
   candidate proofs but never declare them verified. Only the kernel does
   that. **Construction may be wrong; verification cannot.**

2. **Two interaction modes against the same engine.** *Manual mode* (M1,
   shipped): you state a goal with unknowns, the system shows you every
   applicable clause at each step, you pick, the unifier finds the
   bindings. *Automated mode* (M3): the system searches, you watch.
   Same kernel, same IR, same proof format.

3. **Hybrid logic + math.** First-order logic with quantifiers (M0–M1)
   plus linear arithmetic over ℤ/ℚ, finite-domain constraints, and
   symbolic algebraic equations (M2, via Z3 and SymPy). The kernel
   verifies arithmetic witnesses by ground evaluation — Z3's internal
   proof calculus is never translated into Fitch ND.

4. **Long-term: a proof-checked theory growth engine.** Starting M3, the
   system grows reusable theorem libraries from small axiom seeds:
   generate typed conjectures, filter trivial/duplicate/ill-typed ones,
   try to refute via countermodel search, attempt proof, kernel-check,
   admit only verified theorems. The success metric is **library reuse
   and proof shortening**, not raw theorem count. See
   [`docs/strategic_direction.md`](docs/strategic_direction.md) for the
   full vision.

The end goal is a usable, sound, extensible reasoner with a growing
verified theorem library — **not** a frontier-grade general
mathematician, **not** a Mathlib clone, **not** a Lean replacement.
Different foundations, different scale, different community model.

### The motivating example (demoable by end of M2)

```
KB:
  prime(2). prime(3). prime(5). prime(7).

Query:
  ?- prime(?P), greater_than(?P, 2), less_than(?P, 6), not_equal(?P, 4).

Answer:
  ?P = 5.
```

The first goal runs SLD over the KB; the inequality goals dispatch to Z3;
the witness `?P = 5` is verified by the kernel via the new `arithEval`
rule; and the result is a Fitch proof you can audit line-by-line.

See [`prd.md`](prd.md) for the canonical spec and per-milestone PRDs for
implementation detail.

---

## What's working today

**Milestone 0** — the trusted core (shipped):
- Fitch-style natural-deduction proof kernel (22 ND rules)
- CLI proof checker (`hlmr check`) and pretty-printer (`hlmr show`)
- JSON proof format with schema versioning

**Milestone 1** — the manual solver (shipped):
- Horn-clause knowledge bases parsed from Prolog-flavoured `.pl` files
- First-order Robinson unification with occurs check
- Manual SLD resolution: you pick each clause; the system binds variables
- SLD-trace-to-Fitch renderer: every solved query becomes a kernel-verified proof
- Interactive REPL with `back` (undo last pick), `abort`, `:load`, `:export`
- JSONL session logging for future training corpus
- Four canonical demos with kernel-verified proof artifacts

**M1 hardening** — 30-fixture proof corpus and adversarial tests:
- `proofs/m1/` — 26 new fixtures (kinship chains, Peano plus/times/lt,
  capture-avoidance stress, edge cases) plus the 4 original demo proofs;
  each with sidecar metadata. See `proofs/m1/README.md` for the full index
  and `proofs/m1/HARDENING_FINDINGS.md` for property-test findings.
- Regenerate the corpus: `python -m hlmr regenerate-corpus`

**Milestone 2** — arithmetic and dispatch (**shipped**):
- `arithEval` — 23rd kernel rule; verifies ground arithmetic atoms by exact
  evaluation (no floating-point; Python `int` + `fractions.Fraction` only)
- Z3 bridge — linear arithmetic over ℤ/ℚ, finite-domain constraints,
  inequality solving; verify-before-return prevents unsound witnesses
- SymPy bridge — symbolic polynomial root-finding via `solveset` on ℝ;
  multi-root `MultipleSolutions` with contested-convention (0^0) rejection
- Dispatcher — classifies goals (KB / Z3 / SymPy / OutsideFragment),
  routes per goal, produces `DispatcherResolvedStep` for the renderer
- Renderer extension — `arithEval` / `eqRefl` lines, multi-goal andI-chain,
  depth-0 invariant; full Fitch proofs for mixed KB+arithmetic queries
- REPL extended — arithmetic goals auto-dispatch; `:solver` command;
  `MultipleSolutions` interactive picker; `OutsideFragment` rejection messages
- Four M2 demos: `prime_search`, `quadratic`, `linear_system`, `outside_fragment`

---

## M2 — arithmetic queries

### Installation

M2 adds two runtime dependencies (already in `pyproject.toml`):

```powershell
pip install -e ".[test]"   # installs z3-solver and sympy
```

### Running the M2 demos

```powershell
# §2 prime example: KB prime facts + Z3 inequalities → ?P = 5
python -m hlmr demo prime_search

# Quadratic: SymPy root-finding → ?X = 2 (one of {2, 3})
python -m hlmr demo quadratic

# Linear system: Z3 → ?X = 2, ?Y = 8
python -m hlmr demo linear_system

# Honest rejection: transcendental outside the M2 fragment
python -m hlmr demo outside_fragment
```

Proof JSON artifacts land in `proofs/m2/`.

### Using the M2 REPL

```powershell
python -m hlmr repl
```

The REPL auto-detects arithmetic predicates (`plus`, `minus`, `times`,
`divides`, `root_of`) and dispatches them to Z3 or SymPy automatically — no
manual pick required for those goals. KB predicates still use the manual
pick loop as in M1.

```
kb> prime(2).
kb> prime(3).
kb> prime(5).
kb> prime(7).
kb> :query
?- plus(?X, ?Y, 10).
Dispatching: plus(?X, ?Y, 10) (z3)
...
?- root_of(?X, x^2-5x+6).     # parsed as func syntax
Dispatching: root_of(?X, ...) (sympy)
Multiple solutions found. Pick one:
  [0] {?X = 2}
  [1] {?X = 3}
choice: 0
Solved: ?X = 2
```

Use `:solver` to inspect the most recent dispatcher decision:

```
:solver
  Classification: route=sympy
  Outcome: UniqueSolution: {?X = 2}
```

### Architecture pointers

- [`prd_milestone_2.md`](prd_milestone_2.md) — full M2 spec and §14 definition of done
- [`src/hlmr/dispatch/DISPATCH_DESIGN.md`](src/hlmr/dispatch/DISPATCH_DESIGN.md) — Opus 4.7 design for the dispatcher: constraint classification, Z3/SymPy dispatch paths, Case 1/Case 2 solver/kernel disagreement handling
- [`src/hlmr/kernel/ARITH_EVAL_DESIGN.md`](src/hlmr/kernel/ARITH_EVAL_DESIGN.md) — `arithEval` rule design
- [`src/hlmr/solve/RENDER_M2_DESIGN.md`](src/hlmr/solve/RENDER_M2_DESIGN.md) — renderer extension design

---

## Requirements

- Python 3.12+
- Windows (PowerShell) or Linux/macOS

A venv lives at `env_hlmr/`. To create one from scratch:

```powershell
python -m venv env_hlmr
```

## Install

```powershell
# Activate (PowerShell)
.\env_hlmr\Scripts\Activate.ps1

# Install in editable mode with test and lint tools
pip install -e ".[test]"

# Wire git hooks (do this once per clone)
pre-commit install
```

---

## Try it yourself

### 1. Check a hand-built proof

`proofs/m0/` ships 16 example proofs — 13 valid and 3 deliberately broken.

```
$ python -m hlmr check proofs/m0/01_modus_ponens.json
verified (3 lines)
```

```
$ python -m hlmr show proofs/m0/01_modus_ponens.json
1. (P -> Q)                             Premise
2. P                                    Premise
3. Q                                    impE 1, 2
```

The three `99_BAD_*` proofs exercise kernel rejection. Here the `andI` rule
is given `(P & Q)` where the conclusion says `(Q & P)`:

```
$ python -m hlmr check proofs/m0/99_BAD_andI.json
rejected at line 3: FormulaMismatch: ('andI', (P & Q), (Q & P))
```

Exit codes: 0 verified, 1 rejected, 2 malformed input.

---

### 2. Run a built-in demo

```
$ python -m hlmr demo
Available demos:
  syllogism
  kinship
  finite_puzzle
  peano_even
```

**Syllogism** (4-line proof, no unknowns):

```
$ python -m hlmr demo syllogism
1. (forall X. (human(X) -> mortal(X)))  Premise
2. human('socrates')                    Premise
3. (human('socrates') -> mortal('socrates'))  forallE 1 [term='socrates']
4. mortal('socrates')                   impE 3, 2
```

**Kinship** (12-line proof, recursive KB, witness `?A = alice`):

```
$ python -m hlmr demo kinship
 1. (forall X. (forall Y. (forall Z. ((parent(X, Z) & ancestor(Z, Y)) -> ancestor(X, Y)))))  Premise
 2. parent('alice', 'bob')               Premise
 3. (forall X. (forall Y. (parent(X, Y) -> ancestor(X, Y))))  Premise
 4. parent('bob', 'carol')               Premise
 5. (forall Y. (parent('bob', Y) -> ancestor('bob', Y)))  forallE 3 [term='bob']
 6. (parent('bob', 'carol') -> ancestor('bob', 'carol'))  forallE 5 [term='carol']
 7. ancestor('bob', 'carol')             impE 6, 4
... [5 more lines]
12. ancestor('alice', 'carol')           impE 10, 11
```

Each demo also writes its proof to `proofs/m1/<name>.json`.

---

### 3. Interactive REPL session

The REPL lets you build a knowledge base, then issue queries and pick clauses
step-by-step. Here is a complete session using the kinship KB:

```
$ python -m hlmr repl
HLMR REPL — session 2026-05-04T10-48-16_0590e71e
Type ':help' for commands.

kb> :load examples/m1/kinship.pl
  Loaded 4 clause(s) from 'examples/m1/kinship.pl'.

kb> ?- ancestor(?X, carol).

Goal (1 remaining): ancestor(?X, carol)
Candidates:
  1. ancestor(X, Y) :- parent(X, Y).  (rule, ancestor_1)
  2. ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).  (rule, ancestor_2)

> 2

Goal (2 remaining): parent(?X_1, ?Z_3)
Candidates:
  1. parent(alice, bob).  (fact, parent_1)
  2. parent(bob, carol).  (fact, parent_2)

> 1

Goal (1 remaining): ancestor(bob, carol)
Candidates:
  1. ancestor(X, Y) :- parent(X, Y).  (rule, ancestor_1)
  2. ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).  (rule, ancestor_2)

> 1

Goal (1 remaining): parent(bob, carol)
Candidates:
  1. parent(alice, bob).  (fact, parent_1)
  2. parent(bob, carol).  (fact, parent_2)

> 2

Solved: ?X = alice, ?X_1 = alice, ?X_4 = bob, ?Y_2 = carol, ?Y_5 = carol, ?Z_3 = bob
Proof: 12 lines, kernel-verified.
Type ':show last' to display, ':export proof.json' to save.

> :show last
 1. (forall X. (forall Y. (forall Z. ((parent(X, Z) & ancestor(Z, Y)) -> ancestor(X, Y)))))  Premise
 2. parent('alice', 'bob')               Premise
... [8 more lines]
12. ancestor('alice', 'carol')           impE 10, 11

> :quit
Bye.
```

The session is logged to `corpus/<session-id>.jsonl` by default. Pass
`--no-log` to suppress.

**Query-mode commands:** `1`–`N` to pick a clause, `back` to undo the last
pick, `abort` to cancel, `candidates` to redisplay the list.

**KB-mode commands:** `:load <path>`, `:save <path>`, `:export <path>`,
`:show kb`, `:show last`, `:query`, `:edit`, `:help`, `:quit`.

---

### 4. Arithmetic over Peano naturals

`examples/m1/plus.pl` encodes Peano addition; `examples/m1/mult.pl` adds
multiplication. Both predicates run forward (compute a result) and backward
(solve for an unknown argument).

> Note: this is structural arithmetic via successor terms — `s(s(0))` for 2,
> `s(s(s(0)))` for 3 — purely SLD over a Horn-clause KB. Real arithmetic
> with literal numerics, `<`, `>`, `+`, `*` arrives in M2 with the Z3
> bridge and the `arithEval` kernel rule.

**2 + 1 = ?**

```
kb> ?- plus(s(s(0)), s(0), ?R).

Goal (1 remaining): plus(s(s(0)), s(0), ?R)
Candidates:
  1. plus(0, Y, Y).  (fact, plus_1)
  2. plus(s(X), Y, s(Z)) :- plus(X, Y, Z).  (rule, plus_2)
> 2

Goal (1 remaining): plus(s(0), s(0), ?Z_3)
Candidates:
  1. plus(0, Y, Y).  (fact, plus_1)
  2. plus(s(X), Y, s(Z)) :- plus(X, Y, Z).  (rule, plus_2)
> 2

Goal (1 remaining): plus(0, s(0), ?Z_6)
Candidates:
  1. plus(0, Y, Y).  (fact, plus_1)
  2. plus(s(X), Y, s(Z)) :- plus(X, Y, Z).  (rule, plus_2)
> 1

Solved: ?R = s(s(s(0)))
Proof: 11 lines, kernel-verified.
?- :show last
 1. (forall X. (forall Y. (forall Z. (plus(X, Y, Z) -> plus(s(X), Y, s(Z))))))  Premise
 2. (forall Y. plus(0, Y, Y))            Premise
 3. plus(0, s(0), s(0))                  forallE 2 [term=s(0)]
... [8 more lines]
11. plus(s(s(0)), s(0), s(s(s(0))))      impE 10, 7
```

**Backward: 2 + ? = 3**

Supply the result and leave the addend unknown; unification finds it:

```
?- plus(s(s(0)), ?X, s(s(s(0)))).
... (picks: 2, 2, 1)

Solved: ?X = s(0)
Proof: 11 lines, kernel-verified.
```

**1 + 1 = 2** (7-line proof):

```
?- plus(s(0), s(0), ?X).
... (picks: 2, 1)

Solved: ?X = s(s(0))
Proof: 7 lines, kernel-verified.
?- :show last
1. (forall X. (forall Y. (forall Z. (plus(X, Y, Z) -> plus(s(X), Y, s(Z))))))  Premise
2. (forall Y. plus(0, Y, Y))            Premise
3. plus(0, s(0), s(0))                  forallE 2 [term=s(0)]
4. (forall Y. (forall Z. (plus(0, Y, Z) -> plus(s(0), Y, s(Z)))))  forallE 1 [term=0]
5. (forall Z. (plus(0, s(0), Z) -> plus(s(0), s(0), s(Z))))  forallE 4 [term=s(0)]
6. (plus(0, s(0), s(0)) -> plus(s(0), s(0), s(s(0))))  forallE 5 [term=s(0)]
7. plus(s(0), s(0), s(s(0)))            impE 6, 3
```

**2 × 3 = 6**

```
kb> :load examples/m1/mult.pl
  Loaded 4 clause(s) from 'examples/m1/mult.pl'.

kb> ?- mult(s(s(0)), s(s(s(0))), ?R).

Goal (1 remaining): mult(s(s(0)), s(s(s(0))), ?R)
Candidates:
  1. mult(0, Y, 0).  (fact, mult_1)
  2. mult(s(X), Y, Z) :- mult(X, Y, W), plus(W, Y, Z).  (rule, mult_2)
> 2

Goal (2 remaining): mult(s(0), s(s(s(0))), ?W_4)
...
> 2

Goal (3 remaining): mult(0, s(s(s(0))), ?W_8)
...
> 1

... (5 more picks to discharge the plus subgoals)

Solved: ?R = s(s(s(s(s(s(0))))))
Proof: 32 lines, kernel-verified.
```

**1 × 1 = 1** — 11 steps:

```
?- mult(s(0), s(0), ?R).

Goal (1 remaining): mult(s(0), s(0), ?R)
Candidates:
  1. mult(0, Y, 0).  (fact, mult_1)
  2. mult(s(X), Y, Z) :- mult(X, Y, W), plus(W, Y, Z).  (rule, mult_2)
> 2

Goal (2 remaining): mult(0, s(0), ?W_4)
Candidates:
  1. mult(0, Y, 0).  (fact, mult_1)
  2. mult(s(X), Y, Z) :- mult(X, Y, W), plus(W, Y, Z).  (rule, mult_2)
> 1

Goal (1 remaining): plus(0, s(0), ?Z_3)
Candidates:
  1. plus(0, Y, Y).  (fact, plus_1)
  2. plus(s(X), Y, s(Z)) :- plus(X, Y, Z).  (rule, plus_2)
  3. plus(0, Y, Y).  (fact, plus_1)
  4. plus(s(X), Y, s(Z)) :- plus(X, Y, Z).  (rule, plus_2)
> 3

Solved: ?R = s(0)
Proof: 11 lines, kernel-verified.
?- :show last
 1. (forall X. (forall Y. (forall Z. (forall W. ((mult(X, Y, W) & plus(W, Y, Z)) -> mult(s(X), Y, Z))))))  Premise
 2. (forall Y. mult(0, Y, 0))            Premise
 3. (forall Y. plus(0, Y, Y))            Premise
 4. mult(0, s(0), 0)                     forallE 2 [term=s(0)]
 5. plus(0, s(0), s(0))                  forallE 3 [term=s(0)]
 6. (forall Y. (forall Z. (forall W. ((mult(0, Y, W) & plus(W, Y, Z)) -> mult(s(0), Y, Z)))))  forallE 1 [term=0]
 7. (forall Z. (forall W. ((mult(0, s(0), W) & plus(W, s(0), Z)) -> mult(s(0), s(0), Z))))  forallE 6 [term=s(0)]
 8. (forall W. ((mult(0, s(0), W) & plus(W, s(0), s(0))) -> mult(s(0), s(0), s(0))))  forallE 7 [term=s(0)]
 9. ((mult(0, s(0), 0) & plus(0, s(0), s(0))) -> mult(s(0), s(0), s(0)))  forallE 8 [term=0]
10. (mult(0, s(0), 0) & plus(0, s(0), s(0)))  andI 4, 5
11. mult(s(0), s(0), s(0))               impE 9, 10
```

(The 4-candidate list for plus appears because `plus.pl` and `mult.pl` were both loaded in this session. Candidates 1/2 and 3/4 are identical — pick either base or step.)

---

## Demos

Four canonical demos ship with M1, each producing a kernel-verified proof
saved under `proofs/m1/`:

| Name | Description |
|---|---|
| `syllogism` | "All humans are mortal; Socrates is human" — 4-line proof |
| `kinship` | Recursive ancestor KB; finds `?X = alice` for `ancestor(?X, carol)` |
| `finite_puzzle` | Colour-chain puzzle; proves `chain(red, green, blue)` — 15 lines |
| `peano_even` | Peano naturals; proves `even(s(s(s(s(0)))))` — 6 lines |

---

## CLI surface

```powershell
python -m hlmr check PROOF.JSON   # verify; exit 0/1/2
python -m hlmr show  PROOF.JSON   # pretty-print Fitch style
python -m hlmr demo  [NAME]       # run a built-in demo (omit NAME to list)
python -m hlmr repl  [--no-log]   # open interactive REPL
```

---

## Run the test suite

```powershell
# Fast (~90s)
pytest

# With coverage
pytest --cov=src/hlmr --cov-report=term-missing
```

614 tests. Coverage targets: ≥95% kernel and unify, ≥85% renderer and log,
≥70% parser and REPL.

## Lint

```powershell
ruff check src/hlmr
```

---

## Project structure

```
prd.md                          Canonical strategic spec, v4 (read first)
prd_milestone_0.md              M0 spec — kernel and IR (shipped)
prd_milestone_1.md              M1 spec — KB, unification, manual SLD, REPL (shipped)
prd_milestone_2.md              M2 spec — arithmetic and dispatch (in progress)
docs/strategic_direction.md     Long-term theory-growth vision (informs M3+)

src/hlmr/
  ir/                  Frozen-dataclass formula/proof types + JSON serialisation
  kernel/              Trusted proof checker (22 ND rules; arithEval lands in M2)
    ARITH_EVAL_DESIGN.md         M2 — Opus 4.7 design for the new kernel rule
  unify/               Robinson unification with occurs check
  solve/               SLD resolution engine + SLD-to-Fitch renderer
    RENDER_DESIGN.md             M1 renderer (shipped)
    RENDER_M2_DESIGN.md          M2 renderer extension — Opus 4.7 design
  dispatch/            (M2) Constraint classifier and solver router
    DISPATCH_DESIGN.md           M2 dispatcher — Opus 4.7 design
  solvers/             (M2) Z3 and SymPy bridges
  parse/               Lark-based clause and query parser
  repl/                Interactive REPL (prompt_toolkit)
  log/                 JSONL session recorder
  demos.py             Four canonical M1 demo functions
  cli.py               argparse entry point

tests/                 pytest + hypothesis test suites
examples/m1/           Four .pl knowledge-base files for the demos
proofs/m0/             16 example M0 proofs (13 valid + 3 deliberately broken)
proofs/m1/             30 fixtures: 4 demo outputs + 26 hardening fixtures
corpus/                Logged sessions (gitignored)
```

Hard structural rules, enforced by tests:

- `kernel/` imports only from `ir/` and stdlib.
- No module replicates ND rule logic. The kernel is the only place rule
  semantics live.
- From M2 onwards: `solvers/` is the only place Z3 and SymPy are imported.
  Other modules go through its interface.
- `theory/`, `conjecture/`, `countermodel/`, `search/`, `growth/` (all M3+)
  may construct candidate proofs but never verify them. Only the kernel
  produces verified status.

---

## Roadmap

Full specs: [`prd.md`](prd.md) (canonical, v4) and per-milestone PRDs.
Long-term direction: [`docs/strategic_direction.md`](docs/strategic_direction.md).

| Milestone | Status | Adds |
|---|---|---|
| **M0** | shipped | Kernel (22 ND rules), IR, CLI proof checker |
| **M1** | shipped | Horn-clause KB, unification, manual SLD, ND renderer, REPL, parser, JSONL logging |
| **M2** | spec frozen, design approved, implementation pending | Z3 + SymPy bridges, dispatcher, `arithEval` kernel rule, typed metavariables, six-outcome classification |
| **M3** | spec to write | Theory library with metadata, sort-tagged predicates, typed conjecture generation, countermodel search, automated proof search with library reuse, growth-loop orchestration |
| **M4** | planned | Second growth domain (partial orders) plus full multi-sort decision |
| **M5** | planned | First multi-sort domain (`Point`, `Line`); incidence/betweenness/collinearity |
| **M6+** | optional, deferred | Additional theory seeds: monoids/groups, simple number theory over M2's arithmetic, finite-domain combinatorics, geometry sub-tracks |

Each milestone ships standalone and strictly extends its predecessor. The
kernel changes exactly twice between M0 and M2 (the M1 `Meta` rejection
check and the M2 `arithEval` rule); after M2, any further kernel change
requires explicit design review per `prd.md` §4.

### What M2 adds

Arithmetic predicates (`<`, `>`, `+`, `*`, `=`) over ℤ and ℚ, finite-domain
constraints, and symbolic algebraic equations dispatched to SymPy. The
dispatcher classifies each goal independently — KB clauses go through the
M1 SLD path unchanged; arithmetic goals route to Z3 or SymPy; anything
else rejects as `OutsideFragment`. Witnesses are verified by the kernel
through `arithEval` (ground evaluation), never by translating Z3's
internal proof calculus.

### What M3 adds — the theory growth loop

M3 is where the strategic direction becomes demonstrable. Starting from
the three equivalence-relation axioms, the system generates typed
conjectures, filters trivial / duplicate / ill-typed ones, refutes false
ones via countermodel search, attempts proof on the survivors, and admits
only kernel-checked theorems to a growing library. The success signal is
not "we proved 12 theorems" but "theorem 12 used theorem 7 used theorem 3,
and the average proof length dropped after lemma reuse kicked in." That
is growth.

The invariant that makes this whole approach work:

> **Only kernel-checked proofs create new theorems.** Search may be wrong,
> incomplete, biased, or flat-out hallucinatory. None of that admits a
> single false theorem to the library.

### What HLMR is not

Restating, because scope discipline is load-bearing:

- Not "all of mathematics" — Gödel forbids it for any consistent theory
  strong enough to express arithmetic.
- Not a Mathlib clone or Lean replacement.
- Not a frontier neural prover. No transformer, no learned tactic policy
  at the foundation level. An optional small ranker may earn its place
  much later (gated on logged-corpus volume), but the system must work
  fully without it.
- Not an automated theorem prover for unrestricted math. The fragment is
  bounded by the M0–M2 architectural commitments.
- Not brute-force conjecture discovery. Conjectures are generated through
  structured templates and informed recombination, never unstructured
  enumeration.

If a feature can only be justified by appeal to one of the above, push back.
