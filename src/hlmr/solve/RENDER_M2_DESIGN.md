# SLD-trace-to-Fitch-proof renderer — M2 extension

**Status:** Design v1 (Opus 4.7). No code in this document; pseudocode only.
**Implements:** `prd_milestone_2.md` §10 (Task C in §13.2).
**Target reader:** Sonnet 4.6 implementing against this spec, in `src/hlmr/solve/render.py`.
**Extends:** `src/hlmr/solve/RENDER_DESIGN.md` (M1, shipped). Read that document first; this design adds to it without rewriting it.
**Companion designs:** `src/hlmr/kernel/ARITH_EVAL_DESIGN.md` (Task A, v1.1, **approved**) — the contract the renderer's `arithEval` lines must satisfy. `src/hlmr/dispatch/DISPATCH_DESIGN.md` (Task B, this session) — defines the new `DispatcherResolvedStep` type the renderer reads.

---

## 1. Purpose

Extend the M1 SLD-to-ND renderer to handle dispatcher-resolved SLD
steps (per Task B) and emit the new `arithEval` rule line they
correspond to (per Task A).

**Headline observation, restated for M2.** For every M2 query and
demo, the rendered proof remains a **flat, depth-0 ND proof using
only six rules**: the M1 set `{Premise, forallE, andI, impE}` plus
the new `arithEval` (Task A) and — for syntactically-reflexive
arithmetic equalities — `eqRefl` (which the M0 kernel already
provides; the renderer reuses it). No assumptions, no boxes, no
classical reasoning.

The M2 alphabet is therefore `{Premise, forallE, andI, impE,
arithEval, eqRefl}`. Anything else in a rendered M2 proof line is a
smell and indicates the implementer has gone off-spec. A property
test asserts this (§10).

**What this design adds, in scope terms:**

- A new emit path for `DispatcherResolvedStep` history entries: each
  becomes one `arithEval` line (or one `eqRefl` line in the
  syntactically-reflexive subcase, §5).
- An algorithm extension for multi-goal queries (M2 introduces
  these per `prd_milestone_2.md` §11): the rendered proof's final
  line is the and-chained conjunction of every instantiated goal,
  built by `andI` from the per-goal subproofs.
- A reaffirmed flat-depth-0 invariant: the M2 renderer does not
  produce boxed `arithEval` lines, even though the kernel would
  accept them (§7).

**What does NOT change.** The M1 renderer's premise emission, its
`forallE` chain for clause heads, its `andI` left-association for
clause bodies with multiple atoms, and its `impE` step are all
unchanged. The M2 implementation is **additive** — modify
`render.py`, do not rewrite it.

---

## 2. The M2 alphabet

| Rule | Used for | First introduced |
|---|---|---|
| `Premise` | KB clauses appearing in the trace (one per clause) | M1 |
| `forallE` | instantiating a clause head's universal quantifier | M1 |
| `andI` | combining body atoms before applying `impE`; combining per-goal subproofs at the end of a multi-goal query | M1 |
| `impE` | applying a clause's instantiated implication to its body | M1 |
| `arithEval` | dispatcher-resolved arithmetic atoms (non-reflexive) | M2 (Task A) |
| `eqRefl` | dispatcher-resolved arithmetic equalities `Equals(lhs, rhs)` where `lhs == rhs` syntactically | M0 (already in kernel; M2 renderer is the first SLD-renderer that emits it) |

The M2 alphabet has **six** rules. The M1 alphabet had four. M2's
addition is `arithEval` (Task A's new rule) and `eqRefl` (an existing
M0 rule, reused for the trivial reflexive subcase of arithmetic
equality — see §5).

`eqSubst`, `existsI`, `existsE`, `forallI`, `notI`, `notE`, `botE`,
`PBC`, `iffI`, `iffE_L`, `iffE_R`, `orI_L`, `orI_R`, `orE`, `andE_L`,
`andE_R`, `reit`, `impI` — all in the kernel, none emitted by the M2
renderer.

---

## 3. The SLDStep variants the renderer reads

Defined in `src/hlmr/solve/sld.py` (refactored per
`DISPATCH_DESIGN.md` §3.4). The renderer pattern-matches on the
variant and chooses the emit path.

```python
# Recap from DISPATCH_DESIGN.md §3.4:

@dataclass(frozen=True)
class ClauseResolvedStep:
    goal_resolved: Atom | Equals     # post-substitution
    clause_used: Clause
    clause_renamed: Clause
    unifier: Substitution            # accumulated subst after step

@dataclass(frozen=True)
class DispatcherResolvedStep:
    goal_resolved: Atom | Equals     # post-substitution
    ground_atom: Atom | Equals       # post-binding, fully ground
    route: RouteTarget               # Z3 or SYMPY
    binding_added: Substitution
    solver_summary: str

SLDStep = ClauseResolvedStep | DispatcherResolvedStep
```

