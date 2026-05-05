# HLMR M1 — Corpus and Hardening (supplementary)

**Status:** Draft v1
**Supplements:** `prd.md` (canonical), `prd_milestone_1.md` (M1 spec). Do
not contradict either.
**Last updated:** 2026-05-04
**Predecessor:** M1 — see `prd_milestone_1.md`. M1 must already be
shipped and green (≥614 tests passing, all coverage targets in M1
§12.2 met).
**Successor:** M2 — see `prd_milestone_2.md`. This pass exists
specifically to lay groundwork for M2's schema bump and dispatcher
integration.

---

## 0. Pre-flight check — read this first, every session

**Before writing any code, state which Claude model you are running as.**

- **Claude Sonnet 4.6** — implements this entire pass. No Opus design
  is required. The renderer was designed once in M1
  (`src/hlmr/solve/RENDER_DESIGN.md`); this pass tests the existing
  algorithm harder rather than redesigning it.

If you find yourself reaching for a kernel change, an IR change, or a
renderer redesign mid-implementation: **stop**. None of those are in
scope here. Ask the user before proceeding.

**Verify M1 is in place before starting:**

1. State your model.
2. Confirm the M1 module layout from `prd_milestone_1.md` §6 exists.
3. Run the full M1 test suite: `pytest tests/ -q`. All M1 tests must
   pass (614+).
4. Run the four M1 demos and confirm they still produce
   kernel-verified proofs:
   ```
   python -m hlmr demo syllogism
   python -m hlmr demo kinship
   python -m hlmr demo finite_puzzle
   python -m hlmr demo peano_even
   ```
5. Read this entire document before writing any code.
6. Then propose the implementation order to the user.

**Do-not-invent rule.** Do not claim a command succeeded without
showing its output. Do not claim a test passed without running it.
Do not claim a fixture exists without listing the directory.

---

## 1. Executive summary

This pass does two things, both before M2 implementation begins:

1. **Generate a frozen M1 proof corpus.** ~26 new proof JSONs covering
   IR shapes the four canonical demos don't reach: deeper SLD chains,
   Peano arithmetic via successor structure, capture-avoidance stress,
   multi-meta queries, and trivial-edge KBs. The corpus is checked in
   under `proofs/m1/` and becomes the regression target for M2's v1→v2
   schema migration.
