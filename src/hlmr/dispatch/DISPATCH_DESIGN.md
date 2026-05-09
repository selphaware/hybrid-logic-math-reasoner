# `dispatch/` — design

**Status:** Design v1.1 (Opus 4.7). MultipleSolutions partial-contested witness handling clarified; §3.1 and §5.3 now match §12.6 policy. §13.5 alphabet now includes `eqRefl` per RENDER_M2_DESIGN.md §2. No code in this document; pseudocode only.
**Implements:** `prd_milestone_2.md` §9 (Task B in §13.2).
**Target reader:** Sonnet 4.6 implementing against this spec, in `src/hlmr/dispatch/__init__.py`, `src/hlmr/dispatch/classify.py`, and `src/hlmr/dispatch/route.py`.
**Companion designs:** `src/hlmr/kernel/ARITH_EVAL_DESIGN.md` (Task A, v1.1, **approved**); `src/hlmr/solve/RENDER_M2_DESIGN.md` (Task C, this session). All three must be consistent at the SLD-step-marker boundary, the verify-before-return contract, and the contested-content rejection flow.

---

## 1. Purpose

`dispatch/` is the M2 module that classifies each goal in a query and
routes it to the appropriate solver:

- **KB clauses** (M1 SLD path) for first-order Horn-clause predicates.
- **Z3** for ground or near-ground linear arithmetic over ℤ and ℚ,
  finite-domain enumerations, and inequality constraints.
- **SymPy** for symbolic algebraic equations (polynomials with rational
  coefficients, real domain) where multiple roots or
  algebraic-set-typed answers are needed.
- **`OutsideFragment`** for everything the dispatcher cannot handle
  soundly — transcendentals, contested-convention cases like `0^0`,
  unrecognised goal shapes.

Dispatch is **the** high-risk M2 module. Its mistakes do not compromise
soundness (the kernel arbitrates via `arithEval`'s witness verification
step), but they manifest as the dispatcher silently sending a non-linear
problem to Z3 and reporting a confident wrong answer, or failing to
recognise an `OutsideFragment` boundary case. This is why §6.5 (and PRD
§13.2 Task B) mandate Opus design before any code.

**Headline architectural choice.** The dispatcher operates **goal by
goal**, not query by query. For a multi-goal query like `?- prime(?P),
?P > 2, ?P < 6, ?P != 4.`, the dispatcher classifies each of the four
goals independently. KB-routed goals go through M1's `manual_solve`
clause-picker loop unchanged; arithmetic-routed goals are resolved
in-line and produce a `DispatcherResolvedStep` in the SLD history that
the renderer later walks. This matches `prd_milestone_2.md` §12's
specification of `manual_solve` and keeps the M1 SLD path bit-for-bit
unchanged for queries with no arithmetic content.

**Out of scope.** Automated proof search (M3); backtracking through
prior user picks via the engine (M3); proof reconstruction from Z3's
internal proof calculus (never — see §13); approximate / floating
solutions (soundness-incompatible); a new IR term type for arithmetic
(arithmetic operators stay as conventional `Func` names per
`prd_milestone_2.md` §6.2).

---

## 2. Where `dispatch/` sits in the architecture

### 2.1 Module layout

```
src/hlmr/dispatch/
├── __init__.py          # re-exports: Dispatcher, DispatchOutcome,
│                        # RouteTarget, ClassifyDecision, the six outcome
│                        # dataclasses, and the new SLDStep variants
├── DISPATCH_DESIGN.md   # this document
├── classify.py          # pure classification: goal -> RouteTarget,
│                        # plus the contested-shape detector
└── route.py             # the Dispatcher class: classify, call solver,
                         # verify, return outcome
```

Two source files. `classify.py` is pure — no solver imports, no I/O,
testable in isolation. `route.py` holds the `Dispatcher` class which
owns the Z3 context, holds references to the bridge instances, and
runs the verify-before-return cycle.

### 2.2 Import graph

```
hlmr.kernel              ← (trusted; only imports stdlib + hlmr.ir)
hlmr.ir                  ← (no imports beyond stdlib)
hlmr.unify               ← imports hlmr.ir
hlmr.solve.sld           ← imports hlmr.ir, hlmr.unify
hlmr.solve.render        ← imports hlmr.ir, hlmr.unify, hlmr.solve.sld
hlmr.solvers.z3_bridge   ← imports hlmr.ir, z3
hlmr.solvers.sympy_bridge← imports hlmr.ir, sympy
hlmr.dispatch.classify   ← imports hlmr.ir
hlmr.dispatch.route      ← imports hlmr.ir, hlmr.kernel (check_proof
                                                          only),
                                  hlmr.solvers.z3_bridge,
                                  hlmr.solvers.sympy_bridge,
                                  hlmr.unify.substitution,
                                  hlmr.dispatch.classify
hlmr.solve.__init__      ← (manual_solve) imports
                              hlmr.dispatch (when a Dispatcher is
                              passed), hlmr.solve.sld, hlmr.solve.render
hlmr.repl                ← imports everything user-facing
```

Hard rules, restated from `prd.md` §5 and `prd_milestone_2.md` §4:

- **`kernel/` imports only stdlib and `hlmr.ir`.** Unchanged from M1.
  `dispatch/` does NOT appear in any kernel import chain.
- **`dispatch/` imports `kernel.check_proof` (the public entry only),
  not `kernel/rules.py`'s private `_eval_term` / `_eval_atom`
  helpers.** The witness-verification round-trip goes through the
  same `check_proof` API the rest of the codebase uses. This keeps
  the trust boundary clean — if `dispatch/` had its own arithmetic
  evaluator, dispatcher bugs could mask kernel bugs and vice versa.
- **`solvers/` is the only place Z3 and SymPy are imported.**
  `dispatch/route.py` talks to the bridges through their typed
  return values; it never imports `z3` or `sympy` directly.
- **The IR is the single bus.** `dispatch/` reads and writes
  `Atom`, `Equals`, `Substitution`, `Meta`, `Func`, `Const`, `Var`
  — the same types every other module uses.

### 2.3 The kernel-isolation test still passes

`tests/test_kernel_isolation.py` walks `kernel/*.py` with `ast` and
asserts every import resolves to stdlib or `hlmr.ir`. M2 adds nothing
to `kernel/` beyond `arithEval` (per Task A) which only adds
`fractions.Fraction` and re-uses already-imported IR types. The
isolation test is unaffected by `dispatch/`'s creation.

---

## 3. Public API surface

This section enumerates what `dispatch/__init__.py` re-exports.
Implementations live in `classify.py` and `route.py`.

### 3.1 The six outcomes

The outcome ADT. Each variant is a frozen dataclass; collectively
they form a sealed sum type `DispatchOutcome`.

```python
@dataclass(frozen=True)
class UniqueSolution:
    """The constraint has exactly one satisfying assignment.
    binding maps query-meta names to ground terms."""
    binding: Substitution

@dataclass(frozen=True)
class MultipleSolutions:
    """The constraint has finitely many *verified valid* satisfying
    assignments, all enumerated. solutions is non-empty (≥2
    entries).

    steps is paired one-to-one with solutions: steps[i] is the
    pre-verified DispatcherResolvedStep that the renderer would
    walk if the user picks solutions[i].

    Partitioning of bridge-returned witnesses (§5.3 / §7 / §12.6).
    When the bridge returns a candidate root set, the dispatcher
    runs verify-before-return (§5.4) on each candidate and
    partitions the results into three classes:

      (a) Verified valid — arithEval accepts the constructed
          ground atom. The witness joins the solutions/steps arrays.
      (b) Case 2 — verify rejects with MalformedArithmetic on a
          contested-shape ground atom (currently `0^0` per
          ARITH_EVAL_DESIGN.md §11.3 M14; see §7.3 for the
          contested-shape detector). The witness is logged as a
          contested rejection (informational, surfaced in the REPL
          — see §12.6) and DROPPED from the result. It does not
          join solutions/steps.
      (c) Case 1 — verify rejects with EvaluationFalse, or with
          MalformedArithmetic on a non-contested shape (§7.2).
          This is a true solver/kernel disagreement — the
          dispatcher CRASHES via SolverKernelDisagreement. No
          partial result is returned.

    Outcome narrowing on the count of (a):
      0 valid → outcome becomes NoSolution()
      1 valid → outcome becomes UniqueSolution(binding=…)
                with step = the single pre-built step
      ≥2 valid → outcome stays MultipleSolutions(solutions, steps)

    This means a MultipleSolutions outcome reaching the caller
    always carries ≥2 verified valid witnesses; partial-contested
    inputs that reduce the valid set to <2 are silently narrowed
    to a more specific outcome. §12.6 walks through the canonical
    example (?X^?X = 1 with bridge-roots {1, 0} → ?X=0 dropped as
    Case 2 → outcome narrows to UniqueSolution({?X: 1}))."""
    solutions: tuple[Substitution, ...]
    steps: tuple[DispatcherResolvedStep, ...]

@dataclass(frozen=True)
class InfinitelyManySolutions:
    """The constraint admits infinitely many satisfying assignments.
    example is one such; free_metas lists which meta names remain
    unbound when example is applied."""
    example: Substitution
    free_metas: tuple[str, ...]

@dataclass(frozen=True)
class NoSolution:
    """The constraint is unsatisfiable. The dispatcher reports this
    as the resolved outcome for that goal — the caller decides
    whether to backtrack via 'back' or abort."""
    pass

@dataclass(frozen=True)
class Underdetermined:
    """The constraint admits a binding for some metas but leaves
    others structurally unbound (chains of metas that never resolve
    to ground terms). Generalises M1's HARDENING_FINDINGS.md
    universal-fact case to cover solver-side underdetermination too.

    partial_binding is the saturated substitution from the solver
    (or from SLD, in the M1-universal-fact case). unbound names the
    metas in the original query that, after applying partial_binding
    and saturating, still resolve to a Meta rather than a ground
    term."""
    partial_binding: Substitution
    unbound: tuple[str, ...]

@dataclass(frozen=True)
class OutsideFragment:
    """The constraint is outside HLMR's M2 decidable fragment. The
    classification field names the specific reason (used for
    logging, REPL display, and dispatch-test assertions). reason is
    a free-form human-readable message."""
    classification: OutsideFragmentReason
    reason: str

DispatchOutcome = (
    UniqueSolution
    | MultipleSolutions
    | InfinitelyManySolutions
    | NoSolution
    | Underdetermined
    | OutsideFragment
)

class OutsideFragmentReason(Enum):
    TRANSCENDENTAL = "transcendental"
    CONTESTED_CONVENTION = "contested_convention"
    UNRECOGNISED_SHAPE = "unrecognised_shape"
    NON_LINEAR_BEYOND_SYMPY = "non_linear_beyond_sympy"
    SOLVER_TIMEOUT = "solver_timeout"
    SOLVER_UNKNOWN = "solver_unknown"
```

