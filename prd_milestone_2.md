# HLMR Milestone 2 — Arithmetic and Dispatch

**Status:** Draft v2 (revised after Opus 4.7 consistency review)
**Supplements:** `prd.md` (canonical project spec, do not contradict)
**Last updated:** 2026-05-04
**Predecessor milestone:** M1 — see `prd_milestone_1.md`. M2 work
should not begin until M1 is complete and its test suite is green
(≥614 tests passing, all PRD §12.2 coverage targets met).

---

## 0. Pre-flight check — read this first, every session

**Before writing any code, state which Claude model you are running as.**
Three parts of M2 are gated on Opus 4.7 design and the rest is Sonnet
4.6 implementation. Implementing the wrong section in the wrong
model produces work that has to be redone.

- **Claude Sonnet 4.6** — implements most of this milestone. Default.
- **Claude Opus 4.7** — required for design work on (a) the new
  kernel rule `arithEval`, (b) the dispatcher, and (c) the renderer
  extension that emits `arithEval` lines. See §13 for the full
  breakdown.

If you are Sonnet 4.6 and you reach a section marked
`[REQUIRES OPUS 4.7 — DESIGN]`, **stop and ask the user to switch
models for that section**. Do not proceed by guessing the design.

If you are Opus 4.7 working on a `[SONNET 4.6 — IMPLEMENTATION]`
section, that's fine but wasteful — the user can downgrade once the
design is locked.

**Verify M1 is in place before starting M2:**

1. State your model.
2. Confirm `src/hlmr/solve/`, `src/hlmr/parse/`, `src/hlmr/repl/`,
   `src/hlmr/log/` exist and contain the modules listed in
   `prd_milestone_1.md` §6.
3. Run the M1 test suite: `pytest tests/ -q`. All M1 tests must
   pass (614+). If they don't, M2 work is blocked until M1 is
   fixed.
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
Do not claim a module exists without listing the directory.

---

## 1. Executive summary

Milestone 2 adds arithmetic to HLMR: linear arithmetic over ℤ and ℚ,
finite-domain constraints, and symbolic algebraic equations. Goals
that mix logical inference with arithmetic — the §2 motivating
example in `prd.md` — become solvable end-to-end with kernel-verified
proofs.

The differentiating capability: a query like
`?- prime(?P), greater_than(?P, 2), less_than(?P, 6), not_equal(?P, 4).`
runs SLD over the KB-defined `prime` predicate while the inequality
constraints dispatch to Z3, which finds the witness `?P = 5`. The
witness is then verified by the kernel via a new ground-arithmetic
evaluation rule, and the system returns a Fitch proof the user can
audit.

What this milestone does not do: automated proof search (M3),
non-linear real arithmetic beyond what SymPy specifically handles,
calculus, geometry, set theory beyond finite sets, theory libraries
of any kind. Those remain explicitly out of scope per `prd.md` §6.2.

---

## 2. How M2 fits

| Milestone | Adds | Demoable on |
|---|---|---|
| **0** | kernel, IR, CLI checker | hand-built proofs verify |
| **1** | KB, unification, manual SLD, ND renderer, REPL, parser, logging | kinship, Zebra, Peano even |
| **2 (this)** | Z3 + SymPy bridges, dispatcher, typed metas, `arithEval` kernel rule | the §2 prime example, `x² − 5x + 6 = 0` |
| **3** | search engine, optional learned suggester | benchmarks (FOLIO, ProofWriter) |

The kernel changes once in M2 — exactly one new rule, `arithEval`,
designed by Opus before any code is written. This is the second
kernel change since M0 (the first being the `Meta` rejection in M1
§5.3). All other kernel rules and infrastructure remain untouched.

The IR gains typed metavariables and a small set of distinguished
arithmetic operator names (no new IR node types). Two new top-level
modules appear: `solvers/` (Z3 and SymPy bridges) and `dispatch/`
(constraint classification and routing). The renderer is extended to
handle arithmetic witnesses — the extension itself is small but
warrants Opus design because it crosses the SLD/dispatcher seam.

---

## 3. Scope

### 3.1 In scope

- Linear arithmetic over ℤ (LIA) and ℚ (LRA)
- Finite-domain constraints (e.g. `?X ∈ {2, 3, 5, 7}`)
- Symbolic algebraic equations dispatched to SymPy (polynomials with
  rational coefficients, real domain, all roots returned)
- Typed metavariables: `Integer`, `Rational`, `FiniteDomain(values)`,
  and `Categorical` (the M1 untyped category, renamed for clarity)
- A dispatcher that classifies each goal and routes it: unification
  for first-order, Z3 for linear arithmetic and finite domains,
  SymPy for symbolic algebraic equations
- Outcome classification: `UniqueSolution`, `MultipleSolutions`,
  `InfinitelyManySolutions`, `NoSolution`, `Underdetermined`,
  `OutsideFragment`
- One new kernel rule: `arithEval`, which verifies ground arithmetic
  atoms (e.g. `5 > 2`, `3 + 4 = 7`) by evaluation
- Renderer extension for arithmetic witnesses — flat depth-0 proofs
  as in M1, with a new emit path for `arithEval` lines
- Multi-goal queries in the parser (already needed for the §2 demo)
- REPL display of new outcome types
- Three new demos exercising the arithmetic path, plus one
  demonstrating honest rejection of out-of-fragment problems

