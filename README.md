# HLMR — Hybrid Logic-Math Reasoner

HLMR is a Python 3.12 interactive theorem prover for first-order logic. It
supports Prolog-style Horn-clause knowledge bases, first-order Robinson
unification, manual SLD resolution (you pick the clauses; the system finds
the bindings), and renders every solved query as a Fitch-style
natural-deduction proof that the trusted kernel verifies.

**Status:** Milestone 1 complete. The system is a working manual theorem prover
over Horn-clause knowledge bases with kernel-verified Fitch-style proofs.
Milestone 2 (arithmetic via Z3 and SymPy) is the next planned increment.

See `prd.md` for the full spec and `prd_milestone_1.md` for M1 details.

---

## What's working

**Milestone 0** — the trusted core:
- Fitch-style natural-deduction proof kernel (22 ND rules)
- CLI proof checker (`hlmr check`) and pretty-printer (`hlmr show`)
- JSON proof format with schema versioning

**Milestone 1** — the manual solver:
- Horn-clause knowledge bases parsed from Prolog-flavoured `.pl` files
- First-order Robinson unification with occurs check
- Manual SLD resolution: you pick each clause; the system binds variables
- SLD-trace-to-Fitch renderer: every solved query becomes a kernel-verified proof
- Interactive REPL with `back` (undo last pick), `abort`, `:load`, `:export`
- JSONL session logging for future training corpus
- Four canonical demos with kernel-verified proof artifacts

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
prd.md                 Canonical strategic spec (read first)
prd_milestone_1.md     M1 spec (KB, unification, manual SLD, REPL, logging)
src/hlmr/
  ir/                  Frozen-dataclass formula/proof types + JSON serialisation
  kernel/              Trusted proof checker (22 ND rules)
  unify/               Robinson unification with occurs check
  solve/               SLD resolution engine + SLD-to-Fitch renderer
  parse/               Lark-based clause and query parser
  repl/                Interactive REPL (prompt_toolkit)
  log/                 JSONL session recorder
  demos.py             Four canonical M1 demo functions
  cli.py               argparse entry point
tests/                 pytest + hypothesis test suites
examples/m1/           Four .pl knowledge-base files for the demos
proofs/m0/             16 example M0 proofs (13 valid + 3 deliberately broken)
proofs/m1/             Four canonical M1 proof outputs (generated by demos)
```

---

## Project status and roadmap

Full specs: [`prd.md`](prd.md) (canonical) and [`prd_milestone_1.md`](prd_milestone_1.md) (M1 details).

| Milestone | Status | Adds |
|---|---|---|
| M0 | **complete** | Kernel, IR, CLI checker |
| M1 | **complete** | KB, unification, manual SLD, REPL, logging |
| M2 | not started | Z3 + SymPy arithmetic bridge, auto-dispatcher |
| M3 | not started | Automated search engine, optional learned ranker |

M2 adds arithmetic predicates (`<`, `>`, `+`, `*`) via a Z3/SymPy bridge,
letting the system handle linear arithmetic and quadratic constraints without
changing the kernel. M3 adds automated proof search so the user no longer
needs to pick every clause manually, plus an optional learned ranker trained
on the M1 session corpus.