### 3.2 Route targets and classification

```python
class RouteTarget(Enum):
    KB = "kb"               # M1 SLD path; not handled by Dispatcher
    Z3 = "z3"               # linear arithmetic, finite domains
    SYMPY = "sympy"         # symbolic algebraic equations
    REJECTED = "rejected"   # OutsideFragment

@dataclass(frozen=True)
class ClassifyDecision:
    """The classifier's verdict on a single goal."""
    target: RouteTarget
    # If REJECTED, why:
    reason: OutsideFragmentReason | None = None
    detail: str = ""
```

`ClassifyDecision` is the pure output of `classify.py` — no solver
calls, just a verdict. `Dispatcher.dispatch()` consumes it.

### 3.3 The Dispatcher class

```python
@dataclass
class Dispatcher:
    """Stateful dispatcher; one per REPL session.

    Owns a persistent Z3 context (per §5.2 of prd_milestone_2.md;
    confirmed in §9 of this design). SymPy is stateless (also
    confirmed). Holds a logger handle for emitting JSONL events
    per §10.
    """

    z3_bridge: Z3Bridge          # one persistent context
    sympy_bridge: SymPyBridge    # stateless wrapper
    kb: KnowledgeBase            # for finite-domain extraction
    logger: SessionLogger | None = None
    timeout_ms: int = 5000       # default per-solver timeout

    def classify(self, goal: Atom | Equals,
                 subst: Substitution) -> ClassifyDecision:
        """Pure classification. Apply subst to goal first."""

    def dispatch(self, goal: Atom | Equals,
                 subst: Substitution) -> DispatchResult:
        """Classify + route + verify. Returns DispatchResult.

        DispatchResult is a thin wrapper combining the classify
        decision, the resulting outcome, and (on success) the
        DispatcherResolvedStep that the renderer will walk."""
```

```python
@dataclass(frozen=True)
class DispatchResult:
    decision: ClassifyDecision
    outcome: DispatchOutcome
    step: DispatcherResolvedStep | None
    # step is set ONLY for UniqueSolution (one witness, one step).
    # For MultipleSolutions, the per-solution steps live on
    # outcome.steps (paired with outcome.solutions); the result-level
    # step field is None and manual_solve picks the chosen step
    # from the outcome.  For NoSolution, Underdetermined, and
    # OutsideFragment, no step is produced — the renderer is not
    # invoked on those paths.
```

### 3.4 The new SLD step variants

`solve/sld.py`'s `SLDStep` becomes a discriminated union. M1 callers
(four demos, M1 tests) construct only `ClauseResolvedStep`; they
remain green. M2 introduces `DispatcherResolvedStep` for arithmetic
goals.

```python
@dataclass(frozen=True)
class ClauseResolvedStep:
    """An SLD step resolved by unifying the goal with a KB clause.
    This is the M1 step shape, renamed."""
    goal_resolved: Atom | Equals     # post-substitution
    clause_used: Clause
    clause_renamed: Clause
    unifier: Substitution            # accumulated subst after step

@dataclass(frozen=True)
class DispatcherResolvedStep:
    """An SLD step resolved by routing the goal to the dispatcher.
    The goal is no longer a candidate for clause resolution; it is
    proven directly by the kernel's arithEval rule once the dispatcher
    binds any metas in it."""
    goal_resolved: Atom | Equals     # post-substitution; may still
                                     # contain metas before binding
    ground_atom: Atom | Equals       # post-binding, fully ground;
                                     # this is what the renderer
                                     # emits as an arithEval line's
                                     # formula
    route: RouteTarget               # Z3 or SYMPY (never KB or REJECTED)
    binding_added: Substitution      # what the solver added to subst
    solver_summary: str              # for logging; not load-bearing

SLDStep = ClauseResolvedStep | DispatcherResolvedStep
```

`SLDState.history` becomes `tuple[SLDStep, ...]` with the new
discriminated union. The renderer pattern-matches on the variant to
choose its emit path (see `RENDER_M2_DESIGN.md` §3 and §4).

> **Note on the M2 PRD §7 phrasing.** PRD §7 says "SLDStep gains an
> optional 'arithmetic origin' marker." A discriminated union is
> structurally cleaner than an optional field with implicit
> field-presence invariants. The end result is the same: a step is
> either clause-resolved (with `clause_used`/`clause_renamed`/
> `unifier`) or dispatcher-resolved (with `ground_atom`/`route`/
> `binding_added`). Implementer's choice in style; this design
> recommends the discriminated-union form for type clarity.

---

## 4. Constraint classification (in detail)

This is the core of `classify.py`. The classifier reads a single goal
plus the current substitution and returns a `ClassifyDecision`. It
does not call solvers; it does not consult the KB beyond predicate
names; it is pure.

### 4.1 The classification function

```python
def classify(goal: Atom | Equals,
             subst: Substitution,
             kb: KnowledgeBase) -> ClassifyDecision:
    """
    1. Apply subst to goal.
    2. Pattern-match on the goal's top-level shape.
    3. Return the routing verdict.
    Conservative defaults: when in doubt, REJECTED with
    UNRECOGNISED_SHAPE.
    """
```

### 4.2 Classification rules, in order

The classifier evaluates these patterns top-to-bottom. The first
matching pattern wins. Order is deliberate — earlier patterns are
more specific.

**Rule C1: KB predicate.** Goal is `Atom(pred, args)` where `pred` is
the head predicate of some clause in the KB **and** `pred` is not in
the M2 arithmetic predicate set
(`{<, <=, >, >=, !=, plus, minus, times, divides, root_of}`).
→ `KB`. The dispatcher does not handle this; M1's clause-picker
loop in `manual_solve` does.

**Rule C2: Comparison atom (operator-form).** Goal is `Atom(pred,
(a, b))` where `pred ∈ {<, <=, >, >=, !=}` and arity is exactly 2.
- If both `a` and `b` are arithmetic-evaluable terms (recursively
  built from `Const(int|Fraction)`, `Meta`, `Var`, and the operators
  `{+, -, *, /, ^}`) AND no `^` subterm has a non-`Const(int)`
  exponent or a base-or-exponent that is contested when ground (see
  Rule C8 below for `0^0`):
  → `Z3`.
- Otherwise: → `REJECTED` with `UNRECOGNISED_SHAPE` or
  `TRANSCENDENTAL` as appropriate.

**Rule C3: Predicate-form ternary atom.** Goal is `Atom(pred,
(a, b, c))` where `pred ∈ {plus, minus, times, divides}` and arity is
3. Same evaluable-shape requirements as C2.
→ `Z3`.

**Rule C4: `root_of/2`.** Goal is `Atom("root_of", (target, poly))`
with arity 2.
- If `poly` is a polynomial with rational coefficients in a single
  variable (recognisable by walking `poly`: only `+ - * ^` operators,
  one `Var` or `Meta` representing the variable, all `Const`s
  numeric, no `^` with a `Var/Meta` exponent):
  → `SYMPY`.
- If `poly` contains transcendentals (`^` with `Var/Meta` in the
  exponent, or any other unrecognised function symbol like `sin`,
  `log`, `exp`):
  → `REJECTED` with `TRANSCENDENTAL`.
- Otherwise: → `REJECTED` with `UNRECOGNISED_SHAPE`.

**Rule C5: `Equals` IR node.** Goal is `Equals(lhs, rhs)`.
- If both sides are arithmetic-evaluable (per the term shape rules
  in C2): the equality is in the arithmetic fragment.
  - If linear in any free metas: → `Z3`.
  - If polynomial (non-linear in some meta) with rational
    coefficients: → `SYMPY`.
  - If transcendental: → `REJECTED` with `TRANSCENDENTAL`.
- If both sides are non-arithmetic terms (e.g. `Equals(Var("X"),
  Const("alice"))`): this is a unification-style equality, handled
  by SLD in M1 — but M1's SLD does not produce `Equals` goals from
  Horn-clause resolution. If such a goal appears in M2, treat as
  `KB` and let `manual_solve` route it to its existing logic
  (which may unify, fail, or stall). M2 does not extend equality
  handling.
- If sides are mixed (one arithmetic, one symbolic): → `REJECTED`
  with `UNRECOGNISED_SHAPE`.

**Rule C6: Multi-goal queries.** A query is a `tuple[Atom | Equals,
...]`. The classifier is called per-goal. There is no "classify the
tuple" entry point. `manual_solve` iterates the tuple in order
applying the running substitution; each goal is classified
independently.

**Rule C7: Default — anything else.** → `REJECTED` with
`UNRECOGNISED_SHAPE`. This is the conservative-default per
`prd.md` §4. The dispatcher never guesses.

**Rule C8: Contested-content shape detection.** This is the new
rule introduced in v1.1 of ARITH_EVAL_DESIGN.md.

The classifier maintains a `_contested_shapes` predicate that
detects atoms whose syntactic shape is in `arithEval`'s evaluable
set but whose value is convention-dependent. Currently this is a
single pattern:

```python
def _is_contested_when_ground(t: Term) -> bool:
    """True if t is a ground Func("^", (a, b)) where a and b both
    evaluate to 0 (i.e., 0^0 — contested per docs/strategic_direction.md
    §6.9 and §11.7).

    Used by classify() in two places:
      - As a pre-filter: if a goal's terms include a ground 0^0
        subterm, skip Z3/SymPy (those would produce a witness that
        arithEval rejects on conservative-default grounds, which
        looks like a Case 2 disagreement) and classify directly as
        REJECTED with CONTESTED_CONVENTION.
      - As a post-filter at verify-time: if Z3/SymPy returns a
        witness that produces a ground 0^0 (or other contested
        shape) when substituted into the original goal, the
        Dispatcher reclassifies as OutsideFragment per §7.
    """
    match t:
        case Func(name="^", args=(a, b)):
            # both arguments must evaluate to 0 (using the same
            # ground-evaluator structure as arithEval, but staying in
            # classify.py — duplicate the small subset needed; do not
            # import kernel internals)
            return _is_zero_const(a) and _is_zero_const(b)
        case Func(args=args):
            return any(_is_contested_when_ground(a) for a in args)
        case _:
            return False
```