### 3.2 Out of scope

- Automated proof search without a human picking clauses (M3)
- Backtracking through the user's previous picks via the engine (M3)
- Non-linear real arithmetic beyond what SymPy specifically handles
  (e.g. transcendental equations like `2^x + x² = 5`)
- Calculus (derivatives, integrals, limits)
- Geometry, probability theory, set theory beyond finite sets
- Theory libraries (M4+; explicitly deferred per `prd.md` §7.6)
- Multi-sort first-order logic (single sort with typed metas
  suffices)
- Negation-as-failure or any non-Horn extension to KB syntax
- Higher-order predicates
- A new IR term type for arithmetic — arithmetic terms remain `Func`
  with distinguished operator names
- Numerical (floating-point) approximate solutions where exact
  symbolic solving fails — the system returns `OutsideFragment`
  rather than an unverifiable approximation
- Proof reconstruction from Z3's internal proof calculus (Z3 proofs
  are not Fitch ND; translating between them is a research project,
  not part of M2)

### 3.3 Demos that must work by end of M2

The repo includes runnable scripts for each. Failures here are
blockers for M2's definition of done.

1. **The §2 prime example.** KB encodes `prime(2). prime(3). prime(5).
   prime(7).`. Query: `?- prime(?P), greater_than(?P, 2),
   less_than(?P, 6), not_equal(?P, 4).` System returns `?P = 5` with
   a kernel-verified proof. This is the canonical mixed-goal demo.
2. **Quadratic.** SymPy demo: `?- root_of(?X, x^2 - 5*x + 6).`
   System returns `?X ∈ {2, 3}` with each witness kernel-verified by
   substitution. The user picks one or both via the REPL; the proof
   for each chosen witness is rendered.
3. **Linear system.** Z3 demo: `?- plus(?X, ?Y, 10), greater_than(?X, 0),
   less_than(?X, ?Y).` System returns one valid solution; user can
   request more solutions until `unsat`.
4. **`OutsideFragment` rejection.** Query like
   `?- root_of(?X, 2^x + x^2 - 5).` System detects the transcendental
   equation, reports `OutsideFragment` with a clear message, does
   not produce a proof.

The exact line counts and witness orderings produced by the
dispatcher and renderer are not pre-specified in this PRD —
those are Opus design deliverables (§9, §10).

### 3.4 Compatibility with M1 demos

The four M1 demos (`syllogism`, `kinship`, `finite_puzzle`,
`peano_even`) must continue to run unchanged after M2 ships. They
use `Categorical` metavariables (the M1 default) and predicates
that are not in the M2 arithmetic set (§6.2), so the dispatcher
classifies them as `KB` and falls through to M1's SLD path.
`test_demos.py` regression-runs all four after M2 implementation.

---

## 4. Architectural commitments (recap)

These are reproduced from `prd.md` because they constrain M2
directly. Anything contradicting them is wrong by construction.

- **The kernel is the only trusted component.** Z3, SymPy, the
  dispatcher, and any new bridge code can all be buggy without
  compromising soundness, as long as every rendered proof is run
  through the kernel. The kernel changes exactly once in M2 — the
  new `arithEval` rule, designed by Opus.
- **The IR is the single bus.** Typed metas extend the IR; arithmetic
  operators are conventional `Func` names, not new IR types. Every
  module reads and writes IR objects.
- **Soundness over completeness.** The dispatcher may classify a
  problem as `OutsideFragment` even when an external solver could
  in principle handle it. False rejections are acceptable; false
  acceptances (claiming a verified proof when one is invalid) are
  catastrophic.
- **Solver dispatch is explicit, not heuristic.** The dispatcher is
  a classifier with documented rules. Its choice is logged. Solver
  disagreement with the kernel is a development-time crash, never a
  production-time silent failure.
- **Logging from day one.** Every dispatcher decision and every
  solver call goes to the JSONL session log. Schema bumps to v2.
- **No Z3-proof-to-Fitch translation.** Z3 finds witnesses; the
  kernel verifies witnesses; the renderer never consumes Z3's
  internal proof calculus. Same for SymPy.

### 4.1 Non-functional commitments specific to M2

- **Python 3.12+.**
- **PEP 8** throughout. Use `ruff` locally.
- **Type hints required** on every public function and dataclass
  field. Modern syntax (`list[int]`, `X | Y`).
- **Modular and shallow.** No deep wrapper hierarchies. Modules over
  ~600 lines are split.
- **One file = one concept.** Particularly applicable to `solvers/`
  (one bridge file per backend) and `dispatch/` (classification
  separate from routing).
- **No surprise dependencies.** New runtime dependencies for M2 are
  exactly two: `z3-solver` and `sympy`. Anything else needs explicit
  user approval before adding.
- **No kernel changes** other than the §6.4 `arithEval` rule. Any
  proposed change to `src/hlmr/kernel/` requires asking the user
  first.

---

## 5. Architectural decisions locked in

These are decisions taken before implementation begins, separate
from the design content that Opus will produce in §6.4, §9, and §10.
Most come from the empirical exploration in
`scratch/M2_PREP_REPORT.md`.

### 5.1 Settled findings (from prep work)

1. **Witness verification via `arithEval`, not Z3-proof translation.**
   Solvers find witnesses; the kernel verifies them. The renderer
   emits ground arithmetic atoms (e.g. `5 > 2`) with an `arithEval`
   justification, and the kernel evaluates them by computation.
   Z3's internal proof calculus is never translated to Fitch ND.