> **Renderer invariant — verify-before-step.** Per
> DISPATCH_DESIGN.md §13.2, the dispatcher's `_verify_arith_ground`
> step runs *before* a `DispatcherResolvedStep` is appended to
> `state.history`. The renderer can therefore assume:
>
> - `step.ground_atom` is fully ground (no `Var`, no `Meta`).
> - `step.ground_atom` is in `arithEval`'s evaluable set (per
>   ARITH_EVAL_DESIGN.md §5).
> - `arithEval` will accept `step.ground_atom` when `check_proof`
>   is run on the rendered proof.
>
> The renderer relies on this invariant. If it is ever violated
> (the dispatcher accidentally appends an unverified step), the
> kernel's `check_proof` rejects the resulting proof — the
> soundness backstop in §10 catches that case.

---

## 4. The render algorithm — extended

The M1 renderer's main entry, in `src/hlmr/solve/render.py`:

```python
def render(state: SLDState,
           kb: KnowledgeBase,
           query: Atom | Equals) -> Proof:
    """Walk state.history and emit a Fitch proof whose final line
    is the instantiated query goal."""
```

M2 generalises the `query` parameter from a single literal to a
tuple of literals (per `prd_milestone_2.md` §11 multi-goal queries),
and dispatches on the new step variants. The new signature:

```python
def render(state: SLDState,
           kb: KnowledgeBase,
           query: Atom | Equals | tuple[Atom | Equals, ...]
           ) -> Proof:
    """Walk state.history and emit a Fitch proof whose final line
    is the instantiated query goal (or the and-chained conjunction
    of instantiated goals, for multi-goal queries)."""
```

### 4.1 The high-level shape