2. **Add adversarial property tests** on the M1 components most
   likely to harbour latent bugs: the renderer (per `prd_milestone_1.md`
   §13's "kernel-passing but logically wrong proofs" risk), the
   unifier's occurs check, and the capture-avoidance machinery in
   clause renaming-apart.

This is not a milestone. There is no kernel change. There is no IR
change. There is no new module. The deliverable is fixtures and tests.

---

## 2. Why this matters before M2

Three reasons, in order of leverage:

**Schema bump regression target.** `prd_milestone_2.md` §6.3 bumps the
proof JSON schema from v1 to v2 (typed metas, tightened `Const`,
explicit `value_type` tags). The Risks section in that PRD calls out
"Schema v1/v2 deserialisation drift" with mitigation:

> round-trip test that loads each of `proofs/m0/*.json` and
> `proofs/m1/*.json` under M2 and asserts the resulting IR matches
> what M1 produces from the same input.

That mitigation only works if `proofs/m1/` is *rich*. Four demos is
thin. A bug in M2's deserialiser that only manifests on, say, deeply
nested `Func(s, ...)` chains with `Const(int)` leaves at the bottom
will pass the four-demo regression and fail in production. This pass
fixes that.

**Renderer is the M1 component with the highest latent risk.** The
M1 PRD explicitly flags this: the kernel checks individual rule
applications, not theorem identity, so a buggy renderer can produce
proofs that *check* but prove the wrong thing. The four demos are
hand-curated; they don't probe the algorithm adversarially.

**Capture-avoidance is silent when broken.** Variable renaming-apart
is the kind of code that works correctly until it doesn't, and when
it doesn't, the failure mode is a unifier returning the wrong
substitution rather than an error. A small dedicated stress test is
cheap insurance.

---

## 3. Scope

### 3.1 In scope

- ~26 new proof JSONs under `proofs/m1/`
- ~6 new example knowledge bases under `examples/m1/`
- 4–5 new test files under `tests/`
- A regenerate command (`python -m hlmr regenerate-corpus`) that
  rebuilds every proof in `proofs/m1/` from its source `.pl` and
  picker script, so the corpus can be refreshed when something
  legitimate changes
- A short README at `proofs/m1/README.md` listing every fixture and
  what it exercises

### 3.2 Out of scope

- Any kernel change. The M1 PRD's `Meta` rejection (§5.3) is the only
  M1 kernel change ever; this pass adds nothing.
- Any IR change. No new term types, no new formula types.
- Any new module under `src/hlmr/`. Test files only.
- M2 features: no arithmetic predicates (`<`, `>`, `+`, `*`), no
  typed metas, no dispatcher, no solver bridges, no Z3, no SymPy.
  Strict M1 fragment per `prd_milestone_1.md` §3.1.
- Refactoring existing M1 code "to make it easier to test." If a
  test is hard to write because the code is awkward, note it for
  M2; do not refactor.
- Performance work.
- Documentation beyond the corpus README.
- Adding `negation`, `cut`, or any non-Horn extension as a fixture.

### 3.3 Hard fragment boundary

Every fixture's `.pl` must parse and solve using only:

- Horn clauses (head plus zero or more positive body literals)
- Logical variables (`Uppercase` or `_lead`)
- Metavariables in queries only (`?Uppercase`)
- Predicate names that are alphanumeric + underscore
- Constants that are alphanumeric + underscore (or quoted strings if
  the parser supports them — check first)

If a fixture uses any operator atom (`<`, `>`, `+`, `=`, etc. in
operator position) it is in M2 territory and must be removed. The
predicate name `lt` is fine because it's a regular predicate; the
operator `<` is not.

---

## 4. The corpus to generate

Each fixture below specifies the KB, the query, and the expected
witness or shape requirement. The PRD does not pre-specify proof
line counts — those fall out of the M1 renderer's existing algorithm.
Each generated proof must kernel-verify and its final line must equal
the instantiated query (the M1 §13 cheap end-to-end soundness check).

Proof JSONs follow the existing M1 naming convention:
`<fixture-group>_<short-description>.json`. Each is generated by a
small driver script under `scripts/m1_corpus/` that loads the KB,
runs `manual_solve` with a programmatic picker, and writes the JSON.

### 4.1 Kinship — extend existing (4 new, 5 total)

KB extended in `examples/m1/kinship_extended.pl` with a chain at
least 6 deep so a recursive `ancestor` query has somewhere to go.

| File | Query | Expected | Shape requirement |
|---|---|---|---|
| existing | `?- ancestor(?X, alice).` | `?X = bob` | one resolution step |
| `kinship_deep.json` | `?- ancestor(?X, alice).` | `?X = carol` | requires recursive `ancestor_2` clause, SLD depth ≥ 4 |
| `kinship_first_child.json` | `?- parent(alice, ?Y).` | first child | single fact lookup, no body |
| `kinship_two_metas.json` | `?- ancestor(?X, ?Y).` | first pair | both metas resolve from one resolution chain |
| `kinship_chain6.json` | `?- ancestor(?Top, leaf6).` | top of 6-deep chain | SLD depth ≥ 6, exercises renaming-apart over a long chain |

### 4.2 Peano even — extend existing (3 new, 4 total)

KB unchanged from M1 demo.

| File | Query | Expected | Shape |
|---|---|---|---|
| existing | `?- even(s(s(s(s(0))))).` | proven | depth-2 SLD |
| `peano_even_6.json` | `?- even(s(s(s(s(s(s(0))))))).` | proven | depth-3 SLD |
| `peano_even_8.json` | `?- even(s(s(s(s(s(s(s(s(0))))))))).` | proven | depth-4 SLD |
| `peano_even_find_first.json` | `?- even(?N).` | `?N = 0` | trivial single-step (picker picks `even_zero`) |

### 4.3 Peano plus — new (5 new fixtures, new `examples/m1/peano_plus.pl`)

```prolog
% Peano addition. plus(A, B, C) means A + B = C.
plus(0, Y, Y).
plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
```

Successor structure only — this is not arithmetic. The renderer
treats `s/1` as a regular function symbol.

| File | Query | Expected witness |
|---|---|---|
| `peano_plus_2_2.json` | `?- plus(s(s(0)), s(s(0)), ?R).` | `?R = s(s(s(s(0))))` |
| `peano_plus_3_2.json` | `?- plus(s(s(s(0))), s(s(0)), ?R).` | `?R = s(s(s(s(s(0)))))` |
| `peano_plus_find_b.json` | `?- plus(0, ?B, s(s(s(0)))).` | `?B = s(s(s(0)))` (immediate) |
| `peano_plus_find_a.json` | `?- plus(?A, s(s(0)), s(s(s(s(0))))).` | `?A = s(s(0))` (requires recursive descent) |
| `peano_plus_5.json` | `?- plus(s(0), s(s(s(s(0)))), ?R).` | `?R = s(s(s(s(s(s(0))))))` |

### 4.4 Peano times — new (3 new fixtures, new `examples/m1/peano_times.pl`)

`peano_times.pl` imports the `plus` clauses (or restates them — pick
whichever the parser supports cleanly) and adds:

```prolog
times(0, _, 0).
times(s(X), Y, Z) :- times(X, Y, W), plus(W, Y, Z).
```

| File | Query | Expected witness |
|---|---|---|
| `peano_times_2_2.json` | `?- times(s(s(0)), s(s(0)), ?R).` | `?R = s(s(s(s(0))))` |
| `peano_times_2_3.json` | `?- times(s(s(0)), s(s(s(0))), ?R).` | `?R = s(s(s(s(s(s(0))))))` |
| `peano_times_3_2.json` | `?- times(s(s(s(0))), s(s(0)), ?R).` | `?R = s(s(s(s(s(s(0))))))` |

These produce the deepest SLD chains in the corpus — useful for
stressing both the renderer and the JSON serialiser on substantial
nested-`Func` shapes.

### 4.5 Peano lt — new (2 new fixtures, new `examples/m1/peano_lt.pl`)

```prolog
% Structural less-than over Peano naturals. NOT arithmetic.
lt(0, s(_)).
lt(s(X), s(Y)) :- lt(X, Y).
```

| File | Query | Expected |
|---|---|---|
| `peano_lt_2_4.json` | `?- lt(s(s(0)), s(s(s(s(0))))).` | proven |
| `peano_lt_find.json` | `?- lt(?X, s(s(s(0)))).` | `?X = 0` (first witness) |

The wildcard `_` in the first clause stresses the parser/unifier's
handling of fresh anonymous variables across renaming-apart.

### 4.6 Syllogism — extend (2 new, 3 total)

| File | Notes |
|---|---|
| existing | `mortal(socrates)` from `human(socrates)` + `human(X) -> mortal(X)` |
| `syllogism_chained.json` | Three universals chained: `human → mortal`, `mortal → temporal`. Query `?- temporal(socrates).` Exercises multiple `forallE` + `impE` cycles in the renderer. |
| `syllogism_andE.json` | Body with two literals; query forces `andE_L`/`andE_R` premise splitting in the renderer. |

### 4.7 Finite puzzle — extend (1 new, 2 total)

The existing finite-puzzle demo is small. Add one slightly larger:

| File | Notes |
|---|---|
| existing | 3-constraint puzzle |
| `finite_puzzle_4var.json` | 4-variable, 5-constraint puzzle. Still solvable by manual SLD with no arithmetic. |

### 4.8 Capture-avoidance stress — new (3 new, new `examples/m1/capture_stress.pl`)

The whole point: KBs whose clauses share variable names, so
renaming-apart is the only thing standing between correct and
incorrect substitutions.

| File | What it stresses |
|---|---|
| `capture_shared_xy.json` | Two clauses both use `X` and `Y`; query chains through both |
| `capture_meta_clash.json` | A clause uses `X`; query uses `?X`. The renamer must keep these distinct (M1 already separates `Var` from `Meta`, but the test pins this down) |
| `capture_mutual_recursion.json` | Two mutually recursive clauses both using `X, Y, Z`. Each invocation must rename apart from every previous |

These do not need novel KB content — they need adversarial naming.

### 4.9 Edge cases — new (3 new)

| File | What it covers |
|---|---|
| `edge_single_fact.json` | KB is one fact. Query is exactly that fact. Renderer emits Premise + nothing. Smallest valid M1 proof. |
| `edge_query_is_fact.json` | KB has both facts and rules. Query unifies with a fact directly; the rules are never used. |
| `edge_all_meta.json` | Query has every argument as a meta (`?- pred(?A, ?B, ?C).`). All bind from the first matching fact. |

---

## 5. Hardening tests

Five new test files under `tests/`. Each is small and focused.

### 5.1 `test_corpus_regression.py`

Discovers every `*.json` under `proofs/m1/`, loads each one through
the existing kernel `check_proof` API, asserts each proof is
kernel-verified, and asserts the proof's final line matches the
instantiated query recorded in a sidecar metadata file
(`<name>.meta.json`) generated alongside each proof. The sidecar
contains the original query, the expected witness, and a hash of the
KB used to generate the proof.

This is the regression target for M2's v1→v2 schema work. When M2
ships, this test runs against v1 JSONs through the v2 deserialiser
and the same assertions must hold.

Test count: one parametrised test per fixture, ~30 cases total.

### 5.2 `test_corpus_serialisation.py`

For each proof in `proofs/m1/`, load → re-serialise → compare. The
comparison is structural (deserialise both, compare IR equality),
not byte-level — JSON whitespace and key ordering are not part of
the contract.

Catches: serialiser non-idempotency, dict-vs-list serialisation
drift, schema-version write bugs.

### 5.3 `test_renderer_property.py`

Hypothesis property test. Generators produce small KBs and goals
within strict bounds (≤ 5 clauses, ≤ 3 body literals per clause,
predicate arity ≤ 2, term depth ≤ 3, no arithmetic predicates). For
each generated case:

1. Run `manual_solve` with a programmatic picker that always picks
   the first candidate clause.
2. If solving succeeds, render the proof.
3. Assert the rendered proof passes `check_proof`.
4. Assert the proof's final line equals the instantiated query.

If solving fails (no clause matches, occurs check fires, etc.) the
test passes that case vacuously — this is a one-sided property.

Settings: at least 200 examples per CI run, deadline=None (the
renderer can be slow on adversarial inputs but slow is not wrong).

This test is the one most likely to find a real bug. It is also the
one most likely to find a Hypothesis quirk; if it does, shrink to
the minimal failing case and ask before patching.

### 5.4 `test_unify_adversarial.py`

Three groups:

- **Deep occurs check.** `?X` unified with `f(f(f(...?X)))` at depths
  1, 5, 50, 500. All return None. Hypothesis: `unify(?X, t)` returns
  None whenever `?X` is structurally inside `t`.
- **Capture-avoidance with adversarial names.** Variables named `X`,
  `X_1`, `X_renamed`, `?X` interspersed; assert the unifier keeps
  them distinct.
- **Substitution composition associativity.** Random small
  substitutions over a fixed term universe; assert
  `apply(compose(s1, compose(s2, s3)), t) == apply(compose(compose(s1, s2), s3), t)`
  on closed terms.

### 5.5 `test_capture_avoidance.py`

Integration-level tests using the three `capture_*` fixtures from
§4.8. Assert that for each, manual_solve with a fixed picker script
produces the substitution recorded in the sidecar metadata. If the
renamer is broken, the substitution will be subtly wrong (e.g. two
metas bind to the same constant when they shouldn't).

---

## 6. New file layout

```
examples/m1/
├── kinship.pl                  EXISTING
├── kinship_extended.pl         NEW — adds 6-deep ancestor chain
├── peano_even.pl               EXISTING
├── peano_plus.pl               NEW
├── peano_times.pl              NEW
├── peano_lt.pl                 NEW
├── syllogism.pl                EXISTING
├── syllogism_chained.pl        NEW
├── finite_puzzle.pl            EXISTING
├── finite_puzzle_4var.pl       NEW
└── capture_stress.pl           NEW

proofs/m1/
├── README.md                   NEW — fixture index
├── kinship.json                EXISTING
├── kinship_deep.json           NEW
├── kinship_first_child.json    NEW
├── kinship_two_metas.json      NEW
├── kinship_chain6.json         NEW
├── peano_even.json             EXISTING
├── peano_even_6.json           NEW
├── peano_even_8.json           NEW
├── peano_even_find_first.json  NEW
├── peano_plus_2_2.json         NEW
├── peano_plus_3_2.json         NEW
├── peano_plus_find_b.json      NEW
├── peano_plus_find_a.json      NEW
├── peano_plus_5.json           NEW
├── peano_times_2_2.json        NEW
├── peano_times_2_3.json        NEW
├── peano_times_3_2.json        NEW
├── peano_lt_2_4.json           NEW
├── peano_lt_find.json          NEW
├── syllogism.json              EXISTING
├── syllogism_chained.json      NEW
├── syllogism_andE.json         NEW
├── finite_puzzle.json          EXISTING
├── finite_puzzle_4var.json     NEW
├── capture_shared_xy.json      NEW
├── capture_meta_clash.json     NEW
├── capture_mutual_recursion.json NEW
├── edge_single_fact.json       NEW
├── edge_query_is_fact.json     NEW
├── edge_all_meta.json          NEW
└── *.meta.json                 NEW — sidecar metadata, one per proof

scripts/m1_corpus/
├── __init__.py                 NEW
├── regenerate.py               NEW — entrypoint for `python -m hlmr regenerate-corpus`
├── drivers/                    NEW — one driver per fixture group
│   ├── kinship.py
│   ├── peano_even.py
│   ├── peano_plus.py
│   ├── peano_times.py
│   ├── peano_lt.py
│   ├── syllogism.py
│   ├── finite_puzzle.py
│   ├── capture.py
│   └── edge.py

tests/
├── test_corpus_regression.py       NEW
├── test_corpus_serialisation.py    NEW
├── test_renderer_property.py       NEW
├── test_unify_adversarial.py       NEW
└── test_capture_avoidance.py       NEW
```

The `regenerate.py` entrypoint is plumbed into `cli.py` as a new
subcommand. It walks each driver, generates the proof + sidecar, and
writes both. Running it twice with no code changes produces no diff
(deterministic — drivers use fixed pickers, not random). The driver
modules are not test code; they are corpus-generation code.

---

## 7. Model selection

**Sonnet 4.6 throughout.** Every part of this pass is mechanical:
write fixtures, write drivers that exercise the existing
`manual_solve` API, write tests that exercise the existing kernel
and serialiser. No design work, no module boundaries, no kernel
trust-boundary changes.

If during implementation a fixture turns out to require something
not in M1 — for instance, an operator atom that the parser doesn't
accept, or a query shape the renderer can't handle — **stop**. Do
not work around it. That is a finding for M2's risk register, not a
problem for this pass to solve.

If a property test finds a real bug in the renderer or unifier:
**stop and ask the user**. A renderer bug is significant. The fix
may be small or may want Opus design input. Do not patch silently.

---

## 8. Definition of done

This pass is done when **all** of these hold:

1. All 26 new fixtures listed in §4 exist under `proofs/m1/` and
   each has a sidecar `*.meta.json`.
2. All four existing M1 demo proofs are also present in
   `proofs/m1/` (regenerate them through the same driver pipeline so
   the format is uniform).
3. `python -m hlmr regenerate-corpus` runs idempotently — running
   it twice produces no `git diff`.
4. All five new test files pass:
   - `test_corpus_regression.py` (~30 parametrised cases)
   - `test_corpus_serialisation.py` (~30 parametrised cases)
   - `test_renderer_property.py` (≥200 Hypothesis examples)
   - `test_unify_adversarial.py`
   - `test_capture_avoidance.py`
5. All existing M0 + M1 tests still green. No regressions.
6. `proofs/m1/README.md` lists every fixture, what it queries, what
   it exercises (one short line each).
7. The kernel still has zero imports outside `ir/` and stdlib.
   `test_kernel_isolation.py` still passes.
8. Coverage targets from `prd_milestone_1.md` §12.2 are still met
   or exceeded. (Coverage on the renderer and unifier should
   *increase* given the new tests.)
9. README in the repo root has a one-line pointer to the corpus
   under a "M1 hardening" subsection.

---

## 9. Risks

**Corpus drift.** A genuine bug found by `test_renderer_property.py`
gets fixed; the fix changes how some proofs render; the saved JSONs
no longer match. Mitigation: the regenerate command exists for
exactly this case. Document it in `proofs/m1/README.md`. Treat
corpus regeneration as a deliberate, reviewed step — never blanket
`git add proofs/m1/`.

**Property test flakiness.** Hypothesis can produce inputs that hit
slow renderer paths and time out under default deadlines. Mitigation:
`deadline=None` plus `max_examples=200` on the property test. If a
single shrink shows a 30-second case, that's a finding worth
investigating — not silenced with `@settings(deadline=60000)`.

**Scope creep into M2.** Someone adds a fixture that requires `+` in
operator position, or `<` between integers, or a typed meta.
Mitigation: §3.3 lists the hard fragment boundary. Any fixture
using a banned shape gets removed at review.

**Driver code quietly diverges from M1's user-facing API.** If a
driver calls a private SLD function rather than `manual_solve`, it's
testing a different path than the REPL uses. Mitigation: every
driver goes through `manual_solve` from `solve/__init__.py`. No
private imports.

**False sense of security.** A fully green corpus does not prove the
renderer is correct — it proves the renderer is correct *on this
corpus*. Mitigation: this is what the property test is for.
Together they cover more ground than either alone, but neither
constitutes a soundness proof. The kernel remains the trust
boundary.

**Sidecar metadata becoming a second source of truth that drifts.**
The `*.meta.json` files contain the expected witness and KB hash;
if these are hand-edited and the regenerate command isn't re-run,
the regression test will pass against the wrong target. Mitigation:
the regenerate command writes both the proof and the sidecar in
lockstep. Hand-editing the sidecar is forbidden by the corpus README.

---

## 10. Quick reference (Windows / PowerShell)

```powershell
# Activate venv
.\env_hlmr\Scripts\Activate.ps1

# Generate the corpus (idempotent)
python -m hlmr regenerate-corpus

# Run the new tests in isolation
pytest tests/test_corpus_regression.py tests/test_corpus_serialisation.py `
       tests/test_renderer_property.py tests/test_unify_adversarial.py `
       tests/test_capture_avoidance.py -v

# Run the full suite (M0 + M1 + this pass)
pytest tests/ -q

# Re-check a single fixture through the kernel
python -m hlmr check proofs/m1/peano_times_2_3.json

# Pretty-print a fixture
python -m hlmr show proofs/m1/kinship_chain6.json
```

That is the full hardening pass. After it lands, M2 implementation
can begin against `prd_milestone_2.md` §0 with a richer regression
target underneath it.