When C8 fires during classification, the goal is `REJECTED` with
`CONTESTED_CONVENTION`. The full rationale, including how this
plays out at the verify-before-return step, is in §7.

### 4.3 What classification does NOT do

- **Does not call any solver.** Pure function. Testable in isolation
  with constructed IR inputs.
- **Does not bind metas.** That is the dispatcher's `route()` job.
- **Does not consult clause bodies.** Classification reads only the
  predicate name (against the KB's known predicates) and the goal's
  syntactic shape. It does not enumerate KB clauses to derive a
  finite domain — that is `route.py`'s job (when needed for Z3
  encoding, see §5.2.b).
- **Does not normalise.** `5 + 0 = 5` is not simplified to `5 = 5`.
  The dispatcher routes on shape, not on value.

### 4.4 Classification determinism

For a fixed `(goal, subst, kb.clauses)` triple, `classify()` returns
the same `ClassifyDecision` every time. Tested by a Hypothesis
property test (§11.3).

---

## 5. Routing and witness verification

`route.py`'s `Dispatcher.dispatch()` is the workhorse. Given a goal
and substitution, it produces a `DispatchResult`.

### 5.1 The dispatch loop

```python
def dispatch(self, goal: Atom | Equals,
             subst: Substitution) -> DispatchResult:
    # 1. Apply substitution to goal.
    g = apply_to_formula(subst, goal)

    # 2. Classify.
    decision = classify(g, subst, self.kb)

    # 3. Log the classification decision.
    self._log_classify(g, decision)

    # 4. Route.
    match decision.target:
        case RouteTarget.KB:
            # Should not happen — KB goals do not reach the dispatcher.
            # The caller (manual_solve) routes KB goals to its own
            # clause-picker loop. If we get here, it is a wiring bug.
            raise DispatchError(
                "KB-classified goal reached dispatcher — caller bug")
        case RouteTarget.REJECTED:
            return DispatchResult(
                decision=decision,
                outcome=OutsideFragment(
                    classification=decision.reason,
                    reason=decision.detail or "rejected by classifier"),
                step=None,
            )
        case RouteTarget.Z3:
            return self._dispatch_z3(g, decision, subst)
        case RouteTarget.SYMPY:
            return self._dispatch_sympy(g, decision, subst)
```

### 5.2 Z3 dispatch path

```python
def _dispatch_z3(self, goal, decision, subst) -> DispatchResult:
    # 5.2.a Build the Z3 problem.
    #   - Translate every Meta in `goal` into a Z3 Int or Real,
    #     pinned to self.z3_bridge.context.
    #   - Translate Const, Func, and the operator atoms through the
    #     bridge's typed conversion API (defined by §8 of
    #     prd_milestone_2.md, which solvers/ implements).
    #   - For metas typed as FiniteDomain(values), add a disjunctive
    #     constraint Or(M == v1, M == v2, ...).
    #   - For Integer-typed metas, declare as z3.Int.
    #   - For Rational-typed metas, declare as z3.Real.
    #   - For Categorical-typed metas (the M1 default) appearing in
    #     an arithmetic context, this is a wiring issue — the M2
    #     parser should mark such metas Integer/Rational explicitly.
    #     The classifier rejects with UNRECOGNISED_SHAPE if a
    #     Categorical meta appears in an arithmetic atom.

    # 5.2.b If goal references a KB predicate transitively (e.g. the
    # §2 prime example needs ?P ∈ {2, 3, 5, 7} extracted from the
    # prime/1 facts), this extraction is done by manual_solve BEFORE
    # the goal reaches the dispatcher: SLD has already bound ?P to
    # one of the four primes via the picker, so by the time
    # ?P > 2 reaches the dispatcher, ?P is ground.
    # In other words: the dispatcher does not synthesise finite domains
    # from the KB. Manual mode does this through the user's clause picks.

    # 5.2.c Call the Z3 bridge.
    z3_result = self.z3_bridge.check(constraints, timeout_ms=self.timeout_ms)

    match z3_result:
        case Z3Sat(model):
            # 5.2.d Convert model to a Substitution.
            binding = self._z3_model_to_subst(model, original_metas)

            # 5.2.e Detect underdetermination via add-negation-and-recheck.
            if self._has_free_metas_in_model(model, original_metas):
                # Z3 treats remaining metas as anything; explicitly
                # check whether a second model exists.
                neg = self._negate_model(model)
                second = self.z3_bridge.check(constraints + (neg,),
                                               timeout_ms=self.timeout_ms)
                if isinstance(second, Z3Sat):
                    return DispatchResult(
                        decision=decision,
                        outcome=Underdetermined(
                            partial_binding=binding,
                            unbound=tuple(self._free_meta_names(...))),
                        step=None,
                    )
                # else: the first model is the unique witness for the
                # remaining metas → fall through to UniqueSolution.

            # 5.2.f Verify before return: build a ground residual and
            # check_proof it via arithEval (§6).
            ground = apply_to_formula(binding, goal)
            verify_result = self._verify_arith_ground(ground)

            return self._classify_verify_result(
                verify_result, ground, decision, binding,
                route=RouteTarget.Z3,
                solver_summary=str(model),
                original_goal=goal,
                subst_extension=binding,
            )

        case Z3Unsat():
            return DispatchResult(
                decision=decision,
                outcome=NoSolution(),
                step=None,
            )
        case Z3Unknown(reason):
            return DispatchResult(
                decision=decision,
                outcome=OutsideFragment(
                    classification=OutsideFragmentReason.SOLVER_UNKNOWN,
                    reason=f"Z3 returned unknown: {reason}"),
                step=None,
            )
        case Z3Timeout():
            return DispatchResult(
                decision=decision,
                outcome=OutsideFragment(
                    classification=OutsideFragmentReason.SOLVER_TIMEOUT,
                    reason=f"Z3 timed out after {self.timeout_ms}ms"),
                step=None,
            )
```

### 5.3 SymPy dispatch path

> **Verify-atom construction.** Most arithmetic goals are first-order:
> when bound, the post-substitution goal *is* the atom `arithEval`
> verifies. For example `Atom(">", (Meta("?P"), Const(2)))` with
> `{?P: 5}` becomes `Atom(">", (Const(5), Const(2)))`, which arithEval
> directly evaluates.
>
> `root_of/2` is the exception. It is a higher-order shape:
> `root_of(?X, p)` means "?X is a root of polynomial p," where p
> contains a placeholder variable (typically `Var("x")`). Substituting
> `{?X: 2}` into the goal produces `root_of(Const(2), p)`, which
> `arithEval` rejects (`root_of` is not in §5 of ARITH_EVAL_DESIGN.md
> — it is a dispatcher-recognised predicate, not an evaluable one).
>
> The dispatcher therefore constructs the **verify atom** explicitly
> for `root_of` goals: substitute the root into the polynomial and
> equate to zero. Concretely:
>
> ```python
> def _construct_verify_atom(
>     goal: Atom | Equals,
>     binding: Substitution,
> ) -> Atom | Equals:
>     """For most goals, the verify atom is just goal[binding]. For
>     root_of(target, poly) goals, the verify atom is the substituted
>     polynomial = 0 equation."""
>     match goal:
>         case Atom(pred="root_of", args=(target, poly)):
>             # target is the meta being solved for; poly is a
>             # polynomial in some Var.  Substitute the bound value
>             # of target into poly's free variable and assert == 0.
>             root_term = apply_to_term(binding, target)
>             poly_var = _polynomial_var(poly)         # the Var inside poly
>             instantiated_poly = subst_term(poly, poly_var.name, root_term)
>             return Equals(instantiated_poly, Const(0))
>         case _:
>             return apply_to_formula(binding, goal)
> ```
>
> The verify atom is what the dispatcher's `ground_atom` field on
> `DispatcherResolvedStep` records — and what the renderer emits as
> the formula on its `arithEval` line. The original goal stays in
> `goal_resolved` for logging and traceability.
>
> This is the only goal-shape transformation in M2; future arithmetic
> predicates may need their own. The transformation lives in
> `dispatch/route.py`; the renderer is shape-agnostic and trusts that
> `step.ground_atom` is `arithEval`-acceptable.