For each top-level entry in `state.history`, the renderer emits
either an M1-style subproof (for `ClauseResolvedStep`s) or a single
`arithEval` / `eqRefl` line (for `DispatcherResolvedStep`s). For
multi-goal queries, after rendering all per-goal subproofs, the
renderer emits a chain of `andI` lines that combine them into the
instantiated conjunction (the proof's `goal`).

Pseudocode:

```python
def render(state, kb, query):
    saturated = _saturate(state.subst)
    goals = (query,) if isinstance(query, (Atom, Equals)) else query

    # 1. Premise emission. Walk the history and find every clause
    #    that appears in any ClauseResolvedStep. Emit each as a
    #    Premise (M1 logic; reuse _build_premise_formula and the
    #    M1 deduplication strategy).
    premise_lines = _emit_premises(state.history)

    # 2. Per-goal subproofs. For each top-level goal in the query
    #    tuple, find its corresponding history entry and render.
    body_lines: list[ProofLine] = []
    final_line_per_goal: list[int] = []  # the line number that
                                          # holds each goal's
                                          # instantiated formula
    for i, goal in enumerate(goals):
        # The history is in goal-evaluation order; the i-th
        # top-level step corresponds to the i-th goal. (This is
        # the order coupling specified in DISPATCH_DESIGN.md §13.3.)
        # Subgoals from clause body decomposition appear nested
        # inside ClauseResolvedSteps and are handled recursively
        # by _render_step (below).
        step = _toplevel_step_for_goal(state.history, i)
        line, sub_lines = _render_step(
            step, premise_lines, body_lines, saturated, kb)
        body_lines.extend(sub_lines)
        final_line_per_goal.append(line.number)

    # 3. AndI chain for multi-goal queries.
    if len(goals) > 1:
        and_lines = _emit_and_chain(
            final_line_per_goal, body_lines, saturated, goals)
        body_lines.extend(and_lines)
        final_line = and_lines[-1]
    else:
        final_line = body_lines[-1]

    # 4. Assemble.
    all_lines = premise_lines + body_lines
    final_formula = final_line.formula
    return Proof(lines=tuple(all_lines), goal=final_formula)
```

### 4.2 Rendering one step

```python
def _render_step(step, premise_lines, body_lines, saturated, kb):
    """Emit lines for one top-level history entry. Returns
    (final_line_for_this_step, list_of_emitted_body_lines)."""
    match step:
        case ClauseResolvedStep():
            # M1 path. Reuse the existing logic in render.py:
            # forallE chain to instantiate the clause head, then
            # andI of body subproofs, then impE.
            return _render_clause_step(step, ...)  # M1 logic, unchanged

        case DispatcherResolvedStep():
            # M2 path. One arithEval (or eqRefl) line.
            return _render_dispatcher_step(step, body_lines, saturated)
```

### 4.3 Rendering a `DispatcherResolvedStep`

```python
def _render_dispatcher_step(step, body_lines, saturated):
    rule_name = _choose_equality_rule(step.ground_atom)
    next_line_number = _next_line_number(body_lines)
    line = ProofLine(
        number=next_line_number,
        formula=step.ground_atom,
        justification=RuleApp(rule=rule_name,
                              line_refs=(),
                              box_refs=(),
                              extra={}),
        box_depth=0,
    )
    return line, [line]
```

A `DispatcherResolvedStep` produces **exactly one line**. No premise
lines are added (the dispatcher's witness comes from outside the KB,
so there's no clause to introduce as a premise). No `forallE`,
`andI`, or `impE`. The line stands alone, justified by the kernel's
`arithEval` (or `eqRefl`) rule reading the formula in isolation.

### 4.4 The eqRefl-vs-arithEval policy

Per ARITH_EVAL_DESIGN.md §5.3, both rules accept the syntactically-
reflexive case (e.g. `Equals(Const(7), Const(7))`); only `arithEval`
accepts the non-reflexive case (e.g. `Equals(Func("+", (Const(3),
Const(4))), Const(7))`).

Policy: prefer `eqRefl` for syntactic reflexivity, `arithEval`
otherwise. Algorithm:

```python
def _choose_equality_rule(f: Atom | Equals) -> str:
    """Return 'eqRefl' or 'arithEval' for the given ground atom.
    Pure function on IR shape — no kernel call.

    Reflexive case:  Equals(t, t) with t identical on both sides
                     → 'eqRefl'.
    Everything else (Atoms with ordering predicates, predicate-form
    arithmetic atoms, non-reflexive Equals, Equals where lhs/rhs
    differ syntactically even if numerically equal):
                     → 'arithEval'.
    """
    match f:
        case Equals(lhs=lhs, rhs=rhs) if lhs == rhs:
            return "eqRefl"
        case _:
            return "arithEval"
```

Notes:

- The `lhs == rhs` test uses Python's `==` on frozen dataclass IR
  objects. `Const(1) == Const(Fraction(1, 1))` is `True` in Python
  (`int == Fraction(int)` is `True`, and the dataclass `__eq__`
  compares the `value` field via `==`). So a syntactically-mixed
  pair like `Equals(Const(1), Const(Fraction(1, 1)))` is treated
  as reflexive and routes to `eqRefl`. This is sound — `eqRefl`
  accepts `Equals(t, t)` whenever the IR equates `t` with itself.
- For `Atom` shapes (`<`, `>`, `<=`, `>=`, `!=`, `plus`, `minus`,
  `times`, `divides`), there is no reflexive case to handle (these
  are not equality predicates). Always `arithEval`.
- The renderer never emits `eqSubst` (M0's other equality rule) —
  not in the M2 alphabet.

### 4.5 The premise emission step (M1, restated)

Premise emission for `ClauseResolvedStep`s is M1 logic:

- Walk every `ClauseResolvedStep` in `state.history` (recursively;
  body-decomposition steps too).
- Collect the unique set of `clause_used` references.
- For each, emit one `Premise` line at the top of the proof. Facts
  emit as the head atom; rules emit as the universally-quantified
  implication form `∀v_1 ... v_n. (b_1 ∧ ... ∧ b_k) → head` (M1
  pattern).
- Premise line numbers are assigned in stable order (matches M1's
  existing deduplication).

**`DispatcherResolvedStep`s emit no premises.** A dispatcher step's
"premise" is the arithmetic axiom system itself, which the kernel
internalises as the `arithEval` rule — there is nothing to add to
the proof's premise prologue. This is consistent with the M2
alphabet not introducing new premise types.

### 4.6 The andI chain for multi-goal queries

For a multi-goal query `?- g_1, g_2, ..., g_n.` (n ≥ 2), after
rendering each per-goal subproof the renderer emits a left-
associated `andI` chain to derive the conjunction:

```
... per-goal lines, with the i-th goal's final line at index k_i ...

next.   andI of k_1 and k_2  →  (G_1 ∧ G_2)
next+1. andI of (next) and k_3  →  ((G_1 ∧ G_2) ∧ G_3)
...
next+(n-2). andI of (...) and k_n →  (((G_1 ∧ G_2) ∧ G_3) ∧ ... ∧ G_n)
```

Each `andI` line uses `RuleApp(rule="andI", line_refs=(left, right),
box_refs=(), extra={})`. The leftmost ref accumulates the running
conjunction; the right ref is the next goal's final line.

The proof's `goal` field is the final `andI` line's formula — the
fully and-chained conjunction with substitution applied.

For single-goal queries (n=1), no `andI` chain is needed; the proof's
`goal` is just the per-goal final line's formula. (M1's existing
behaviour.)

### 4.7 Top-level history splitting

The renderer needs to know which history entries correspond to which
top-level goals. The dispatcher emits steps in goal-evaluation order
(per DISPATCH_DESIGN.md §13.3), so the i-th top-level step is for
goal i. But "top-level" is the key qualifier — `ClauseResolvedStep`s
for rules introduce nested resolution for the body atoms, and those
nested steps appear in `state.history` too.

In M1, the renderer used `_build_step_tree(history)` to build a tree
where each node is a step and the tree structure reflects body-atom
decomposition. M2 reuses `_build_step_tree` unchanged: each
`DispatcherResolvedStep` is a tree leaf (no body to decompose), and
the tree's roots are the top-level steps in goal order.

The implementer can extract goal-i's tree root by walking the tree
roots in order: `tree.roots[i]` corresponds to `goals[i]`. This is
M1's structure with a small extension to recognise dispatcher steps
as leaves.

---

## 5. The eqRefl reuse — why this is sound

`eqRefl` is an M0 kernel rule (`src/hlmr/kernel/rules.py:_eqRefl`).
It accepts `Equals(t, t)` for any term `t`. The renderer emitting
`eqRefl` for ground arithmetic equalities where `lhs == rhs` is
syntactically reflexive is sound by construction — the kernel rule
itself enforces the reflexivity check.

This is **not** a kernel change. The M0 rule is unchanged; the M2
renderer simply chooses to invoke it in cases where `arithEval`
would also work. This expands the renderer's effective alphabet to
six rules without expanding the kernel's trust surface.

The choice of `eqRefl` over `arithEval` for reflexive cases is
mostly cosmetic (proofs read more cleanly with the simpler rule),
but it has one operational benefit: `eqRefl` does not invoke the
arithmetic evaluator, so for very large constants
(e.g. `Equals(Const(2**100), Const(2**100))`) the kernel check is
constant-time rather than linear in bit-length. Negligible on the
M2 demo set, but worth noting.

---

## 6. Worked rendering examples

For each of the four M2 demos in `prd_milestone_2.md` §3.3, the
hand-traced rendered proof. Inputs are (KB + final SLDState +
query); outputs are the line-by-line proof.

### 6.1 Demo 1 — the §2 prime example

**KB.**
```
prime(2).
prime(3).
prime(5).
prime(7).
```

**Query.** `?- prime(?P), greater_than(?P, 2), less_than(?P, 6),
not_equal(?P, 4).`

After parsing, the goals tuple is:
```
(Atom("prime", (Meta("?P", Integer()),)),
 Atom(">",     (Meta("?P", Integer()), Const(2))),
 Atom("<",     (Meta("?P", Integer()), Const(6))),
 Atom("!=",    (Meta("?P", Integer()), Const(4))))
```

(The PRD §3.3 description uses `greater_than`/`less_than`/`not_equal`
predicate names for readability. The parser per §11 produces operator
atoms `>`, `<`, `!=`. The renderer's behaviour is identical either
way — the dispatcher recognises both forms via §5.1 / §5.2 of
ARITH_EVAL_DESIGN.md.)

**The trace** (user picks `prime(5)` at step 1; see DISPATCH_DESIGN.md
§8 for the dispatcher view):

```
state.history = (
    ClauseResolvedStep(
        goal_resolved=Atom("prime", (Meta("?P"),)),
        clause_used=prime_5_clause,           # prime(5).
        clause_renamed=prime_5_clause,        # no vars; identity
        unifier={?P: Const(5)},
    ),
    DispatcherResolvedStep(
        goal_resolved=Atom(">", (Meta("?P"), Const(2))),
        ground_atom=Atom(">", (Const(5), Const(2))),
        route=Z3,
        binding_added={},
        solver_summary="ground 5>2; verified by arithEval",
    ),
    DispatcherResolvedStep(
        goal_resolved=Atom("<", (Meta("?P"), Const(6))),
        ground_atom=Atom("<", (Const(5), Const(6))),
        route=Z3,
        binding_added={},
        solver_summary="ground 5<6; verified by arithEval",
    ),
    DispatcherResolvedStep(
        goal_resolved=Atom("!=", (Meta("?P"), Const(4))),
        ground_atom=Atom("!=", (Const(5), Const(4))),
        route=Z3,
        binding_added={},
        solver_summary="ground 5!=4; verified by arithEval",
    ),
)
```

**Rendered proof:**

```
1. prime(5)                              Premise            (prime_5_clause)
2. (5 > 2)                               arithEval
3. (5 < 6)                               arithEval
4. (5 != 4)                              arithEval
5. (prime(5) & (5 > 2))                  andI 1, 2
6. ((prime(5) & (5 > 2)) & (5 < 6))      andI 5, 3
7. (((prime(5) & (5 > 2)) & (5 < 6)) & (5 != 4))   andI 6, 4
```

Seven lines. Final line (line 7) is the and-chained conjunction of
the four instantiated goals. `proof.goal` is set to that
conjunction. The kernel verifies:

- Line 1: `Premise` (M0 rule, depth 0 ✓).
- Lines 2–4: `arithEval` (M2 rule, ground atoms in evaluable set,
  evaluator returns True for each — see ARITH_EVAL_DESIGN.md A1, A2,
  A3 worked examples).
- Lines 5–7: `andI` (M0 rule, two refs each, both refs accessible).

All six rule applications pass the kernel.

### 6.2 Demo 2 — the quadratic

**KB.** None required (the goal routes entirely to SymPy).

**Query.** `?- root_of(?X, x^2 - 5*x + 6).`

After dispatcher routing (per DISPATCH_DESIGN.md §12.2), SymPy
returns roots `{2, 3}`. This is `MultipleSolutions`. The user via
the REPL picks one (or asks for both).

**For chosen witness `?X = 2`:**

```
state.history = (
    DispatcherResolvedStep(
        goal_resolved=Atom("root_of", (Meta("?X"), <poly_x>)),
        ground_atom=Equals(<poly_2>, Const(0)),
            # poly_2 = Func("+", (Func("+", (
            #     Func("^", (Const(2), Const(2))),
            #     Func("*", (Const(-5), Const(2))))),
            #     Const(6)))
            # = (2^2 + (-5)*2 + 6 = 4 - 10 + 6 = 0)
        route=SYMPY,
        binding_added={?X: Const(2)},
        solver_summary="sympy: roots {2, 3}; chose 2",
    ),
)
```

**Rendered proof for ?X = 2:**

```
1. ((2^2) + ((-5) * 2)) + 6 = 0          arithEval
```

One line. The arithEval evaluator computes
`((2^2) + ((-5) * 2)) + 6 = (4 + -10) + 6 = -6 + 6 = 0` and the rhs
is `0`, so `0 == 0` is True. Accept.

`proof.goal` is the single line's formula `Equals(<poly_2>,
Const(0))`. Single-goal query, no andI chain.

**For chosen witness `?X = 3`:** mirror image, replacing 2 with 3.
The arithEval evaluator gets `9 - 15 + 6 = 0`. Accept.

If the user wants both proofs, the renderer is called twice with
two different `state.history` tuples (one per witness), producing
two separate `Proof` objects — one per witness. The REPL displays
both.

### 6.3 Demo 3 — linear system

**Query.** As discussed in DISPATCH_DESIGN.md §12.3, this demo's
exact phrasing in the M2 PRD §3.3 needs goal-by-goal-friendly
constraints. Assuming a goal-by-goal-determinate version like
`?- ?X = 3, ?Y = 7, plus(?X, ?Y, 10).`:

```
state.history = (
    DispatcherResolvedStep(
        goal_resolved=Equals(Meta("?X"), Const(3)),
        ground_atom=Equals(Const(3), Const(3)),
        route=Z3,
        binding_added={?X: Const(3)},
        solver_summary="z3: ?X = 3; ground 3=3; verified",
    ),
    DispatcherResolvedStep(
        goal_resolved=Equals(Meta("?Y"), Const(7)),
        ground_atom=Equals(Const(7), Const(7)),
        route=Z3,
        binding_added={?Y: Const(7)},
        solver_summary="z3: ?Y = 7; ground 7=7; verified",
    ),
    DispatcherResolvedStep(
        goal_resolved=Atom("plus", (Meta("?X"), Meta("?Y"), Const(10))),
        ground_atom=Atom("plus", (Const(3), Const(7), Const(10))),
        route=Z3,
        binding_added={},
        solver_summary="ground plus(3,7,10); verified",
    ),
)
```

**Rendered proof:**

```
1. (3 = 3)                              eqRefl     (lhs == rhs syntactically)
2. (7 = 7)                              eqRefl     (ditto)
3. plus(3, 7, 10)                       arithEval
4. ((3 = 3) & (7 = 7))                  andI 1, 2
5. (((3 = 3) & (7 = 7)) & plus(3, 7, 10))  andI 4, 3
```

Five lines. Lines 1 and 2 use `eqRefl` because they are syntactically
reflexive. Line 3 is a non-reflexive ternary atom — `arithEval`. The
final line (line 5) is the and-chained conjunction.

> **Implementer note for the PRD.** As flagged in DISPATCH_DESIGN.md
> §12.3, the original PRD §3.3 demo 3 phrasing
> `?- plus(?X, ?Y, 10), ?X > 0, ?X < ?Y.` is genuinely under-
> determined under the goal-by-goal model (the first goal alone
> admits multiple `(?X, ?Y)` pairs and Z3's add-negation-and-recheck
> correctly classifies it as `Underdetermined`). The implementer
> should revise the demo to a goal-by-goal-determinate form, or
> adjust the user's expectation: the "request more solutions until
> unsat" framing in the PRD requires either (a) an explicit
> finite-domain prefix on `?X` (e.g. `?X ∈ {1, 2, 3, 4}`), or (b) a
> joint-solve enhancement (M3 work). Either choice is consistent
> with this design. The rendered proof shape is the same regardless
> of which witness the user requests.

### 6.4 Demo 4 — `OutsideFragment` rejection

**Query.** `?- root_of(?X, 2^x + x^2 - 5).`

The dispatcher classifies this as `OutsideFragment(TRANSCENDENTAL,
"...")` per DISPATCH_DESIGN.md §12.4. **No proof is produced.** The
renderer is not called.

The REPL displays the honest-rejection message; there is no
`proofs/m2/04_outside_fragment.json` because there is no proof.

For completeness in `proofs/m2/`: the implementer may instead save
a small JSONL session-log file containing the dispatcher's classify
event and outcome event, demonstrating the rejection path. This is
not a proof artefact; it is a session-log artefact. Document this
in `proofs/m2/README.md`.

### 6.5 The contested-convention rejection (Case 2)

Hypothetical query: `?- root_of(?X, ?X^?X - 1).` (See
DISPATCH_DESIGN.md §12.6 for the dispatcher view.)

If the dispatcher returns `UniqueSolution({?X: Const(1)})` (SymPy
returned only ?X=1, or returned ?X=1 alongside ?X=0 and the latter
was reclassified as Case 2):

**Rendered proof:**

```
1. (((1^1) - 1) = 0)                    arithEval
```

`arithEval` evaluator: `1^1 = 1`, `1 - 1 = 0`, `0 == 0` True.
Accept.

The contested ?X=0 path produces no proof; the REPL note explains
this as an informational message (DISPATCH_DESIGN.md §7.4).

---

## 7. Box behaviour — flat depth-0 in M2

`arithEval` lines work fine inside Fitch boxes (per
ARITH_EVAL_DESIGN.md §2 — the kernel's structural pass permits
zero-ref/zero-box rule applications at any depth). The M2 renderer,
however, **does not produce boxed `arithEval` lines** for any of the
four demos in `prd_milestone_2.md` §3.3.

### 7.1 Why flat is sufficient for M2

M2's arithmetic content is always at the top level of a goal
(directly resolvable by Z3 or SymPy). There is no proof-by-cases or
proof-by-contradiction shape that would require an `arithEval` line
inside an assumption box. Every M2 demo's rendered proof is a flat
depth-0 sequence — same shape M1 produced.

### 7.2 What boxed arithEval would require

If a future milestone needed boxed `arithEval` (e.g. an `impI` that
introduces an arithmetic assumption like `?X > 0` and derives
`?X^2 > 0` via `arithEval` within the box), the renderer would
need:

- A box-depth tracker through the SLD-trace walk.
- Coordination with the dispatcher to mark which dispatcher steps
  occur inside an open box (e.g. by extending
  `DispatcherResolvedStep` with a `box_context` field).
- Premise emission still at depth 0 (premises stay outside boxes).

This is well within the kernel's existing capabilities — the kernel
does not need to change, only the renderer and dispatcher need to
agree on box context. Marked as future work; not in M2.

### 7.3 Test invariant

A property test (§10.2) asserts that every line in every
M2-rendered proof has `box_depth == 0`. If a future contributor
inadvertently introduces a boxed line, the test fails. This
documents the M2 invariant in the test suite.

---

## 8. Mixed-goal interleaving order — why goal order

The renderer emits per-goal subproofs in **goal-evaluation order**
(left-to-right through the query tuple), exactly matching the order
the dispatcher emits steps. This is the order specified in
DISPATCH_DESIGN.md §13.3 and §6.

Why goal order, not some optimised order:

- **Determinism.** The user's query syntax fixes the goal order.
  The rendered proof is a function of the user's input, the KB,
  and the user's clause picks. Goal order makes this transparent.
- **Logical dependency.** When goal i+1 references metas bound by
  goal i, the rendered proof must derive goal i first. Goal order
  satisfies this trivially.
- **AndI chain shape.** The and-chain is left-associated:
  `(((G_1 ∧ G_2) ∧ G_3) ∧ ... ∧ G_n)`. This matches goal-order
  rendering with no shuffling.
- **Backtracking.** When the user uses `back` to undo a pick, the
  renderer's view of `state.history` shrinks from the right end.
  Goal-order emission keeps history-prefix and proof-prefix in
  one-to-one correspondence — useful for incremental rendering in
  future REPL enhancements (not in M2).

The dispatcher and renderer agree on goal order; this is one of the
four coupling points (DISPATCH_DESIGN.md §13.3).

---

## 9. The (sat, None) underdetermined case

Per DISPATCH_DESIGN.md §3.1 and §12.7, the `Underdetermined` outcome
unifies the M1 universal-fact case with the M2 solver-side
underdetermination case. When `manual_solve` encounters
`Underdetermined`, it returns `(subst, None)` per the M1 fix in
`HARDENING_FINDINGS.md`. **The renderer is not called.**

The renderer therefore never sees an `Underdetermined` step. Its
input invariant (per §3) holds: every history entry is either a
clause-resolved step (whose unifier is well-defined and ground after
saturation, or the universal-fact-pattern detection in
`manual_solve` would have triggered before the renderer is invoked)
or a dispatcher-resolved step (whose `ground_atom` is already
verified ground per §3).

If the renderer is mistakenly invoked with an underdetermined
state, the existing M1 grounding-check in `solve/__init__.py` (per
HARDENING_FINDINGS.md) catches it and returns `(subst, None)` rather
than producing a malformed proof. This existing safety net is
unchanged in M2.

---

## 10. Soundness backstop and tests

### 10.1 The renderer kernel-rejection test (M2 analogue)

M1 has `tests/test_renderer_property.py` (Hypothesis-based) that
asserts every rendered proof passes `check_proof`. M2 extends this:

- The Hypothesis strategy generates KBs **plus** small ground
  arithmetic atoms (per the same operator/predicate set as
  ARITH_EVAL_DESIGN.md §11). For arithmetic-only queries, the
  generator wraps each in a single-goal query.
- The picker is the same bounded-first-candidate picker as in M1.
- The dispatcher is a real `Dispatcher` instance with mock bridges
  that return the obvious witness for each constructed query.
- The property: if `manual_solve` returns `(subst, proof)` with a
  non-None proof, then `check_proof(proof)` returns `Verified` AND
  `proof.lines[-1].formula == proof.goal`.

This is a one-sided property — `(subst, None)` and `None` outcomes
are vacuous passes (covered by integration tests separately).

### 10.2 Box-depth invariant test

A targeted test (`tests/test_renderer_m2_box_depth.py`, new file)
runs each of the four M2 demos and asserts every line in the
rendered proof has `box_depth == 0`. Documents the §7 invariant.

### 10.3 Rule-alphabet test

Another targeted test asserts that every rule name in every
rendered M2 demo proof is in the M2 alphabet `{Premise, forallE,
andI, impE, arithEval, eqRefl}`. Catches accidental `eqSubst` or
`existsI` emissions.

### 10.4 The malicious-renderer kernel-rejection test

Synthetic test: construct a rendered proof line by hand with an
`arithEval` justification but a formula that evaluates to False
(e.g. `Atom(">", (Const(2), Const(5)))`). Wrap in a `Proof` and run
`check_proof`. Assert the result is `CheckFailure` with `reason` an
instance of `EvaluationFalse`.

This is the M2 analogue of M0's `99_BAD_*` proofs and M1's
renderer kernel-rejection test. It demonstrates that the kernel
catches a buggy renderer that emits an arithmetically-false
`arithEval` line.

A second variant: hand-built proof with an `arithEval` line whose
formula contains a `Meta` (e.g. `Atom(">", (Meta("?X"), Const(2)))`).
The kernel's §5.3 `UnresolvedMeta` check catches this before
`arithEval` runs. Test asserts `CheckFailure` with `UnresolvedMeta`
reason. Documents the layered defence.

A third variant: hand-built proof with an `arithEval` line whose
formula is `Equals(Func("^", (Const(0), Const(0))), Const(1))`. The
kernel's `arithEval` rejects with `MalformedArithmetic` per
ARITH_EVAL_DESIGN.md §11.3 M14 (the contested-convention case).
Test asserts `CheckFailure` with `MalformedArithmetic`. Demonstrates
that the kernel still rejects the contested case even if a
hypothetical malicious renderer tried to slip it through.

### 10.5 Per-demo end-to-end tests

For each of the four M2 demos, an integration test that runs the
demo end-to-end (parser → dispatcher → renderer → kernel) and
asserts `Verified`. Mirrors M1's `test_demos.py`. The demo for
`OutsideFragment` (demo 4) asserts `manual_solve` returns `None`
with `dispatcher.last_outside_fragment.classification ==
TRANSCENDENTAL`.

---

## 11. Coordination notes back to the dispatcher

The renderer relies on these contracts from `DISPATCH_DESIGN.md`:

### 11.1 Step-emission timing

Per DISPATCH_DESIGN.md §13.2, the dispatcher's `_verify_arith_ground`
runs **before** appending a `DispatcherResolvedStep` to
`state.history`. The renderer assumes every step it sees is
verified.

### 11.2 Step content invariants

Per DISPATCH_DESIGN.md §3.4, every `DispatcherResolvedStep` the
renderer reads has:

- `ground_atom` fully ground (no `Var`, no `Meta`).
- `ground_atom` in `arithEval`'s evaluable set (per
  ARITH_EVAL_DESIGN.md §5).
- `route` either `Z3` or `SYMPY` (never `KB` or `REJECTED`).

These are checked by the dispatcher's tests. The renderer trusts
them and does not re-check (would be redundant; the kernel's
`check_proof` is the final arbiter).

### 11.3 No step on Case-1/Case-2 paths

Per DISPATCH_DESIGN.md §7 and §13.4, when the dispatcher detects a
solver/kernel disagreement (Case 1) or a contested-convention
rejection (Case 2), it emits no step. The renderer is not invoked
for these paths. Case 1 crashes; Case 2 returns `OutsideFragment`
to the caller.

### 11.4 Goal-order emission

Per DISPATCH_DESIGN.md §13.3, dispatcher steps appear in
`state.history` in goal-evaluation order. The renderer's per-goal
walk in §4.1 relies on this.

### 11.5 What the renderer expects per outcome

| Dispatcher outcome | Step | Renderer behaviour |
|---|---|---|
| `UniqueSolution` | `DispatcherResolvedStep` | render one arithEval/eqRefl line |
| `MultipleSolutions` (after user picks) | step for chosen witness | render one arithEval/eqRefl line for the chosen witness; alternative witnesses produce separate Proof objects |
| `InfinitelyManySolutions` | (does not occur in M2 — the dispatcher classifies this as `Underdetermined`; the name `InfinitelyManySolutions` is reserved for future use, see DISPATCH_DESIGN.md §3.1) | renderer not called |
| `NoSolution` | None | renderer not called; manual_solve returns None |
| `Underdetermined` | None | renderer not called; manual_solve returns (subst, None) |
| `OutsideFragment` | None | renderer not called; manual_solve returns None with last_outside_fragment set |

> **Note on `InfinitelyManySolutions`.** The PRD enumerates six
> outcomes including `InfinitelyManySolutions`. In M2, the
> dispatcher detects "infinitely many" via add-negation-and-recheck
> and emits `Underdetermined` rather than `InfinitelyManySolutions`
> — the difference between "many but enumerable" and "infinitely
> many" is moot for the manual-mode user (both produce no ground
> witness for proof rendering). M3 may distinguish these for
> automated search; for M2, they unify under `Underdetermined`.

---

## 12. Non-goals

Out-of-scope items, surfaced because they look natural extensions:

1. **Boxed `arithEval` lines.** Per §7. Future work.
2. **Z3-proof-to-Fitch translation.** Per
   `prd_milestone_2.md` §4. The renderer never consumes Z3's
   internal proof calculus; it only emits `arithEval` lines for
   verified witnesses.
3. **`eqSubst` for arithmetic substitution.** A future milestone
   might use `eqSubst` to rewrite `Equals(?X, Const(5))` into
   `Equals(?X^2, Const(25))`. Out of scope; M2 derives both via
   independent `arithEval`/`eqRefl` lines instead.
4. **Multi-witness combined proofs.** When the dispatcher returns
   `MultipleSolutions` and the user wants proofs for all witnesses,
   the renderer is called once per witness, producing one Proof
   each. There is no "combined proof of all witnesses"
   construction. The REPL may display them sequentially.
5. **Conjecture or counterexample annotations.** The renderer
   emits proof lines, not metadata about why each line was chosen.
   Logging (per `log/`) records the dispatcher's reasoning; the
   proof itself is the kernel-checkable artefact only.
6. **Pretty-printing of arithmetic.** `Func("+", (Const(3),
   Const(4)))` may render as `(3 + 4)` or `Func("+", (3, 4))`
   depending on the printer in `solve/render.py` (existing M1
   logic, unchanged). M2 does not introduce a new infix printer.
   ASCII-only rendering remains the M1 standard through M2.
7. **Renderer-side fragment classification.** The renderer does
   not classify atoms as in/outside the fragment — that is the
   dispatcher's job. The renderer trusts the dispatcher's
   verify-before-step invariant.

---

## 13. Implementer summary

What Sonnet should produce against this design:

1. **`src/hlmr/solve/render.py`** — extend the existing M1 renderer:
   - Modify `render(state, kb, query)` to accept a tuple of goals
     in addition to a single goal (the M2 multi-goal extension).
   - Pattern-match on `SLDStep` variants in the step-walking logic
     (the M1 single-variant assumption becomes a discriminated
     union match). For `DispatcherResolvedStep`, emit a single
     `arithEval` or `eqRefl` line.
   - Add `_choose_equality_rule(f)` helper per §4.4. Pure function;
     no kernel call.
   - Add `_emit_and_chain(...)` helper per §4.6. Standard `andI`
     left-associated chaining.
   - Update `_emit_premises(...)` to skip `DispatcherResolvedStep`s
     (they have no clause to emit).

   Estimated diff: ~100 lines added; M1 logic unchanged.

2. **`src/hlmr/solve/sld.py`** — refactor `SLDStep` into
   `ClauseResolvedStep | DispatcherResolvedStep` per
   DISPATCH_DESIGN.md §3.4. Update `resolve()` and any other M1
   constructors to produce `ClauseResolvedStep` (renamed from M1's
   `SLDStep`). Existing M1 tests pass after this rename — the field
   set is identical.

   Estimated diff: ~50 lines (rename + new dataclass).

3. **`src/hlmr/solve/__init__.py:manual_solve`** — extend per
   DISPATCH_DESIGN.md §6. Most of the existing M1 logic is reused;
   the new branches handle `dispatcher.classify` and
   `dispatcher.dispatch` for non-KB goals.

   Estimated diff: ~100 lines added.

4. **Tests** — new files:
   - `tests/test_renderer_m2_demos.py` — per-demo end-to-end tests
     (§10.5).
   - `tests/test_renderer_m2_box_depth.py` — depth-0 invariant
     (§10.2).
   - `tests/test_renderer_m2_alphabet.py` — rule-alphabet invariant
     (§10.3).
   - `tests/test_renderer_m2_kernel_rejection.py` — malicious-
     renderer tests (§10.4).
   - Extend `tests/test_renderer_property.py` to cover the M2
     dispatcher path (§10.1).

   Estimated total: ~300 lines of tests.

5. **Documentation** — update `src/hlmr/solve/RENDER_DESIGN.md`'s
   "Status" line to note "extended for M2; see RENDER_M2_DESIGN.md."
   The M1 design doc is not rewritten.

The renderer extension is small relative to its design scope — most
of the work is in `dispatch/` (Task B) and the bridges (separate
work). The renderer just consumes Task B's contract and emits the
Task A-compatible lines.

---

## 14. Checklist against `prd_milestone_2.md` §10

| §10 deliverable | Where in this doc |
|---|---|
| Worked rendering examples for each M2 demo | §6 |
| The extended algorithm vs M1 | §4 |
| The `SLDStep` marker / variant | §3, §11 |
| Edge cases (mixed steps, multiple witnesses) | §6, §11.5 |
| Test strategy | §10 |
| Rule-alphabet bounded to `{Premise, forallE, andI, impE, arithEval, eqRefl}` | §2, §10.3 |
| No `Meta` survives in any line | §3 invariant, §10.4 (test) |
| Kernel-rejection of malicious renderer | §10.4 |
| Coordination with the dispatcher | §11 |
| `eqRefl` vs `arithEval` choice (per ARITH_EVAL_DESIGN.md §5.3) | §4.4, §5 |
| Box behaviour | §7 |

All §10 items addressed. Ready for review alongside DISPATCH_DESIGN.md.