2. **`solveset` over `solve` in SymPy.** `solveset(expr, var,
   domain)` returns clean set-typed results that map to the M2
   outcome classification. The legacy `solve()` API has quirks
   (the `domain=` kwarg is silently ignored).

3. **Z3 underdetermination requires a second model.** Z3 returns
   `sat` with an arbitrary model when a system is underdetermined.
   The dispatcher detects underdetermination by adding the negation
   of the first model and calling `check()` again.

4. **No floating-point in `Const.value`.** Soundness property:
   `arithEval` evaluates with Python's exact arithmetic, and
   admitting `float` would let rounding errors leak into proofs.
   `Const.__post_init__` rejects `float` at construction time.

### 5.2 Tentative decisions for the design phase

These were proposed in the prep report but are not fully settled.
Opus may revise them during the §9 dispatcher design pass; if so,
the decision should be revisited in this PRD before implementation.

- **Z3 Context lifecycle.** Working assumption: one persistent
  context per dispatcher session (tied to the REPL session). The
  alternative — fresh context per call — is simpler but slower.
  Opus picks during §9.
- **SymPy stateless.** Working assumption: no per-session state in
  the SymPy bridge. Confirm during §9.
- **Numerical fallback.** Working assumption: transcendentals are
  `OutsideFragment`. The system does not fall back to `nsolve` for
  approximate roots. Confirm during §9.

---

## 6. IR extensions

Three additions. The rest of `ir/` is unchanged from M1.

### 6.1 Typed metavariables — extend `src/hlmr/ir/formula.py`

The current `Meta(name)` class becomes `Meta(name, kind)`, where
`kind` is one of:

```python
@dataclass(frozen=True)
class MetaKind:
    """Sealed base class for metavariable kinds."""

@dataclass(frozen=True)
class Categorical(MetaKind):
    """The M1 untyped category. Solvable only by unification."""

@dataclass(frozen=True)
class Integer(MetaKind):
    """An integer-valued unknown. Solvable by unification or Z3
    (LIA)."""

@dataclass(frozen=True)
class Rational(MetaKind):
    """A rational-valued unknown. Solvable by unification or Z3
    (LRA), or SymPy."""

@dataclass(frozen=True)
class FiniteDomain(MetaKind):
    """An unknown ranging over a finite set of constants."""
    values: tuple[Const, ...]
```

The kind field has a default of `Categorical()`, so all M1 code
that constructs `Meta(name)` continues to compile and behave
identically. M1 tests, M1 proof JSONs, and the four M1 demos
continue to pass without modification.

The kind is metadata for the dispatcher. Unification itself ignores
kind — `unify(Meta("?X", Integer()), Meta("?Y", Categorical()))`
succeeds and produces `{"?X": Meta("?Y", Categorical())}` (or the
symmetric binding). The dispatcher reads kinds to decide routing.

**Existing `meta.py` re-export shim.** The file `src/hlmr/ir/meta.py`
exists today as a shim (`from hlmr.ir.formula import Meta`). It
remains; it continues to re-export the now-extended `Meta` class.
The shim does not need modification.

**Serialisation contract.** The JSON serialiser at
`serialise.py` produces `Meta` records of shape
`{"_type": "Meta", "name": "...", "kind": {...}}`. The deserialiser
reads `kind` if present and falls back to `Categorical()` if absent
(for backward compatibility with v1 proof JSONs). See §6.3 for the
schema-version policy.

### 6.2 Arithmetic operator names — convention, not type

Distinguished `Func` names that the dispatcher recognises as
arithmetic:

| Name | Arity | Meaning |
|---|---|---|
| `+` | 2 | Addition |
| `-` | 2 | Subtraction (or unary negation when arity 1) |
| `*` | 2 | Multiplication |
| `/` | 2 | Division (rational) |
| `^` | 2 | Power (integer exponent only in M2) |

And distinguished `Atom` predicate names:

| Name | Arity | Meaning |
|---|---|---|
| `<`, `<=`, `>`, `>=` | 2 | Inequalities |
| `!=` | 2 | Disequality (Equals's negation; `=` itself uses the `Equals` IR node) |
| `plus`, `minus`, `times`, `divides` | 3 | Predicate forms (e.g. `plus(2, 3, 5)` for `2+3=5`) |
| `root_of` | 2 | `root_of(X, p)` means `X` is a root of polynomial `p` |

The parser recognises these names. The dispatcher routes them. The
kernel's `arithEval` rule (designed in §6.4) checks ground instances
of them.

This is convention, not a new IR type. `Func("+", (Const(2),
Const(3)))` represents `2 + 3` and the dispatcher knows the name `+`
is arithmetic. Anything *not* on the lists above is treated as a
regular Horn-clause predicate.

The exact subset of these operators that `arithEval` accepts is
fixed during §6.4 design. Operators in the table that don't appear
in §6.4's evaluable set are accepted by the parser and routable by
the dispatcher but not provable by the kernel — the dispatcher must
classify their use as `OutsideFragment`.

### 6.3 Numeric constants — tighten `Const.value`

`Const.value` is currently typed as `object` (anything goes). M0/M1
code already constructs `Const(int)` for Peano demos and similar.

M2 **tightens** the type signature:

```python
@dataclass(frozen=True)
class Const(Term):
    value: str | int | Fraction

    def __post_init__(self) -> None:
        if isinstance(self.value, bool):
            raise TypeError("Const cannot wrap bool (Python bools are ints)")
        if isinstance(self.value, float):
            raise TypeError("Const cannot wrap float (use Fraction for exact rationals)")
```

The `bool` rejection prevents `Const(True)` being silently treated
as `Const(1)` — an old Python pitfall. The `float` rejection is the
soundness property from §5.1.

**JSON schema bump from v1 to v2.** The existing serialiser at
`serialise.py:_proof_from_dict` checks `version == SCHEMA_VERSION`
strictly and raises on mismatch. M2 loosens this to accept both v1
and v2:

```python
if version not in (1, 2):
    raise ValueError(f"Unsupported schema version: {version}")
```

When reading v1, missing `kind` fields on `Meta` records default to
`Categorical()`. Numeric `Const` records in v2 carry an explicit
type tag (`"value_type": "int"|"fraction"|"str"`) so deserialisation
is unambiguous. The schema-version writer emits v2 always.

### 6.4 The `arithEval` kernel rule — `[REQUIRES OPUS 4.7 — DESIGN]`

This is the only kernel change permitted in M2. Before any
implementation begins, Opus 4.7 produces a design document at
`src/hlmr/kernel/ARITH_EVAL_DESIGN.md`. That document is the
authoritative spec for `arithEval`; this PRD defers to it.

The deliverable must contain, at minimum:

- **Exact rule semantics.** When does `arithEval` accept? What
  ground arithmetic atoms qualify? What is the relationship between
  the rule's input formula and its conclusion?
- **The set of ground evaluable atoms.** A precise enumeration:
  inequalities of literal numerics; arithmetic equations of literal
  numerics; what about `Equals` whose sides are arithmetic
  expressions; what about the predicate forms (`plus(2, 3, 5)`).
- **The evaluation algorithm.** Recursive descent over `Func` and
  `Const`. Behaviour on non-arithmetic `Func`, on `Var`, on `Meta`
  (the latter is in principle ruled out by the M1 §5.3
  `UnresolvedMeta` check, but the rule should not assume that and
  should reject independently).
- **Soundness argument.** Why does this rule preserve the kernel's
  soundness property? Specifically, the relationship between
  Python's integer/`Fraction` arithmetic and the formal arithmetic
  the rule claims to evaluate. Edge cases — extreme integer
  magnitudes, division by zero, integer-vs-rational coercion.
  `float` is excluded by §6.3 and by `Const.__post_init__`; the
  argument should still cover what happens if a `float` somehow
  appears.
- **Failure modes.** What does the rule reject, with what error
  type? At minimum: `MalformedArithmetic` for non-evaluable atoms;
  `EvaluationFalse` for atoms that evaluate to false (e.g. a proof
  line claims `2 > 3` and `arithEval` rejects it).
- **API surface.** What does the rule's `RuleApp.extra` field
  contain? The kernel rule pattern allows a payload; the design
  decides what (if anything) goes there. Likely nothing — the
  rule's input is just the line's formula.
- **Worked examples.** At minimum: `5 > 2` accepts; `2 > 5` rejects
  with `EvaluationFalse`; `Equals(Func("+", (Const(3), Const(4))),
  Const(7))` accepts; non-ground arithmetic rejects with
  `MalformedArithmetic`; unknown operator rejects.

Once Opus has produced the design doc and the user has approved it,
Sonnet implements `arithEval` as a normal kernel rule following the
M0/M1 pattern in `kernel/rules.py`.

---

## 7. New modules

```
src/hlmr/
├── ir/
│   ├── formula.py             EXTENDED — Meta gets a kind field;
│                              MetaKind hierarchy added; Const
│                              tightened to str | int | Fraction
│   ├── meta.py                UNCHANGED — re-export shim still valid
│   └── serialise.py           EXTENDED — schema v2 reader/writer
├── kernel/
│   ├── ARITH_EVAL_DESIGN.md   NEW (§6.4) [Opus]
│   ├── rules.py               EXTENDED — _arithEval rule added
│   └── errors.py              EXTENDED — MalformedArithmetic,
│                              EvaluationFalse error types
├── solvers/                   NEW — §8
│   ├── __init__.py
│   ├── z3_bridge.py           Z3 wrapper
│   └── sympy_bridge.py        SymPy wrapper
├── dispatch/                  NEW — §9 [REQUIRES OPUS 4.7 — DESIGN]
│   ├── __init__.py
│   ├── DISPATCH_DESIGN.md     NEW [Opus]
│   ├── classify.py            Constraint classification rules
│   └── route.py               Routing decisions, solver invocation
├── solve/
│   ├── render.py              EXTENDED [REQUIRES OPUS 4.7 — DESIGN]
│   │                          See §10 and RENDER_M2_DESIGN.md
│   ├── RENDER_M2_DESIGN.md    NEW [Opus]
│   ├── sld.py                 EXTENDED — SLDStep gains an optional
│                              "arithmetic origin" marker
│   └── __init__.py            EXTENDED — manual_solve gains an
│                              optional dispatcher parameter
├── parse/
│   ├── grammar.lark           EXTENDED — multi-goal queries,
│                              numeric literals, operator atoms,
│                              typed metas
│   └── parser.py              EXTENDED — same scope
└── repl/
    ├── commands.py            EXTENDED — :solver command;
                               'solver' added to Command.type set
    └── interactive.py         EXTENDED — display new outcome types
```

Module-level model guidance (full breakdown in §13):

| Module | Model | Rationale |
|---|---|---|
| `ir/` extensions | **Sonnet 4.6** | Routine dataclass additions |
| `kernel/ARITH_EVAL_DESIGN.md` | **Opus 4.7** | Soundness boundary |
| `kernel/rules.py` (`_arithEval`) | **Sonnet 4.6** | Implementation against design |
| `solvers/` (both bridges) | **Sonnet 4.6** | Wrapper code; well-trodden |
| `dispatch/DISPATCH_DESIGN.md` | **Opus 4.7** | High-risk classifier |
| `dispatch/` implementation | **Sonnet 4.6** | Implementation against design |
| `solve/RENDER_M2_DESIGN.md` | **Opus 4.7** | Crosses SLD/dispatcher seam |
| `solve/render.py` extension | **Sonnet 4.6** | Implementation against design |
| `solve/sld.py` extension | **Sonnet 4.6** | Add a marker field |
| `solve/__init__.py` (manual_solve) | **Sonnet 4.6** | Threading change |
| Parser/REPL extensions | **Sonnet 4.6** | UI plumbing |

---

## 8. Solver bridges — `src/hlmr/solvers/`

### 8.1 Z3 bridge — `z3_bridge.py`

A thin wrapper exposing a typed, IR-friendly API. The bridge is the
only place in the codebase that imports `z3`. Other modules read
the bridge's enum-typed return values.

The exact public method signatures are decided during the §9
dispatcher design — the bridge's API serves the dispatcher's needs
and shouldn't be specified before those needs are clear. What's
fixed:

- One `Z3Bridge` instance per dispatcher session, holding one
  persistent `z3.Context` (per §5.2's tentative decision).
- All Z3 variables and solver instances pinned to that context.
- Return values are sealed types: `Z3Sat(model)`, `Z3Unsat`,
  `Z3Underdetermined(model, free_vars)`, `Z3Unknown(reason)`. The
  bridge does not interpret these into M2 outcomes — that's the
  dispatcher's job.

### 8.2 SymPy bridge — `sympy_bridge.py`

Same shape: thin wrapper, only place that imports `sympy`,
sealed return types `SymPyFiniteRoots(roots)`, `SymPyNoRealRoots`,
`SymPyConditionSet(reason)`, `SymPyError(message)`. Uses `solveset`,
not `solve` (per §5.1.2).

### 8.3 Tests

- Bridge unit tests with constructed IR inputs and asserted outputs.
- Each return type appears in at least one test.
- Mock-test the dispatcher against fake bridges to verify dispatch
  logic without depending on Z3/SymPy in unit tests.
- Real Z3/SymPy integration tests run as part of the standard suite
  once `z3-solver` and `sympy` are runtime dependencies (per §4.1,
  they are added unconditionally — there is no optional-dependency
  gate).

---

## 9. Dispatcher — `src/hlmr/dispatch/` `[REQUIRES OPUS 4.7 — DESIGN]`

This is the high-risk module of M2. Opus produces
`src/hlmr/dispatch/DISPATCH_DESIGN.md` before any code is written.
This PRD defers to that document for the API and algorithm.

### 9.1 Opus deliverable

The design doc must contain, at minimum:

- **Worked examples for each demo (§3.3).** For each demo, walk
  through the dispatcher's classification of every goal, the
  routing decision, the solver call, the result mapping, and the
  proof-line emission. Hand-trace the §2 prime example end to end.
  Hand-trace the `OutsideFragment` rejection path.
- **The classification algorithm.** Given a goal `Atom | Equals`
  and the current `Substitution`, what does the dispatcher decide?
  Tabulate the rules; be explicit about precedence when a goal
  could in principle route to multiple solvers. Include the
  conservative-default rule: when in doubt, `OutsideFragment`.
- **The mixed-goal seam.** How does SLD interact with dispatch when
  a query mixes KB-resolved goals (e.g. `prime(?P)`) with
  arithmetic-routed goals (e.g. `greater_than(?P, 2)`)? Specify
  the data flow: what does SLD pass to the dispatcher, what does
  the dispatcher return, where do dispatcher-resolved bindings
  enter the SLD substitution, where do arithmetic-witness atoms
  enter the proof history. The current SLD engine in
  `src/hlmr/solve/sld.py` is the starting point; this design fixes
  the integration shape.
- **Outcome handling.** Each of the six outcomes
  (`UniqueSolution`, `MultipleSolutions`,
  `InfinitelyManySolutions`, `NoSolution`, `Underdetermined`,
  `OutsideFragment`) needs a defined behaviour: what the
  dispatcher returns, what the renderer does with it, what the
  REPL displays.
- **Public API.** The full type signatures for `Dispatcher`,
  `DispatchResult` (or whatever shape the design settles on),
  `RouteTarget`, and any helper types. The PRD does not pre-specify
  these types — that's the design's job.
- **Z3 context lifecycle.** Confirm or refine §5.2's tentative
  "one persistent context per dispatcher session" decision.

### 9.2 Tests required (after design)

Per Opus design plus:

- Each of the six outcomes appears in at least one test.
- Each demo runs end-to-end with the dispatcher in the loop.
- Hypothesis property: classification is deterministic given the
  same goal.
- Soundness regression: a hand-built malicious dispatcher (returning
  wrong bindings) is caught by the kernel during witness
  verification. This is the equivalent of M0's
  `99_BAD_*` proofs and M1's renderer kernel-rejection test —
  defense-in-depth coverage that the kernel catches dispatcher
  bugs.

---

## 10. Renderer extension — `src/hlmr/solve/render.py` `[REQUIRES OPUS 4.7 — DESIGN]`

The M1 renderer uses the rule alphabet `{Premise, forallE, andI,
impE}` and is documented in `src/hlmr/solve/RENDER_DESIGN.md`. M2
extends the alphabet with `arithEval` and changes how the renderer
walks the SLD history (steps may be arithmetic-origin rather than
clause-resolution-origin).

This extension is a separate Opus design pass because:

- It crosses the SLD/dispatcher seam (it consumes whatever
  arithmetic-origin marker the dispatcher and SLD agree on in §9).
- It changes the structural shape of the rendered proof for
  arithmetic-bearing queries.
- The same failure mode as M1's renderer applies: a buggy
  extension can produce kernel-passing-but-wrong proofs.

### 10.1 Opus deliverable

`src/hlmr/solve/RENDER_M2_DESIGN.md` containing:

- **Worked examples.** For each of demos 1, 2, 3 in §3.3, the full
  rendered proof, line by line, with rule justifications. The PRD
  does not pre-specify line counts; the design produces them.
- **The extended algorithm.** How the M1 algorithm in
  `RENDER_DESIGN.md` is modified to handle arithmetic-origin
  steps. What changes in the step-tree walk; what changes in
  premise emission; what new emit path is added for `arithEval`
  lines.
- **The SLDStep marker.** What field is added to `SLDStep` (or what
  new step type is introduced) to mark arithmetic origin.
  Coordinated with the §9 dispatcher design so the SLD-side and
  renderer-side definitions match.
- **Edge cases.** Mixed steps where one body atom is arithmetic
  and another is KB-derived. Steps where the dispatcher returns
  multiple witnesses (§9's `MultipleSolutions`).
- **Test strategy.** Per-demo end-to-end (each demo's rendered
  proof passes the kernel and matches the instantiated query in
  its final line). Property tests: the rule alphabet is bounded to
  `{Premise, forallE, andI, impE, arithEval}` and no other rules
  appear; no `Meta` survives in any line.

### 10.2 What does NOT need redesign

The M1 renderer's core loop, premise emission for KB clauses,
and box-depth-0 invariant are unchanged. The extension is additive:
new emit path for arithmetic, new step-marker handling. Modify
`render.py`, do not rewrite it.

---

## 11. Parser extension — `src/hlmr/parse/`

Four additions to the M1 grammar:

1. **Multi-goal queries.** Currently the grammar parses
   `single_query: "?-" literal "."` (one literal per query). The §2
   demo requires `?- g1, g2, g3.` (comma-separated). The grammar
   is extended to accept a comma-separated literal list in query
   position. Output type: `tuple[Atom | Equals, ...]` instead of
   the single `Atom | Equals` from M1. `parse_query` is updated
   accordingly; existing single-literal queries continue to parse
   into a one-element tuple for forward compatibility.
2. **Numeric literals.** `0`, `1`, `42`, `-7`, `3/4` parse as
   `Const(int)` or `Const(Fraction)`. New tokens for integer and
   rational literals.
3. **Operator atoms.** `5 > 2`, `?X + ?Y = 10`, etc. parse as
   `Atom` or `Equals` with the distinguished operator names from
   §6.2. The grammar gains operator-position parsing for the
   binary operators.
4. **Typed metavariables.** Surface syntax for declaring meta
   types: `?X : Integer`, `?X : Rational`, `?X : {2, 3, 5, 7}`.
   The default kind is `Categorical` (M1 behaviour).

Tests: round-trip for each new token, error messages for ambiguous
operator precedence, fixture queries for each demo parse correctly.
M1 parser tests (45 tests in `test_parser.py`) continue to pass.

---

## 12. REPL extension — `src/hlmr/repl/`

Three additions to the M1 REPL.

1. **Outcome display.** Each of the six outcomes from §9 has a
   REPL display format. `UniqueSolution` looks like M1's success.
   `MultipleSolutions` shows all solutions and asks the user which
   to verify. `Underdetermined` shows one example solution with a
   note about the free variables. `OutsideFragment` reports
   honestly that the system can't handle this query, with the
   classification reason.

2. **`:solver` command.** Adds `'solver'` to `Command.type` in
   `repl/commands.py` and the help text. Shows which solver each
   goal in the current query was dispatched to. Useful for
   understanding dispatcher decisions during interactive use.

3. **Logging extension.** The session recorder records dispatcher
   decisions (`dispatch_classify`, `dispatch_route`,
   `solver_call`, `solver_result`). Schema bumps to v2 with
   backward-compatible reading of v1 logs. The schema doc at
   `src/hlmr/log/schema.md` is updated.

`manual_solve`'s public signature is extended:

```python
def manual_solve(
    kb: KnowledgeBase,
    goal: Atom | Equals | tuple[Atom | Equals, ...],
    picker: Callable[[list[Clause], SLDState], int | None],
    dispatcher: Dispatcher | None = None,
) -> tuple[Substitution, Proof] | None:
```

Two changes from M1:

- `goal` accepts a single literal (M1) or a tuple (M2 multi-goal
  queries). Internally it's normalised to a tuple.
- `dispatcher` is optional. When `None`, behaviour is exactly M1's
  (no arithmetic). When provided, arithmetic-flavoured goals route
  to the dispatcher; non-arithmetic goals continue to use the
  picker. The dispatcher decides goal-by-goal, not query-by-query.

M1 callers (the four demos, the existing test suite) pass no
`dispatcher` and continue to work unchanged.

---

## 13. Model selection guide — read before each session

### 13.1 Sonnet 4.6 — default for implementation

Sonnet handles all of:
- IR additions (Meta kind, MetaKind hierarchy, Const tightening,
  schema v2 read/write)
- `kernel/rules.py` `_arithEval` rule **implementation** once Opus
  has produced `ARITH_EVAL_DESIGN.md`
- `solvers/` (both bridges)
- `dispatch/` **implementation** once Opus has produced
  `DISPATCH_DESIGN.md`
- `solve/render.py` extension **implementation** once Opus has
  produced `RENDER_M2_DESIGN.md`
- `solve/sld.py` step-marker extension
- `solve/__init__.py:manual_solve` signature change
- Parser extension (multi-goal, numeric literals, operators,
  typed metas)
- REPL extension (outcome display, `:solver`, logging)
- All test suites
- All demo scripts
- Documentation

### 13.2 Opus 4.7 — required for these specific tasks

**Task A: `arithEval` kernel rule design.** Before any code in
`kernel/rules.py` for the new rule, Opus produces
`src/hlmr/kernel/ARITH_EVAL_DESIGN.md` per §6.4.

**Task B: Dispatcher design.** Before any code in `dispatch/`,
Opus produces `src/hlmr/dispatch/DISPATCH_DESIGN.md` per §9.

**Task C: Renderer extension design.** Before any code in
`solve/render.py` for the M2 extension, Opus produces
`src/hlmr/solve/RENDER_M2_DESIGN.md` per §10. This may run in the
same session as Task B since the two designs are coupled at the
SLD-step-marker boundary.

**Task D: Any new module boundary.** If during implementation a
new module turns out to be needed (something not in §7), Opus
decides whether it belongs and where. One-prompt sanity check.

**Task E: Any IR change beyond §6.** The IR is the bus between
modules; breaking it requires care. If anything beyond typed metas
and `Const` extension needs adding, escalate to Opus.

### 13.3 What to do at a model boundary

If you are Sonnet and you hit `[REQUIRES OPUS 4.7 — DESIGN]`:

> "This section is marked as requiring Opus 4.7 for design. I am
> Sonnet 4.6. Please switch models for this section, or override
> this requirement explicitly in your next message."

Then stop. Do not proceed by guessing.

If you are Opus and you finish a design task, hand off:

> "Design complete in `<path>`. Implementation can proceed in
> Sonnet 4.6."

---

## 14. Definition of done

M2 is done when **all** of these hold:

1. All four demos in §3.3 run end-to-end. Each produces a
   kernel-verified proof (or, for demo 4, an honest
   `OutsideFragment` rejection). Proofs are saved as JSON in
   `proofs/m2/`.
2. The full test suite passes:
   - All M0 tests still green (kernel sound/unsound regression
     suites in `test_kernel_sound.py`, `test_kernel_unsound.py`,
     `test_kernel_coverage.py`).
   - All M1 tests still green, including `test_kernel_isolation.py`
     and `test_kernel_unresolved_meta.py`.
   - New M2 tests covering `solvers/`, `dispatch/`,
     `kernel/_arithEval`, the IR/parser/REPL extensions, and the
     four new demos.
   - New file `tests/test_kernel_arith_eval.py` covers the
     `arithEval` rule's accept/reject paths exhaustively (worked
     examples from §6.4 plus property tests).
3. Coverage targets:
   - Kernel including `_arithEval`: ≥95% (matches M0/M1 floor)
   - `unify/` and `solve/sld.py`: ≥95% (unchanged from M1)
   - `solvers/`: ≥85%
   - `dispatch/`: ≥85%
   - `solve/render.py` after extension: ≥85% (matches M1 floor)
   - Parser, REPL, IR extensions: ≥70% (matches M1 floor)
   - `log/`: ≥85% (unchanged from M1)
4. The kernel still has zero imports outside `ir/` and stdlib.
   `test_kernel_isolation.py` still passes.
5. `python -m hlmr repl` opens an interactive session that handles
   all six outcome types.
6. Every REPL session logs to JSONL with schema v2. v1 logs
   continue to be parseable.
7. README updated for M2: install, run new demos, run REPL with
   arithmetic, pointer to PRD.
8. The `99_BAD_*` demonstration proofs from M0 still fail with
   the same errors. The kernel's `arithEval` rule has its own
   negative tests in `tests/test_kernel_arith_eval.py`: a proof
   line claiming `2 > 5` is rejected; a proof line with non-ground
   arithmetic is rejected; a proof line whose `arithEval`
   formula contains a `Meta` is caught by the M1 §5.3 check
   first; constructing a `Const(3.14)` raises `TypeError`.

---

## 15. Risks

**Dispatcher misclassification.** A non-linear problem misclassified
as linear and routed to Z3, which returns a confident wrong answer.
Mitigation: classification is conservative — anything ambiguous is
`OutsideFragment` rather than guessed. Property tests cover
boundary cases. Soundness backstop: kernel verifies witnesses
independently of how they were found.

**`arithEval` soundness bug.** Python's integer arithmetic differs
from formal arithmetic only on edge cases (Python `int` is
arbitrary-precision; `Fraction` is exact). But: floating-point would
be a soundness disaster. Mitigation: `Const` refuses `float` values
at construction time (§6.3); the `arithEval` design (§6.4) must
explicitly cover what happens if a `float` somehow appears anyway.

**Z3/SymPy disagreement with the kernel.** Z3 returns "X = 5
satisfying X > 2 and X < 6 and X != 4" but the kernel rejects the
rendered proof. Mitigation: kernel is arbiter; disagreements crash
during development, not in production. Bridge round-trip tests.

**Witness verification round-trip failure.** Z3's `?X = 5` becomes
`Const(5)`, but the rendered proof line `5 > 2` doesn't reduce
correctly under `arithEval` because of some IR-encoding mismatch.
Mitigation: bridge code includes a "verify before return" step that
substitutes the witness back into the original constraint and
checks `arithEval` on each resulting ground atom before claiming
success.

**Underdetermined Z3 answers leaking through.** Z3 returns `sat`
for `?X + ?Y = 10` with arbitrary `(10, 0)`; user sees this as
"the" answer when actually any pair sums to 10. Mitigation:
§5.1.3 requires the dispatcher to detect underdetermination via
the add-negation-and-recheck strategy. The `Underdetermined`
outcome is displayed clearly in the REPL.

**Scope creep into non-linear arithmetic.** SymPy can handle a lot;
the temptation to push the boundary is real. Mitigation: the
`OutsideFragment` outcome is first-class. The dispatcher actively
rejects rather than tries.

**Geometry / theory libraries pressure.** As soon as M2 ships,
arithmetic-flavoured problems will tempt the user to ask "can it
do geometry?" The PRD framing (M4+ is theory libraries, deferred)
must be defended. Mitigation: this risk is documented in `prd.md`
§11; M2 implementers should not encode geometric or numerical
domain knowledge in the codebase.

**M1 demo regression under typed Meta.** The Peano even demo
encodes naturals as `Func("s", ...)` and `Const(0)`; the integer
typed-meta path could in principle interfere. Mitigation: §3.4
makes M1 demo regression a hard requirement; the dispatcher
classifies non-arithmetic-operator goals as `KB` and the M1 SLD
path is unchanged.

**Schema v1/v2 deserialisation drift.** Loading old M1 proof JSONs
under M2 must produce structurally-identical IR objects to what
M1 originally created. Mitigation: round-trip test that loads each
of `proofs/m0/*.json` and `proofs/m1/*.json` under M2 and asserts
the resulting IR matches what M1 produces from the same input.

**Model misuse — Sonnet implements `arithEval`, the dispatcher,
or the renderer extension without Opus design.** Result: probably
works for the simplest demo and quietly breaks on the §2 prime
example. Mitigation: §0 and §13 are at the top of this PRD
specifically to make this hard to do accidentally.

---

## 16. Out of scope, for the avoidance of doubt

- Real-valued non-linear arithmetic beyond what SymPy specifically
  handles. (Limit set by the SymPy bridge's own decisions.)
- Calculus, transcendentals, complex analysis, set theory beyond
  finite sets, measure theory. (Not planned for V1.)
- Geometry (any flavour), probability theory, group theory, number
  theory beyond what M2 + a user-provided KB supports. (M4+.)
- Proof reconstruction from Z3's internal proof calculus. (Not
  planned; the witness-verification approach replaces it.)
- Approximate / floating-point answers. (Soundness incompatible.)
- Automated proof search. (M3.)
- Persistent solver state across REPL sessions beyond what the
  log records.
- A new IR term type for arithmetic expressions.
- Any neural component, training, or model-serving infrastructure.

---

## 17. Quick reference — what the user actually does (Windows / PowerShell)

```powershell
# Activate venv
.\env_hlmr\Scripts\Activate.ps1

# Install (M0 + M1 already in place; M2 adds two deps)
pip install -e ".[test]"

# Run new demos (line counts and exact output emerge from
# the dispatcher and renderer designs — see proofs/m2/)
python -m hlmr demo prime_search
python -m hlmr demo quadratic
python -m hlmr demo linear_system
python -m hlmr demo outside_fragment

# Open the REPL with arithmetic enabled
python -m hlmr repl

# In the REPL:
> :load examples/m2/prime_search.pl
Loaded 4 clause(s) from 'examples/m2/prime_search.pl'.
> :query
> ?- prime(?P), greater_than(?P, 2), less_than(?P, 6), not_equal(?P, 4).
[mixed-goal solve session — SLD picks for prime, dispatcher routes inequalities to Z3]
Solved: ?P = 5.
Proof: kernel-verified.
> :show last
[full proof display]
> :solver
prime(?P)            → KB (SLD)
greater_than(?P, 2)  → Z3 (LIA)
less_than(?P, 6)     → Z3 (LIA)
not_equal(?P, 4)     → Z3 (LIA)
> :quit
```

That is the M2 user experience. M3 will add automated search so
the user no longer has to `pick` SLD candidates manually for the
KB portion of mixed-goal queries.