```python
def _dispatch_sympy(self, goal, decision, subst) -> DispatchResult:
    # 5.3.a Translate goal to SymPy form via the bridge.
    sp_problem = self.sympy_bridge.translate(goal)

    # 5.3.b Call solveset with domain=Reals (per §5.1.2 of
    # prd_milestone_2.md and the prep report).
    sp_result = self.sympy_bridge.solveset(sp_problem)

    match sp_result:
        case SymPyFiniteRoots(roots) if len(roots) == 1:
            binding = self._sympy_root_to_subst(roots[0], target_meta)
            ground = self._construct_verify_atom(goal, binding)
            verify_result = self._verify_arith_ground(ground)
            return self._classify_verify_result(
                verify_result, ground, decision, binding,
                route=RouteTarget.SYMPY,
                solver_summary=f"sympy: {roots}",
                original_goal=goal,
                subst_extension=binding,
            )

        case SymPyFiniteRoots(roots) if len(roots) > 1:
            # Build (binding, ground_atom) pairs for every candidate.
            bindings = tuple(
                self._sympy_root_to_subst(r, target_meta) for r in roots)
            ground_atoms = tuple(
                self._construct_verify_atom(goal, b) for b in bindings)

            # Partition candidates into:
            #   valid       — verify accepts (Class (a) per §3.1)
            #   case2_drops — verify rejects with MalformedArithmetic
            #                 on a contested shape; logged & DROPPED
            #                 (Class (b) per §3.1; see §7.3, §12.6)
            # Case 1 — verify rejects on a non-contested shape, OR
            #          rejects with EvaluationFalse — CRASH; no
            #          partial result is returned (Class (c) per §3.1,
            #          §7.2).  We do not collect Case 1 rejections;
            #          the dispatcher exits via SolverKernelDisagreement
            #          inside _classify_verify_result.
            valid_bindings: list[Substitution] = []
            valid_steps: list[DispatcherResolvedStep] = []
            for i, (b, ga) in enumerate(zip(bindings, ground_atoms)):
                vr = self._verify_arith_ground(ga)
                if vr.ok:
                    step = self._make_step(
                        goal, ga, RouteTarget.SYMPY, b,
                        solver_summary=f"sympy: {roots}; witness {i}")
                    valid_bindings.append(b)
                    valid_steps.append(step)
                    continue

                # vr.ok is False — discriminate per §7.2.
                if (vr.error_class is MalformedArithmetic
                    and _ground_atom_lands_on_contested_shape(ga)):
                    # Case 2 — drop this witness and log informationally.
                    self._log_contested_rejection(
                        ga, RouteTarget.SYMPY, b)
                    continue

                # Case 1 — disagreement.  Crash.  Re-using the
                # shared discriminator keeps the crash message
                # uniform across single- and multi-witness paths.
                # _classify_verify_result raises SolverKernelDisagreement
                # for both EvaluationFalse and non-contested
                # MalformedArithmetic.
                self._classify_verify_result(
                    vr, ga, decision, b,
                    route=RouteTarget.SYMPY,
                    solver_summary=f"sympy: {roots}; witness {i}",
                    original_goal=goal,
                    subst_extension=b,
                )
                # _classify_verify_result raises in the Case 1 branch;
                # this point is unreachable.  If it ever returns here,
                # that's a bug in the discriminator and we re-raise.
                raise DispatchError(
                    "unreachable: _classify_verify_result must crash "
                    "or return a result; got fall-through on Case 1")

            # Outcome narrowing on the count of valid witnesses
            # (per §3.1 partitioning policy).
            n_valid = len(valid_bindings)
            if n_valid == 0:
                # Every bridge-returned root was contested; report
                # NoSolution (no valid witness exists in arithEval's
                # uncontested fragment).  The contested rejections
                # are already logged.
                return DispatchResult(
                    decision=decision,
                    outcome=NoSolution(),
                    step=None,
                )
            if n_valid == 1:
                # Narrow to UniqueSolution.  The renderer walks the
                # single step; the contested siblings stay in the
                # log.
                return DispatchResult(
                    decision=decision,
                    outcome=UniqueSolution(binding=valid_bindings[0]),
                    step=valid_steps[0],
                )
            # ≥2 valid witnesses — true MultipleSolutions.
            return DispatchResult(
                decision=decision,
                outcome=MultipleSolutions(
                    solutions=tuple(valid_bindings),
                    steps=tuple(valid_steps)),
                # The result-level step field is None for
                # MultipleSolutions; manual_solve reads
                # outcome.steps[chosen] after solver_picker (§6.1).
                step=None,
            )

        case SymPyNoRealRoots():
            return DispatchResult(
                decision=decision, outcome=NoSolution(), step=None)

        case SymPyConditionSet(reason):
            # ConditionSet → SymPy could not simplify; e.g.
            # transcendental that wasn't caught by classify.
            # Treat as OutsideFragment.
            return DispatchResult(
                decision=decision,
                outcome=OutsideFragment(
                    classification=OutsideFragmentReason.NON_LINEAR_BEYOND_SYMPY,
                    reason=f"SymPy returned ConditionSet: {reason}"),
                step=None,
            )

        case SymPyError(msg):
            # The bridge translated the error into a typed value;
            # treat as solver/kernel disagreement (a bug to surface).
            raise DispatchError(f"SymPy bridge error: {msg}")
```

### 5.4 Verify-before-return — `_verify_arith_ground`

This is the development-time crash mechanism for solver/kernel
disagreement (`prd.md` §4 architectural commitment, restated in
`prd_milestone_2.md` §4 and §15). Per ARITH_EVAL_DESIGN.md §8.3
and §12.1, the verification goes through the public `check_proof`
API — never through `_eval_term` / `_eval_atom`.

```python
def _verify_arith_ground(self, ground_atom: Atom | Equals) -> VerifyResult:
    """Build a one-line Proof with ground_atom as the formula and
    arithEval as the justification, run it through check_proof,
    and classify the result."""
    line = ProofLine(
        number=1,
        formula=ground_atom,
        justification=RuleApp("arithEval", (), (), {}),
        box_depth=0,
    )
    one_line_proof = Proof(lines=(line,), goal=ground_atom)
    result = check_proof(one_line_proof)
    return VerifyResult.from_check_result(result, ground_atom)


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    error_class: type | None       # MalformedArithmetic | EvaluationFalse
                                    # | None on success
    formula: Atom | Equals          # the verified or rejected atom

    @classmethod
    def from_check_result(cls, r: CheckResult, formula) -> VerifyResult:
        if isinstance(r, Verified):
            return cls(ok=True, error_class=None, formula=formula)
        # CheckFailure
        return cls(ok=False, error_class=type(r.reason), formula=formula)
```

`VerifyResult` is a thin wrapper — the dispatcher doesn't introspect
the error's `reason` string (which is debug-only per
ARITH_EVAL_DESIGN.md §10.1); it just checks the error class. This
matches the test-contract guidance in CLAUDE.md.

The `_classify_verify_result` helper translates a `VerifyResult` into
the appropriate `DispatchResult` per §7's two-case logic.

### 5.5 The `DispatcherResolvedStep` constructed on success

When verification succeeds, the dispatcher constructs the step the
renderer will walk:

```python
def _make_step(self, goal, ground, route, binding, summary):
    return DispatcherResolvedStep(
        goal_resolved=goal,        # post-substitution from the caller
        ground_atom=ground,        # post-binding, fully ground
        route=route,
        binding_added=binding,
        solver_summary=summary,
    )
```

The renderer reads `step.ground_atom` and emits `Atom(...)` /
`Equals(...)` as a one-line `arithEval` justification (per
RENDER_M2_DESIGN.md §4).

---

## 6. The mixed-goal seam with SLD

`solve/__init__.py:manual_solve` is the integration point. M2's
extended signature (per `prd_milestone_2.md` §12):

```python
def manual_solve(
    kb: KnowledgeBase,
    goal: Atom | Equals | tuple[Atom | Equals, ...],
    picker: Callable[[list[Clause], SLDState], int | None],
    dispatcher: Dispatcher | None = None,
) -> tuple[Substitution, Proof] | tuple[Substitution, None] | None:
```

### 6.1 The integration loop

```python
def manual_solve(kb, goal, picker, dispatcher=None):
    # Normalise to tuple (M2 multi-goal queries).
    goals = (goal,) if isinstance(goal, (Atom, Equals)) else tuple(goal)

    state = SLDState(goals=goals, subst={}, history=())

    while state.goals:
        current = state.goals[0]
        # Decide: KB or dispatcher?
        if dispatcher is None:
            # M1 mode — every goal goes through the picker.
            decision = ClassifyDecision(target=RouteTarget.KB)
        else:
            decision = dispatcher.classify(current, state.subst, kb)

        if decision.target == RouteTarget.KB:
            # M1 path: enumerate candidate clauses, ask picker, resolve.
            candidates = sld.candidates(state, kb)
            idx = picker(candidates, state)
            if idx is None:
                return None  # user gave up
            new_state = sld.resolve(state, candidates[idx])
            if new_state is None:
                return None  # user picked an unmatchable clause
            state = new_state
        else:
            # M2 path: route through dispatcher.
            result = dispatcher.dispatch(current, state.subst)
            if isinstance(result.outcome, NoSolution):
                return None  # this goal failed; caller can backtrack
            if isinstance(result.outcome, OutsideFragment):
                return _outside_fragment_signal(result.outcome)
                # See §11.3 for OutsideFragment threading
            if isinstance(result.outcome, Underdetermined):
                # M1 universal-fact pattern, generalised.
                # Return (subst, None) per HARDENING_FINDINGS.md fix.
                return (state.subst, None)
            if isinstance(result.outcome, MultipleSolutions):
                # M2 lets the user pick (REPL); manual_solve wires
                # this to a sub-picker for solutions.  The
                # dispatcher already verified every witness before
                # returning MultipleSolutions, so each solutions[i]
                # has a paired pre-built steps[i].
                chosen = solver_picker(result.outcome.solutions)
                if chosen is None:
                    return None
                binding = result.outcome.solutions[chosen]
                step_to_append = result.outcome.steps[chosen]
            else:  # UniqueSolution
                binding = result.outcome.binding
                step_to_append = result.step  # set per §3.3

            # Extend the substitution and pop the goal.
            new_subst = compose(state.subst, binding)
            new_history = state.history + (step_to_append,)
            state = SLDState(
                goals=state.goals[1:],
                subst=new_subst,
                history=new_history,
            )

    # All goals resolved. Run the M1 underdetermined check (per
    # HARDENING_FINDINGS.md fix) and either return (subst, proof) or
    # (subst, None).
    sat = _saturate(state.subst)
    if any_query_meta_unbound(sat, original_query_metas):
        return (sat, None)
    proof = render(state, kb, original_query_atom)  # extended renderer
    if not isinstance(check_proof(proof), Verified):
        raise RenderError("rendered proof rejected by kernel")
    return (sat, proof)
```

### 6.2 Goal-by-goal vs joint solve

The dispatcher decides goal-by-goal, in left-to-right query order, as
specified by `prd_milestone_2.md` §12. When the user has a query
`?- prime(?P), ?P > 2, ?P < 6, ?P != 4.`:

1. Goal 1 `prime(?P)` → KB → user picks one of the four `prime` facts.
   Say they pick `prime(5)`. Subst becomes `{?P: 5}`.
2. Goal 2 `?P > 2`, after applying subst, becomes `5 > 2`. Classified
   as Z3. Dispatched. Already ground — Z3 returns sat trivially (or
   the dispatcher short-circuits and verifies directly via arithEval,
   §11.5). Verifies. Step emitted.
3. Goal 3 `?P < 6` → `5 < 6` → arithEval verifies. Step emitted.
4. Goal 4 `?P != 4` → `5 != 4` → arithEval verifies. Step emitted.
5. All goals consumed. Render proof.

If at step 2 the user had instead picked `prime(2)`, then goal 2
would be `2 > 2` → arithEval rejects with `EvaluationFalse` → the
dispatcher returns `NoSolution` for that goal → `manual_solve`
returns `None` → REPL prints "no solution along this path" → user
backtracks via `back` and picks a different clause.

This is the manual-mode interaction model. Joint solving (giving
all four constraints to Z3 at once and letting it find ?P=5
directly) is **not** in M2's scope — that requires the dispatcher
to extract finite-domain content from the KB, which is automated
inference. M3 may add this; for M2, the user does the picking.

### 6.3 Substitution semantics across the SLD/dispatcher seam

- The dispatcher reads `state.subst`, applies it to the goal before
  classifying, and on a Z3/SymPy success returns a `binding` that
  extends the substitution.
- `manual_solve` composes `state.subst` with `binding` via
  `unify.substitution.compose`. M1 already handles compose
  associativity and idempotence; M2 reuses unchanged.
- The renderer reads the final substitution (`_saturate(state.subst)`)
  to apply to ground residual atoms before emitting `arithEval`
  lines. See RENDER_M2_DESIGN.md §4.

### 6.4 Backtracking through dispatcher steps

The user's `back` REPL command (M1) pops the most recent SLD step.
For `ClauseResolvedStep`s this is unchanged from M1. For
`DispatcherResolvedStep`s it works the same way — the step is
popped from `state.history` and the substitution is rolled back to
the pre-step state. The dispatcher itself is stateless beyond the
Z3 context (which holds variable declarations across the session
but is reset to no-assertions at session start; per §9). Re-dispatching
the same goal under the same subst yields the same outcome, so
backtracking-then-redispatching is well-defined.

---

## 7. Conventions as declared axioms — Case 1 vs Case 2 distinction

This is the section §12.1 of ARITH_EVAL_DESIGN.md (v1.1) flagged as
the dispatcher's responsibility. The strategic basis is
`docs/strategic_direction.md` §6.9 (introduced in v1.1) and §11.7.

### 7.1 The two failure modes at verify time

When `_verify_arith_ground` returns `VerifyResult(ok=False,
error_class=...)`, the dispatcher must distinguish:

- **Case 1 — Solver/kernel disagreement (development-time crash).**
  The solver claimed a witness that does not satisfy the constraint
  under arithEval's evaluable set. Either the solver is wrong, the
  bridge translated incorrectly, or the kernel is wrong. This is a
  bug. It crashes loudly in development per `prd.md` §4 / `prd_milestone_2.md`
  §4.

- **Case 2 — Sound rejection on contested-content edge.** The solver
  produced a witness that, when substituted, lands on an atom whose
  syntactic shape arithEval **deliberately** rejects on
  conservative-default grounds (currently only `0^0`; future
  contested operators per `docs/strategic_direction.md` §6.9 may
  expand the list). The witness is not "wrong" — it satisfies the
  constraint under some convention — but the kernel does not commit
  to that convention. Treat as `OutsideFragment` (with
  `CONTESTED_CONVENTION` reason). The user message explains that the
  query rests on a contested mathematical statement and points to
  the M3+ axiom-declaration pattern.

### 7.2 The discriminator

```python
def _classify_verify_result(
    self,
    verify: VerifyResult,
    ground: Atom | Equals,
    decision: ClassifyDecision,
    binding: Substitution,
    *,
    route: RouteTarget,
    solver_summary: str,
    original_goal: Atom | Equals,
    subst_extension: Substitution,
) -> DispatchResult:
    if verify.ok:
        # Success path.
        step = self._make_step(
            original_goal, ground, route, binding, solver_summary)
        return DispatchResult(
            decision=decision,
            outcome=UniqueSolution(binding=subst_extension),
            step=step,
        )

    # verify.ok is False. Pick a side.
    if verify.error_class is EvaluationFalse:
        # Case 1 — true disagreement. Crash.
        raise SolverKernelDisagreement(
            f"Solver via {route.value} returned witness {binding!r} "
            f"for goal {original_goal!r}; arithEval rejects the "
            f"resulting ground atom {ground!r} with EvaluationFalse. "
            f"This is a development-time crash. Either the solver "
            f"bridge translated the constraint wrongly, or the "
            f"solver produced an unsound witness. Investigate."
        )

    # verify.error_class is MalformedArithmetic.
    # Distinguish Case 1 from Case 2 by checking the ground atom's
    # syntactic shape against the contested-shape detector (§4.2 C8).
    if _ground_atom_lands_on_contested_shape(ground):
        # Case 2 — sound rejection. Treat as OutsideFragment.
        self._log_contested_rejection(ground, route, binding)
        return DispatchResult(
            decision=decision,
            outcome=OutsideFragment(
                classification=OutsideFragmentReason.CONTESTED_CONVENTION,
                reason=(
                    f"Goal resolves to {ground!r} which depends on a "
                    f"contested mathematical convention (currently 0^0; "
                    f"see docs/strategic_direction.md §6.9). The kernel "
                    f"does not commit to a value here; M3+ theory seeds "
                    f"may declare this as an axiom (e.g. "
                    f"`axiom pow_zero_zero: 0^0 = 1` for combinatorics)."),
            ),
            step=None,
        )

    # Case 1 — disagreement on a non-contested shape. Crash.
    raise SolverKernelDisagreement(
        f"Solver via {route.value} returned witness {binding!r} "
        f"for goal {original_goal!r}; arithEval rejects the "
        f"resulting ground atom {ground!r} with MalformedArithmetic, "
        f"but the atom's shape is fully within the evaluable set. "
        f"This is either a bridge translation bug, a solver bug, or "
        f"a kernel bug. Investigate."
    )
```

### 7.3 The contested-shape detector

```python
def _ground_atom_lands_on_contested_shape(f: Atom | Equals) -> bool:
    """True iff f contains a ground subterm whose shape is currently
    in the contested set. Currently only 0^0.

    Implementation parallels classify._is_contested_when_ground.
    Lives in classify.py and is used by both classify() (pre-filter)
    and Dispatcher._classify_verify_result (post-filter).

    KEY DESIGN POINT: the dispatcher determines this by examining
    the IR shape of `f` directly. It does NOT import the kernel's
    private _eval_term; it reproduces only the small subset of
    arithmetic-shape detection it needs. The "is this contested?"
    check is convention-list-based, not value-based, and the list
    is short (one entry, `0^0`, in M2). When the list grows in M6+,
    expand both classify._is_contested_when_ground and this detector
    in lock-step.

    Soundness consequence: if a future contested case is added to
    arithEval but not to the dispatcher's detector, the dispatcher
    will crash (Case 1) instead of treating the rejection as Case 2.
    Loud failure, not silent. Acceptable.
    """
    match f:
        case Atom(args=args):
            return any(_is_contested_when_ground(a) for a in args)
        case Equals(lhs=lhs, rhs=rhs):
            return (_is_contested_when_ground(lhs)
                    or _is_contested_when_ground(rhs))
```

### 7.4 What the user sees

For Case 2:

```
> ?- some_goal_involving(?X^?X).
... (solver session) ...
This query depends on a contested mathematical convention.
  Reason: contested_convention
  Detail: Goal resolves to root_of(?X, ...) which depends on a
  contested mathematical convention (currently 0^0; see
  docs/strategic_direction.md §6.9). The kernel does not commit
  to a value here; M3+ theory seeds may declare this as an axiom
  (e.g. axiom pow_zero_zero: 0^0 = 1 for combinatorics).

No proof produced. The query is OutsideFragment.
```

For Case 1: the dispatcher raises `SolverKernelDisagreement`
(unhandled exception). Python exits with a stack trace. This is
intentional — Case 1 is a bug, and silent failure here would defeat
the kernel's role as arbiter.

### 7.5 Forward compatibility with M3+

When M3 introduces theory seeds with declared axioms, the M3
dispatcher (or successor) gains a "consult declared conventions"
step before classifying as `OutsideFragment(CONTESTED_CONVENTION)`.
That step is M3+ work and is **not** in M2 — for M2 the user must
either rephrase the query to avoid the contested case, or accept
the OutsideFragment rejection. The M2 rejection message hints at
the M3 path so users understand the limitation is not permanent.

---

## 8. The §2 prime example end-to-end

This is the canonical mixed-goal demo (per `prd_milestone_2.md` §3.3
demo 1). Hand-traced for the design.

### 8.1 KB

```
prime(2).
prime(3).
prime(5).
prime(7).
```

### 8.2 Query

After parsing (per `prd_milestone_2.md` §11):

```
goals = (
    Atom("prime", (Meta("?P", Integer()),)),
    Atom(">", (Meta("?P", Integer()), Const(2))),
    Atom("<", (Meta("?P", Integer()), Const(6))),
    Atom("!=", (Meta("?P", Integer()), Const(4))),
)
```

### 8.3 The trace (one user picks `prime(5)`)

| Step | Goal (post-subst) | Decision | Action | Result | Subst |
|---|---|---|---|---|---|
| 1 | `prime(?P)` | `KB` | clause-picker presents 4 candidates; user picks `prime(5)` | `ClauseResolvedStep` | `{?P: 5}` |
| 2 | `5 > 2` | `Z3` | dispatcher: ground atom; short-circuit verify via `arithEval` (§11.5) | `UniqueSolution(binding={})`; `DispatcherResolvedStep` with `ground_atom=Atom(">", (Const(5), Const(2)))` | `{?P: 5}` |
| 3 | `5 < 6` | `Z3` | same as step 2 | step | `{?P: 5}` |
| 4 | `5 != 4` | `Z3` | same | step | `{?P: 5}` |

History after step 4: `(ClauseResolvedStep(prime(5)),
DispatcherResolvedStep(5>2), DispatcherResolvedStep(5<6),
DispatcherResolvedStep(5!=4))`. The renderer walks this list to
produce the proof (see RENDER_M2_DESIGN.md §6).

### 8.4 Alternative trace (user picks `prime(2)` first)

| Step | Goal | Result |
|---|---|---|
| 1 | `prime(?P)` | user picks `prime(2)`; subst `{?P: 2}` |
| 2 | `2 > 2` | dispatcher → arithEval → `EvaluationFalse` → `NoSolution` |

`manual_solve` returns `None`. REPL prints "no solution along this
path." User uses `back` to undo the pick, picks `prime(5)`, and
re-dispatches goal 2 onwards. This is the M1 backtracking model
extended to dispatcher steps — `DispatcherResolvedStep`s are
popped on `back` exactly like `ClauseResolvedStep`s.

### 8.5 The dispatcher does not synthesise finite domains

Note that the dispatcher never asks Z3 "what value of ?P satisfies
prime(?P) ∧ ?P > 2 ∧ ?P < 6 ∧ ?P != 4 simultaneously." That would
require translating the KB's `prime/1` predicate into a Z3
finite-domain constraint, which is automated inference (M3 work).
For M2, the user's clause picks supply the finite-domain choice
manually. This is consistent with the "manual mode" framing of M1
and M2.

---

## 9. Z3 context lifecycle

Per `prd_milestone_2.md` §5.2, the tentative decision was "one
persistent context per dispatcher session." This design **confirms**
that decision.

### 9.1 The decision

`Dispatcher` holds one `Z3Bridge` instance, which holds one
`z3.Context`, created at `Dispatcher.__init__`. All Z3 variable
declarations and solver instances are pinned to that context.

### 9.2 Why one persistent context

- **Cheaper.** Z3 context creation is non-trivial; per-dispatch
  context churn would dominate small queries.
- **Variable identity is stable across goals.** `Meta("?P")` declared
  for goal 2 (`?P > 2`) is the same Z3 variable as the one declared
  for goal 3 (`?P < 6`). Caching the Z3 declaration in the bridge
  preserves identity automatically; with fresh contexts per call,
  the bridge would have to re-declare and the goal-by-goal model
  flow would risk subtle identity bugs.
- **The "proof = true" parameter (per the prep report §2(h)) only
  takes effect at context creation.** A persistent context lets us
  set this once. M2 doesn't extract Z3 proofs (per `prd_milestone_2.md`
  §4 commitment), but a single context is the only way to evolve to
  proof-extraction later if we ever want to (we don't, but it costs
  nothing to leave the option open).

### 9.3 The reset boundary

Each dispatcher call to Z3 uses a **fresh `z3.Solver`** within the
persistent context. Solver instances hold assertion stacks; using
fresh solvers means assertions from goal N do not leak into goal
N+1. The Z3 idiom for this is:

```python
solver = z3.Solver(ctx=self.context)
solver.add(*constraints)
result = solver.check()
```

Across goals, the bridge re-declares `z3.Int("?P", ctx=self.context)`
when the same meta name appears (Z3 caches variable identity by
name+context, so this is cheap). The bridge's variable-cache is
implementation-detail; the dispatcher does not see it.

### 9.4 Failure modes

- **Context corruption.** If a Z3 assertion or query somehow corrupts
  the context (extremely rare; likely indicates a Z3 bug), all
  subsequent dispatches in the same session fail. The dispatcher
  treats this as a development-time crash (raise an unhandled
  exception). A REPL session may need restart. Acceptable.
- **Cross-context variable reference.** If the bridge accidentally
  declares a variable in a different context than the solver
  uses, Z3 raises `Z3Exception`. The bridge handles this by
  catching and re-raising as `Z3BridgeError` for the dispatcher to
  treat as Case 1. Solver/kernel disagreement, crash.

### 9.5 SymPy is stateless

Per `prd_milestone_2.md` §5.2, **confirmed.** SymPy operations are
pure functions on SymPy expression trees. The `SymPyBridge` is a
thin function-style wrapper with no instance state beyond the
import handle. One bridge instance per dispatcher is fine, but
multiple instances would also work; there is no shared state.

---

## 10. Logging schema (extends `log/schema.md` to v2)

Per `prd_milestone_2.md` §12.3, the schema bumps to v2. v1 logs
remain readable.

### 10.1 New event types

```jsonl
{"event": "dispatch_classify",
 "hlmr_log_version": 2,
 "ts": "...",
 "goal": <serialised Atom|Equals>,
 "subst_pre": <serialised Substitution>,
 "decision": {"target": "kb"|"z3"|"sympy"|"rejected",
              "reason": "...|null",
              "detail": "..."}}

{"event": "dispatch_route",
 "hlmr_log_version": 2,
 "ts": "...",
 "goal": <serialised>,
 "target": "z3"|"sympy",
 "timeout_ms": <int>}

{"event": "solver_call",
 "hlmr_log_version": 2,
 "ts": "...",
 "solver": "z3"|"sympy",
 "constraints": <stringified>,        # opaque to schema
 "elapsed_ms": <int>}

{"event": "solver_result",
 "hlmr_log_version": 2,
 "ts": "...",
 "solver": "z3"|"sympy",
 "result_kind": "Z3Sat"|"Z3Unsat"|"Z3Unknown"|"Z3Timeout"
                |"SymPyFiniteRoots"|"SymPyNoRealRoots"
                |"SymPyConditionSet"|"SymPyError",
 "summary": "..."}                   # short opaque summary

{"event": "verify_arith",
 "hlmr_log_version": 2,
 "ts": "...",
 "ground_atom": <serialised>,
 "result": "ok"|"evaluation_false"|"malformed_arithmetic"}

{"event": "dispatch_outcome",
 "hlmr_log_version": 2,
 "ts": "...",
 "outcome_kind": "UniqueSolution"|"MultipleSolutions"
                  |"InfinitelyManySolutions"|"NoSolution"
                  |"Underdetermined"|"OutsideFragment",
 "binding": <serialised|null>,
 "free_metas": <list[str]|null>,
 "outside_fragment_reason": "transcendental"
                              |"contested_convention"
                              |"unrecognised_shape"
                              |"non_linear_beyond_sympy"
                              |"solver_timeout"
                              |"solver_unknown"|null}
```

The `solver_result` and `verify_arith` event pair brackets every
solver call. The `dispatch_outcome` event is the dispatcher's final
verdict; it ties to the renderer step (when present) by being the
event immediately before a `step_emit` log entry (existing M1 event,
extended to record the new step type).

### 10.2 v1 backward compatibility

Per `prd_milestone_2.md` §12.3, v1 logs continue to be parseable.
The reader checks `hlmr_log_version`; for v1, all M2 events simply
do not appear. v2 events appearing in a v1-claiming log file are a
schema mismatch and the reader raises a typed error.

### 10.3 What is not logged

- Z3's full constraint dump (proprietary-ish format; verbose). The
  `constraints` field is a short stringified summary like
  `"P > 2 AND P < 6 AND P != 4"`.
- The full Z3 model (could contain large expressions). The
  `binding` field is the serialised `Substitution` post-extraction.
- Z3 proof objects. Per `prd_milestone_2.md` §4, M2 does not consume
  Z3's proof calculus; logging it would be misleading and large.

---

## 11. Failure modes

### 11.1 Solver timeout

Z3 or SymPy exceeds `Dispatcher.timeout_ms`. Outcome:
`OutsideFragment(SOLVER_TIMEOUT, "...")`. Step is None. The user
sees an honest "the solver couldn't finish in time" message. The
REPL allows raising the timeout (`:set timeout 30000`) and re-running.

### 11.2 Solver "unknown"

Z3 returns `unknown` (e.g. on a non-linear constraint Z3 cannot
decide). Outcome: `OutsideFragment(SOLVER_UNKNOWN, "...")`. Same
treatment as timeout from the user's perspective.

### 11.3 OutsideFragment threading

When `manual_solve` receives an `OutsideFragment` outcome from the
dispatcher, it returns a sentinel that the REPL displays as the
honest-rejection message. The exact return shape is:

```python
def _outside_fragment_signal(reason: OutsideFragment) -> None:
    # manual_solve returns None for any failure mode in M1; M2
    # extends this by attaching the OutsideFragment record to the
    # session log so the REPL can display a meaningful reason
    # without an out-of-band error channel.
    self.last_outside_fragment = reason
    return None
```

The REPL checks `dispatcher.last_outside_fragment` after every
`manual_solve` call that returns `None` and displays the reason.
M1's existing "no solution" path remains for `NoSolution` cases.

This avoids changing `manual_solve`'s return type beyond the
existing `(subst, proof) | (subst, None) | None` triple while
giving the REPL enough context to be helpful.

**Lifecycle.** `last_outside_fragment` is cleared at the start of
every `dispatch()` call (the first action in the method body) and
set if and only if that call's outcome is `OutsideFragment`. After
`dispatch()` returns, the field reflects the most recent call's
`OutsideFragment` status, or `None` if the most recent call was not
`OutsideFragment`. This ensures a long-lived Dispatcher (across an
interactive REPL session) does not carry a stale `OutsideFragment`
into subsequent calls — the REPL polls the field after every
`manual_solve` returning `None`, and the field correctly reflects
only the current call's outcome.

### 11.4 Bridge crash

A Z3 or SymPy bridge raises an unexpected exception. The dispatcher
catches it, wraps it in `DispatchError`, and re-raises. This is a
development-time crash. The REPL session terminates; the user sees a
stack trace. Acceptable for M2.

### 11.5 Ground-atom short-circuit

When `classify()` returns `Z3` or `SYMPY` and the goal is already
**fully ground** (no metas after applying `subst`), the dispatcher
SHOULD short-circuit and call `_verify_arith_ground` directly,
skipping the solver. This:

- Saves a Z3/SymPy round-trip on goals like `5 > 2`.
- Produces the same `DispatchResult` as the solver path would have
  (the solver would have returned trivially-sat with an empty
  binding extension).
- Reduces dispatcher logging chatter (the `solver_call` and
  `solver_result` events are skipped; only `verify_arith` is
  logged).

This is an optimisation, not a soundness requirement. Implementer
may include or skip; tests should pass either way.

### 11.6 Verification round-trip soundness backstop

A test (`tests/test_dispatch_soundness_backstop.py`, new file) simulates
a malicious Z3 bridge that returns `?P = 4` for the constraints
`?P > 2 AND ?P < 6 AND ?P != 4`. The dispatcher's verify step
constructs `Atom(">", (Const(4), Const(2)))` (etc.; the original
constraint is `?P != 4` which becomes `4 != 4`, false), and
`arithEval` rejects with `EvaluationFalse`. The dispatcher raises
`SolverKernelDisagreement`. The test asserts the exception is
raised. Mirrors M0's `99_BAD_*` proofs and M1's renderer kernel-
rejection test.

---

## 12. Worked examples

### 12.1 The §2 prime example (demo 1)

Hand-traced in §8. Here is the dispatcher's view goal-by-goal,
assuming the user picks `prime(5)` at step 1.

| Goal | classify() | dispatch() outcome |
|---|---|---|
| `prime(?P)` | `KB` | (handled by manual_solve, not dispatcher) |
| `5 > 2` | `Z3` | `UniqueSolution(binding={})` + step |
| `5 < 6` | `Z3` | `UniqueSolution(binding={})` + step |
| `5 != 4` | `Z3` | `UniqueSolution(binding={})` + step |

All four `UniqueSolution`s; `manual_solve` collects them and asks
the renderer to produce the final proof.

### 12.2 The quadratic (demo 2)

Query: `?- root_of(?X, x^2 - 5*x + 6).`

(`x` is a placeholder for the SymPy variable in `root_of`'s second
argument; the parser produces a SymPy-friendly representation. The
M2 PRD §6.2 lists `root_of/2` as a distinguished predicate. By
convention the second argument's `Var("x")` is the SymPy variable;
the first argument's `Meta("?X")` is the unknown to solve for.)

| Goal | classify() | dispatch() outcome |
|---|---|---|
| `root_of(?X, x^2 - 5x + 6)` | `SYMPY` | `MultipleSolutions(solutions=({?X: 2}, {?X: 3}))` |

The user sees both solutions and picks one (or asks for both
proofs). For each chosen witness, `manual_solve` re-runs with that
binding, the renderer emits an `arithEval` line for `2 == 0`? No —
wait. The semantic of `root_of(?X, p)` is `p[X := ?X] = 0`. The
verification atom is `Equals(p[X := 2], Const(0))` =
`Equals(Func("-", (Func("+", (Func("^", (Const(2), Const(2))),
Func("*", (Const(-5), Const(2))))), Const(6))), Const(0))` (the
specific encoding depends on the parser; the design is structure-
agnostic). `arithEval` evaluates the lhs: `2^2 + (-5)*2 + 6 = 4 - 10
+ 6 = 0`. RHS is 0. Accept.

For ?X = 3: `3^2 + (-5)*3 + 6 = 9 - 15 + 6 = 0`. Accept.

### 12.3 Linear system (demo 3)

Query: `?- plus(?X, ?Y, 10), ?X > 0, ?X < ?Y.`

| Goal | classify() | dispatch() outcome |
|---|---|---|
| `plus(?X, ?Y, 10)` | `Z3` | adds `?X + ?Y == 10` to assertions; sat with model `{?X: 1, ?Y: 9}` (or whatever Z3 picks); detect underdetermination via add-negation-and-recheck — sat → `Underdetermined` |
| (loop terminates here) | | |

`manual_solve` receives `Underdetermined` and returns `(subst,
None)`. The REPL prints "underdetermined: many solutions exist,
constrain further."

If the user adds the constraint `?X > 0`:

| Goal | classify() | dispatch() |
|---|---|---|
| `plus(?X, ?Y, 10), ?X > 0` | each goal classified | first goal → Underdetermined; second goal → Z3 |

In the goal-by-goal model, `plus` is dispatched first; if it's
underdetermined, the dispatcher returns `Underdetermined` for that
single goal. Only when `plus` has a unique witness does the next
goal run.

A subtler interaction: the user might want Z3 to consider all four
constraints jointly (as a system). The goal-by-goal model doesn't
do that. To make this demo work, the user can submit the
constraints in an order Z3 finds determinate:

`?- ?X > 0, ?X < ?Y, plus(?X, ?Y, 10).`

Even here, goal 1 (`?X > 0`) is underdetermined alone. Z3 returns
sat with arbitrary `?X = 1`; add-negation-and-recheck → sat → second
model exists → `Underdetermined`.

This is a real limitation of the goal-by-goal model. M3's joint-
solve mode addresses it; M2 is honest that "all satisfying
solutions" requires either joint-solve (M3) or the user supplying
constraints tight enough that goal-by-goal binds uniquely. Demo 3's
exact phrasing in `prd_milestone_2.md` §3.3 should be revised
during implementation to one that goal-by-goal handles cleanly —
e.g. with a finite-domain bound like `?X ∈ {1, 2, 3, 4, 5}` added.
Mark this as an implementer follow-up; the dispatcher design itself
is consistent.

### 12.4 OutsideFragment (demo 4)

Query: `?- root_of(?X, 2^x + x^2 - 5).`

| Goal | classify() | result |
|---|---|---|
| `root_of(?X, 2^x + x^2 - 5)` | `REJECTED(TRANSCENDENTAL)` | `OutsideFragment(TRANSCENDENTAL, "...")` |

`manual_solve` returns `None` with `last_outside_fragment` set.
REPL prints honest rejection. No proof produced.

### 12.5 Case 1 — synthetic solver/kernel disagreement

A test scenario, not a real demo. Construct a fake `Z3Bridge` that
returns `Z3Sat({?P: 4})` for the constraint `?P > 5`. The dispatcher's
verify step produces `Atom(">", (Const(4), Const(5)))`, which
`arithEval` rejects with `EvaluationFalse`. The dispatcher raises
`SolverKernelDisagreement`. Test passes if the exception is raised.

Live in `tests/test_dispatch_soundness_backstop.py` (§11.6).

### 12.6 Case 2 — contested-convention rejection

Query: `?- root_of(?X, ?X^?X - 1).`

`root_of(?X, ?X^?X - 1)` requires solving `?X^?X = 1`. SymPy may
return `?X = 1` (cleanly: `1^1 = 1`), but the `?X = 0` solution
(under the combinatorics convention) is also "satisfying."

If SymPy returns only `?X = 1`: dispatcher proceeds. Verifies
`1^1 = 1`. Accept. `UniqueSolution`.

If SymPy returns both `?X = 1` and `?X = 0` as roots, the §3.1
partitioning runs:
- For `?X = 1`: verify `Equals(Func("^", (Const(1), Const(1))),
  Const(1))` → arithEval accepts. Class (a) — joins the valid set.
  A pre-built `DispatcherResolvedStep` records the witness.
- For `?X = 0`: verify `Equals(Func("^", (Const(0), Const(0))),
  Const(1))` → arithEval rejects with `MalformedArithmetic` (per
  ARITH_EVAL_DESIGN.md §11.3 M14). The dispatcher's contested-shape
  detector (§7.3) returns True for the `Func("^", (Const(0),
  Const(0)))` subterm. Class (b) — Case 2 contested rejection.
  The witness is logged informationally (`_log_contested_rejection`,
  §10) and DROPPED from the result. It does not become a dispatch
  outcome of its own.

Outcome narrowing per §3.1: one valid witness remains, so the
dispatcher returns `UniqueSolution(binding={?X: Const(1)})` with the
single pre-built step. The dropped contested witness surfaces in
the REPL as an informational note ("another candidate (`?X = 0`)
was rejected because it depends on a contested mathematical
convention; see strategic_direction.md §6.9 for context"), not as a
dispatch outcome.

The general rule, restated for emphasis: **contested-witness
rejections are filtered, not propagated as outcomes.** A
`MultipleSolutions` outcome reaching `manual_solve` always carries
≥2 verified valid witnesses; partial-contested inputs that reduce
the valid set to <2 are narrowed by the dispatcher to
`UniqueSolution` (1 valid) or `NoSolution` (0 valid) per §5.3. The
contested-rejection metadata lives in the session log, not the
outcome ADT.

### 12.7 Underdetermined — the M1 universal-fact case

Query: `?- p(?A).` against KB `p(X).`

| Step | Goal | Decision | Result |
|---|---|---|---|
| 1 | `p(?A)` | `KB` | user picks `p(X)`; SLD renames X→?X_1; subst becomes `{?A: ?X_1}` |

After all goals consumed, `manual_solve` runs `_saturate(subst)` =
`{?A: ?X_1}`. The query meta `?A` is not ground (resolves to a
Meta). Per HARDENING_FINDINGS.md fix, `manual_solve` returns
`(subst, None)`. The REPL prints "Goal resolved but no ground
witness — query is underdetermined."

The dispatcher is not involved (the goal was KB-routed). But the
**outcome shape** is the same `Underdetermined` ADT defined in §3.1
of this document, generalising M1's case.

### 12.8 Underdetermined — the M2 solver-side case

Query: `?- ?X + ?Y = 10.` (no further constraints)

| Step | Goal | Decision | Result |
|---|---|---|---|
| 1 | `Equals(?X + ?Y, 10)` | `Z3` | Z3 returns sat `{?X: 5, ?Y: 5}` (arbitrary); add-negation-and-recheck → sat → `Underdetermined({?X: 5, ?Y: 5}, ("?X", "?Y"))` |

`manual_solve` returns `(subst, None)`. REPL prints
"Underdetermined: example solution X=5, Y=5; many others exist."

---

## 13. Coordination notes for the renderer (`RENDER_M2_DESIGN.md`, Task C)

The dispatcher and renderer are coupled at:

### 13.1 The SLDStep variants (§3.4)

Both designs agree on `ClauseResolvedStep` and
`DispatcherResolvedStep` with the field shapes specified in §3.4.
The renderer pattern-matches on the variant and emits one of:
- For `ClauseResolvedStep`: M1-style `Premise` / `forallE` / `andI`
  / `impE` lines.
- For `DispatcherResolvedStep`: a single `arithEval` line with
  `formula = step.ground_atom`, `RuleApp("arithEval", (), (), {})`,
  and `box_depth = 0`.

### 13.2 Witness-verification timing

The dispatcher's verify step runs **before** the
`DispatcherResolvedStep` is appended to `state.history`. The
renderer therefore never receives a step containing an unverified
ground atom. If the dispatcher's verify step fails (Case 1 or Case
2), no step is emitted; `manual_solve` either crashes (Case 1) or
returns `None` with `last_outside_fragment` set (Case 2). The
renderer is never asked to render a Case-1 or Case-2 path.

This is a critical invariant: the renderer's input is only well-
formed verified steps. The renderer can therefore assume every
`DispatcherResolvedStep.ground_atom` is `arithEval`-acceptable, and
its emitted `arithEval` lines pass the kernel by construction.

### 13.3 Mixed-goal rendering order

The dispatcher emits steps in goal-evaluation order (left-to-right
through the query tuple). `state.history` therefore reflects the
logical dependency order. The renderer walks the history in this
order, producing line numbers that respect goal dependency.

For mixed queries like the §2 prime example, the rendered proof has
`prime(5)` lines first (from the `ClauseResolvedStep`), then the
three `arithEval` lines for the inequalities. RENDER_M2_DESIGN.md
specifies the exact line layout.

### 13.4 The Case 2 (contested-rejection) flow

When the dispatcher returns `OutsideFragment(CONTESTED_CONVENTION,
...)`, no step is emitted, no proof is rendered. The user sees the
honest-rejection message from the REPL. The renderer is not called.
This is the natural extension of the M1 pattern where failed
clause-picks abort proof rendering.

### 13.5 The renderer's rule-alphabet contract

The renderer must emit only rules in the M2 alphabet `{Premise,
forallE, andI, impE, arithEval, eqRefl}`. The sixth rule, `eqRefl`,
is the M0 reflexivity rule (`src/hlmr/kernel/rules.py:_eqRefl`); the
M2 renderer reuses it for `Equals(t, t)` instances where both sides
are syntactically identical, per the policy in ARITH_EVAL_DESIGN.md
§5.3 and RENDER_M2_DESIGN.md §4.4. RENDER_M2_DESIGN.md §2 is the
canonical alphabet definition.

RENDER_M2_DESIGN.md §10.3 specifies a property test asserting that
no other rule names appear in any rendered M2 proof. The dispatcher
honours the contract by ensuring its
`DispatcherResolvedStep.ground_atom` is a syntactic shape both
`arithEval` and (when applicable, for syntactically-reflexive
equalities) `eqRefl` accept. Both rules are zero-ref / zero-box /
zero-extra; the dispatcher emits the same `RuleApp(..., (), (), {})`
shape for either, and the renderer chooses the rule name per its
§4.4 algorithm.

---

## 14. Coordination with existing modules

### 14.1 `solvers/` (Z3 and SymPy bridges)

Per `prd_milestone_2.md` §8, the bridges expose typed return values
(`Z3Sat`, `Z3Unsat`, `Z3Underdetermined`, `Z3Unknown` for Z3;
`SymPyFiniteRoots`, `SymPyNoRealRoots`, `SymPyConditionSet`,
`SymPyError` for SymPy). The dispatcher consumes these via match
statements. The bridges' exact public method signatures are decided
during their implementation; this design lists the return-type set
the dispatcher reads.

The dispatcher does NOT call the bridges' internal solver objects
directly. All Z3/SymPy interaction is mediated by the bridge,
keeping `dispatch/` independent of solver-library specifics.

### 14.2 `unify/` (M1)

The dispatcher calls `apply_to_formula` and `compose` from
`unify.substitution`. Substitution semantics (compose
associativity, idempotence) are M1's existing contract and
unchanged.

### 14.3 `solve/sld.py` and `solve/__init__.py:manual_solve`

The dispatcher is not a hard dependency of `solve/`; `solve/` works
without a dispatcher (M1 mode). When a dispatcher is supplied,
`manual_solve` calls `dispatcher.classify` and `dispatcher.dispatch`
per the loop in §6.1. The new `DispatcherResolvedStep` type lives in
`solve/sld.py` (where `SLDStep` becomes the discriminated union),
not in `dispatch/`. `dispatch/` imports the new types from
`solve.sld`.

### 14.4 `solve/render.py`

Extended per RENDER_M2_DESIGN.md to handle
`DispatcherResolvedStep`. No imports from `dispatch/` — the
renderer reads only the IR shape of the step (route, ground_atom),
which lives in `solve/sld.py`.

### 14.5 `repl/`

Per `prd_milestone_2.md` §12, the REPL gains a `:solver` command
showing each goal's classification, and adds outcome-display
formatters for the six outcomes. The REPL imports `dispatch/`'s
public surface (`Dispatcher`, `DispatchOutcome`, the six outcome
classes) for display formatting. The `last_outside_fragment` field
on the dispatcher (§11.3) is read by the REPL after `None`-return
from `manual_solve`.

### 14.6 `log/`

Per `prd_milestone_2.md` §12.3, `log/recorder.py` extends to emit
the v2 events listed in §10.1. The dispatcher receives a logger
handle at construction and emits events at classify, route,
solver-call, solver-result, verify, and outcome boundaries. The
schema doc at `src/hlmr/log/schema.md` is updated by Sonnet during
implementation to enumerate the v2 fields. Schema versioning per
M1's existing pattern.

---

## 15. Non-goals

Explicit out-of-scope items, surfaced because they are real
temptations:

1. **Joint solve over all goals.** Giving Z3 the entire query at
   once. Requires the dispatcher to extract finite-domain content
   from KB clauses (e.g. `prime/1` → `?P ∈ {2, 3, 5, 7}`). This is
   automated inference; defer to M3.
2. **Z3 proof-tree consumption.** Per `prd_milestone_2.md` §4 and
   the prep report, Z3's proof calculus is not converted to Fitch
   ND. Witnesses are verified by `arithEval`, not by translating
   Z3's proof.
3. **SymPy `nsolve` / numerical fallback.** Per `prd_milestone_2.md`
   §3.2 and §5.1, transcendentals are `OutsideFragment`. No
   floating-point solutions.
4. **Heuristic / probabilistic classification.** All classification
   is rule-based and conservative. No "if it looks linear" guesses.
5. **Cross-goal optimisation.** Each goal is dispatched
   independently. No "if I solve goal 3 first, goal 2 becomes
   trivial." This is search engineering; M3.
6. **A learned classifier.** The classifier is hand-written rules.
   M3 may add an optional learned re-ranker for proof-search; the
   dispatcher's classifier is not in that scope.
7. **Negation, cut, `findall`, `assert`/`retract`.** Per
   `prd_milestone_2.md` §3.2, these stay out of the KB syntax.
8. **Multi-sort logic.** `prd_milestone_2.md` §3.2 keeps M2 to a
   single sort with typed metas (Integer, Rational,
   FiniteDomain, Categorical). Multi-sort decision is M4.
9. **Theory libraries / declared axioms in the KB.** Per
   `docs/strategic_direction.md` §6.9, declared-convention axioms
   for `0^0` etc. are M3+ work. The M2 dispatcher rejects with
   `OutsideFragment(CONTESTED_CONVENTION)` and points at the M3
   path; it does not accept axioms in M2.

---

## 16. Implementer summary

What Sonnet should produce against this design, in approximate order:

1. **`src/hlmr/dispatch/__init__.py`** — re-exports the public
   surface listed in §3.

2. **`src/hlmr/dispatch/classify.py`** — pure classification
   function per §4 plus the `_is_contested_when_ground` detector
   per §7.3. ~150 lines. No solver imports.

3. **`src/hlmr/solve/sld.py`** — refactor `SLDStep` into the
   discriminated union (`ClauseResolvedStep` and
   `DispatcherResolvedStep`) per §3.4. M1 callers updated to use
   `ClauseResolvedStep`. Test-enforced backward equivalence: every
   M1 demo and test still produces identical proofs after the
   refactor.

4. **`src/hlmr/dispatch/route.py`** — `Dispatcher` class per §3.3
   and §5. Owns `Z3Bridge` and `SymPyBridge` instances. Implements
   the dispatch loop, verify-before-return, and the case-1/case-2
   discriminator. ~400 lines.

5. **`src/hlmr/solve/__init__.py:manual_solve`** — extend per §6.1
   (the integration loop). Existing M1 behaviour retained when
   `dispatcher=None`.

6. **`src/hlmr/solvers/`** — Z3 and SymPy bridges (separate task,
   per `prd_milestone_2.md` §8). The dispatcher tests can mock these
   for unit tests; integration tests use the real bridges.

7. **`src/hlmr/log/recorder.py`** — v2 events per §10.1.

8. **`src/hlmr/log/schema.md`** — schema documentation update.

9. **`src/hlmr/repl/commands.py`** and **`interactive.py`** —
   `:solver` command, outcome display formatters,
   `last_outside_fragment` reading.

10. **Tests** — `tests/test_dispatch_classify.py`,
    `tests/test_dispatch_route.py` (with mock bridges),
    `tests/test_dispatch_integration.py` (with real bridges; runs
    each demo end-to-end), `tests/test_dispatch_soundness_backstop.py`
    (Case 1 crash test), `tests/test_underdetermined_unified.py`
    (both M1 universal-fact and M2 solver-side cases produce the
    same `Underdetermined` outcome shape).

The full diff for `dispatch/` itself is ~600 lines plus tests.
`solve/sld.py` and `solve/__init__.py` see modest extensions
(~100 lines combined). Bridges and logging are separate work.

---

## 17. Checklist against `prd_milestone_2.md` §9

| §9 deliverable | Where in this doc |
|---|---|
| Module shape and public API surface | §2, §3 |
| Constraint classification rules | §4 |
| Conservative-default principle | §4.2 (rule C7), §4.4 |
| The six outcomes precisely defined | §3.1 |
| Mapping Z3/SymPy results to outcomes | §5.2, §5.3 |
| Witness verification round-trip | §5.4, §5.5 |
| Solver disagreement → development crash | §7.2 |
| Conventions-as-axioms (Case 2) interaction | §7 (entire) |
| The mixed-goal seam with SLD | §6 |
| Z3 context lifecycle | §9 |
| SymPy stateless | §9.5 |
| Logging schema (v2 fields) | §10 |
| Failure modes | §11 |
| Worked examples (each demo, Case 1, Case 2) | §8, §12 |
| Coordination with renderer (Task C) | §13 |
| Soundness backstop test | §11.6, §12.5 |
| Underdetermined unification (M1 + M2) | §3.1, §12.7, §12.8 |

All §9 items addressed. Ready for review alongside RENDER_M2_DESIGN.md.
