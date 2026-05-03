# SLD-trace-to-Fitch-proof renderer — design

**Status:** Design v1 (Opus 4.7). No code in this document; pseudocode only.
**Implements:** `src/hlmr/solve/render.py` per `prd_milestone_1.md` §8.2 and §11.2 Task A.
**Target reader:** Sonnet 4.6 implementing against this spec.

---

## 1. Headline observation

For every clause and query the M1 PRD admits, the rendered proof is a
**flat, depth-0 ND proof using only five rules**: `Premise`, `forallE`,
`andI`, `impE` (and, trivially, no rule at all when a clause is a fact
that already grounds out a body atom). No assumptions, no boxes, no
classical reasoning, no equality rewriting. The kernel can do far more
than M1 needs; M1 needs the bottom slice.

This falls out of the four worked examples below. Anything else
(e.g. `existsI` or `eqRefl`) is a smell that the implementer has gone
off-spec.

---

## 2. Worked example: Demo 2 — the syllogism

**KB.**
```
human(socrates).                  (c1, fact)
mortal(X) :- human(X).            (c2)
```

**Query.** `?- mortal(socrates).`

### 2.1 SLD trace (by hand)

| State | Goals | Subst | Action |
|---|---|---|---|
| 0 | `[mortal(socrates)]` | `{}` | pick c2 |
| 1 | `[human(?X_1)]` | `{?X_1: socrates}` | pick c1 |
| 2 | `[]` | `{?X_1: socrates}` | done |

c2 is renamed to `mortal(?X_1) :- human(?X_1)`. Unifying
`mortal(socrates)` with the renamed head binds `?X_1 → socrates`.
c1 has no variables; renaming is identity.

### 2.2 Fitch proof (by hand)

```
1. human(socrates)                          Premise            (c1)
2. (forall X. (human(X) -> mortal(X)))      Premise            (c2)
3. (human(socrates) -> mortal(socrates))    forallE 2 [term=socrates]
4. mortal(socrates)                         impE 3 1
```

Four lines. Final line is `apply_subst(final_subst, query) = mortal(socrates)`.
IR types appearing: `Atom`, `Implies`, `ForAll`, `Const`. No `Meta`. No
`Var` outside the bound position of the `ForAll`. No boxes.

### 2.3 What the algorithm just did

- **Premise emission.** Each clause that appears in the trace was emitted
  as a premise. Facts: head as-is. Rules with k body atoms:
  `∀v_1 ... v_n. (b_1 ∧ ... ∧ b_k) → head`, with the conjunction
  left-associated and the universal variables in clause-level
  appearance order.
- **Walking the SLD history.** Step 0 (root) reduces the query goal to
  one body atom. Step 1 reduces that body atom to nothing. The renderer
  walks bottom-up: step 1 is rendered first (returns line 1 directly,
  because c1 is a ground fact); then step 0 instantiates c2 via
  `forallE`, then `impE` against the body atom now sitting on line 1.

---

## 3. Worked example: Demo 1 — kinship (recursive)

**KB.**
```
parent(alice, bob).                                      (c1)
parent(bob, carol).                                      (c2)
ancestor(X, Y) :- parent(X, Y).                          (c3)
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).          (c4)
```

**Query.** `?- ancestor(?A, carol).` Witness: `alice` via the recursive
clause c4.

### 3.1 SLD trace

| Step | Goal resolved (after subst) | Clause | Renamed body | Bindings added |
|---|---|---|---|---|
| 1 | `ancestor(?A, carol)` | c4 | `[parent(?X_1, ?Z_1), ancestor(?Z_1, ?Y_1)]` | `?A→?X_1, ?Y_1→carol` |
| 2 | `parent(?X_1, ?Z_1)` | c1 | `[]` | `?X_1→alice, ?Z_1→bob` |
| 3 | `ancestor(?Z_1, ?Y_1)` (= `ancestor(bob, carol)`) | c3 | `[parent(?X_2, ?Y_2)]` | `?X_2→bob, ?Y_2→carol` |
| 4 | `parent(?X_2, ?Y_2)` (= `parent(bob, carol)`) | c2 | `[]` | none |

Saturating the final substitution: `?A → alice`, `?Z_1 → bob`,
`?Y_1 → carol`, etc. Witness for the original `?A` is `alice`.

### 3.2 Step tree

```
step 1 (c4)
├── body[0] resolved by step 2 (c1)
└── body[1] resolved by step 3 (c3)
    └── body[0] resolved by step 4 (c2)
```

Recovered from the linear history by stack discipline (§5.2).

### 3.3 Fitch proof (by hand)

```
 1. parent(alice, bob)                                                    Premise         (c1)
 2. parent(bob, carol)                                                    Premise         (c2)
 3. (forall X. (forall Y. (parent(X, Y) -> ancestor(X, Y))))              Premise         (c3)
 4. (forall X. (forall Y. (forall Z. ((parent(X, Z) & ancestor(Z, Y)) -> ancestor(X, Y)))))  Premise (c4)
 5. (forall Y. (parent(bob, Y) -> ancestor(bob, Y)))                      forallE 3 [term=bob]
 6. (parent(bob, carol) -> ancestor(bob, carol))                          forallE 5 [term=carol]
 7. ancestor(bob, carol)                                                  impE 6 2
 8. (forall Y. (forall Z. ((parent(alice, Z) & ancestor(Z, Y)) -> ancestor(alice, Y))))   forallE 4 [term=alice]
 9. (forall Z. ((parent(alice, Z) & ancestor(Z, carol)) -> ancestor(alice, carol)))       forallE 8 [term=carol]
10. ((parent(alice, bob) & ancestor(bob, carol)) -> ancestor(alice, carol))               forallE 9 [term=bob]
11. (parent(alice, bob) & ancestor(bob, carol))                           andI 1 7
12. ancestor(alice, carol)                                                impE 10 11
```

Twelve lines.

### 3.4 What this exercises

- **Multi-body decomposition via `andI`.** Step 1's body has two
  literals. They are derived independently (lines 1 and 7), then
  combined into the conjunction the implication expects.
- **Quantifier order in premise emission.** c4's variables are
  `[X, Y, Z]` in left-to-right appearance order: X (head pos 0), Y (head
  pos 1), Z (body[0] pos 1). The premise quantifies in that order,
  outermost-first. `forallE` peels in the same order: X first, then Y,
  then Z. The terms come from the **saturated final substitution**,
  looked up via the original-var → fresh-Meta var-map for that step.
- **Recursion.** c4's body[1] is `ancestor(...)` — same predicate as
  the head. The recursive call goes to render(step 3), which uses c3
  (a *different* clause that happens to have the same head predicate),
  not back to c4. Recursion terminates because each SLD step strictly
  consumes one goal, and the history is finite.
- **The witness is recovered.** The final line is the saturated
  substitution applied to the query: `ancestor(alice, carol)`.

---

## 4. Worked example: Demo 4 — Peano even

**KB.**
```
even(0).                              (c1)
even(s(s(N))) :- even(N).             (c2)
```

**Query.** `?- even(s(s(s(s(0))))).`

### 4.1 SLD trace

| Step | Goal resolved | Clause | Bindings |
|---|---|---|---|
| 1 | `even(s(s(s(s(0)))))` | c2 (renamed: head `even(s(s(?N_1)))`, body `[even(?N_1)]`) | `?N_1 → s(s(0))` |
| 2 | `even(s(s(0)))` | c2 again (renamed: head `even(s(s(?N_2)))`, body `[even(?N_2)]`) | `?N_2 → 0` |
| 3 | `even(0)` | c1 | none |

c2 used twice → two independent fresh metas (`?N_1`, `?N_2`), each
bound to a different value. This is exactly what
`FreshNameGen` was built for.

### 4.2 Fitch proof

```
1. even(0)                                              Premise (c1)
2. (forall N. (even(N) -> even(s(s(N)))))               Premise (c2)
3. (even(0) -> even(s(s(0))))                           forallE 2 [term=0]
4. even(s(s(0)))                                        impE 3 1
5. (even(s(s(0))) -> even(s(s(s(s(0))))))               forallE 2 [term=s(s(0))]
6. even(s(s(s(s(0)))))                                  impE 5 4
```

Six lines. Same premise (line 2) used twice with different `forallE`
terms; each step produces its own instantiation. No premise
deduplication issue because we emit each *clause* once, but `forallE`
itself is per-use.

### 4.3 What this exercises

- **Nested function-symbol terms** (`s(s(s(s(0))))`) survive
  unification, substitution, and `forallE`'s `term` extra unmodified.
- **Same clause used multiple times** with disjoint fresh names. The
  renderer must trust `FreshNameGen` and not collapse uses.

---

## 5. Worked example: Demo 3 — finite puzzle

**KB** (smaller than the Einstein zebra; three facts plus a chain rule):

```
left_of(red, green).                                  (c1)
left_of(green, blue).                                 (c2)
adjacent(X, Y) :- left_of(X, Y).                      (c3)
chain(X, Y, Z) :- adjacent(X, Y), adjacent(Y, Z).     (c4)
```

**Query.** `?- chain(red, green, blue).`

### 5.1 SLD trace (abbreviated)

1. c4 renamed (`?X_1, ?Y_1, ?Z_1`) → bindings `?X_1→red, ?Y_1→green, ?Z_1→blue`.
2. c3 renamed (`?X_2, ?Y_2`) → bindings `?X_2→red, ?Y_2→green`.
3. c1 → no bindings, discharges `left_of(red, green)`.
4. c3 renamed (`?X_3, ?Y_3`) → bindings `?X_3→green, ?Y_3→blue`.
5. c2 → no bindings, discharges `left_of(green, blue)`.

### 5.2 Fitch proof (sketch)

```
 1. left_of(red, green)                                                   Premise (c1)
 2. left_of(green, blue)                                                  Premise (c2)
 3. (forall X. (forall Y. (left_of(X, Y) -> adjacent(X, Y))))             Premise (c3)
 4. (forall X. (forall Y. (forall Z. ((adjacent(X, Y) & adjacent(Y, Z)) -> chain(X, Y, Z)))))  Premise (c4)
 5. (forall Y. (left_of(red, Y) -> adjacent(red, Y)))                     forallE 3 [term=red]
 6. (left_of(red, green) -> adjacent(red, green))                         forallE 5 [term=green]
 7. adjacent(red, green)                                                  impE 6 1
 8. (forall Y. (left_of(green, Y) -> adjacent(green, Y)))                 forallE 3 [term=green]
 9. (left_of(green, blue) -> adjacent(green, blue))                       forallE 8 [term=blue]
10. adjacent(green, blue)                                                 impE 9 2
11. (forall Y. (forall Z. ((adjacent(red, Y) & adjacent(Y, Z)) -> chain(red, Y, Z))))    forallE 4 [term=red]
12. (forall Z. ((adjacent(red, green) & adjacent(green, Z)) -> chain(red, green, Z)))    forallE 11 [term=green]
13. ((adjacent(red, green) & adjacent(green, blue)) -> chain(red, green, blue))          forallE 12 [term=blue]
14. (adjacent(red, green) & adjacent(green, blue))                        andI 7 10
15. chain(red, green, blue)                                               impE 13 14
```

Sixteen-ish lines (depending on whether c2 is dedup-emitted as a
premise even though it's only used once — yes, it is). What this
exercises: deeper subgoal stacks (chain → 2 adjacency goals, each
adjacency → 1 left_of goal) and longer `forallE` chains for
multi-argument predicates.

---

## 6. The general algorithm

### 6.1 Inputs and outputs

```
def render(state: SLDState, kb: KnowledgeBase, query: Atom | Equals) -> Proof
```

**Pre-conditions.** `state.goals == ()` (SLD has succeeded). `query`
is the original goal as the user typed it (possibly containing
`Meta`s; possibly `Equals`).

**Post-conditions.** Returned `Proof` has `goal = apply_to_formula(state.subst, query)`.
The kernel's `check_proof` accepts it.

The KB is taken explicitly (rather than recovered from the history)
only to access the **clause-as-it-appears-in-the-KB** form. Each
`SLDStep` already records `clause_used`, so KB is technically
redundant — but keeping the parameter documents the dependency.

### 6.2 Procedure

1. **Saturate** the final substitution. `apply_to_term` is one-pass; an
   unsaturated subst can leave `?A → ?X_1` and `?X_1 → alice` as
   separate hops. Use a `_saturate` helper (already used in unifier
   tests) or fold `apply_to_term` into a fixed point.

2. **Compute the step tree** from the linear history (§5.2). Result:
   `parent[i]`, `child_position[i]`, and `children[i]` — the indices
   of the steps that resolve each body atom of step *i*, in order.
   Algorithm: walk the history with a stack of
   `(parent_idx, body_indices_remaining)`. Pop the next expected goal,
   record the parent edge, push the new step's body indices.

3. **Determine premise lines**:
   - Walk the history and collect, in first-use order, the set of
     distinct clauses (`{step.clause_used for step in history}`).
   - For each unique clause, emit one `Premise` line. Build the
     premise formula:
     - Let `vars = _vars_in_order(clause)` (clause-level appearance
       order; same helper sld.py already exports).
     - Build the body conjunction:
       - 0 atoms → no implication: premise body is just `clause.head`.
       - 1 atom → premise body is `body[0] -> head`.
       - k ≥ 2 atoms → premise body is `(((b_1 ∧ b_2) ∧ b_3) ... ∧ b_k) -> head`,
         left-associative.
     - Wrap with `ForAll` for each var, outermost-first in `vars` order.
   - Record `clause_premise_line[id(clause)] → line_number`. (Use
     identity, not structural equality, so two distinct clauses with
     the same name don't collide.)

4. **Recursively render each step.** Drive from the root:
   `query_line = render_step(0)`. The implementation is a
   straightforward recursive function on the step tree.

```
render_step(i):
    step = history[i]
    body_lines: list[int] = []
    for child_idx in children[i]:           # in body order
        body_lines.append(render_step(child_idx))

    clause = step.clause_used
    var_map = extract_var_map(clause, step.clause_renamed)
    # var_map maps original Var name → fresh Meta name (e.g. "X" → "?X_1").

    # Apply forallE to the clause premise once per universal variable,
    # outermost-first. The substitution term for each is the saturated
    # final subst applied to the corresponding fresh meta.
    current_line = clause_premise_line[clause]
    for v in _vars_in_order(clause):
        fresh = var_map[v]
        term = apply_to_term(saturated_subst, Meta(fresh))
        # term must be ground; if a Meta survives, raise RenderError.
        new_formula = peel_outer_forall(line_formula(current_line), term)
        current_line = emit(new_formula, RuleApp("forallE",
                                                 line_refs=(current_line,),
                                                 extra={"term": term}))

    # If the clause has a body, current_line now holds (body_conj -> head).
    if clause.body:
        # Build conjunction of body atoms (left-associative).
        if len(body_lines) == 1:
            conj_line = body_lines[0]
        else:
            conj_line = body_lines[0]
            conj_formula = line_formula(body_lines[0])
            for j in range(1, len(body_lines)):
                next_formula = line_formula(body_lines[j])
                conj_formula = And(conj_formula, next_formula)
                conj_line = emit(conj_formula, RuleApp("andI",
                                                       line_refs=(conj_line, body_lines[j])))
        # Apply impE.
        head_formula = line_formula(current_line).right  # the (... -> head)
        head_line = emit(head_formula, RuleApp("impE",
                                               line_refs=(current_line, conj_line)))
        return head_line
    else:
        # Fact (possibly forallE'd to ground): current_line already holds the
        # head atom.
        return current_line
```

5. **Validate.** After construction, the renderer must:
   - Assert `state.goals == ()` on entry (defensive).
   - Assert no line's formula contains a `Meta` (the kernel's §5.3
     backstop catches this, but the renderer should never emit one).
   - Assert `proof.lines[-1].formula == apply_to_formula(saturated_subst, query)`.
   - Optionally call `check_proof(proof)` and raise on failure.
     Recommended for the M1 test demos; gated by a flag for production.

### 6.3 Helper: `extract_var_map`

Walks `clause_used` and `clause_renamed` in parallel. At every position
where the original is `Var(name)`, the corresponding renamed term must
be `Meta(meta_name)`. Records `name → meta_name`. The map is total
over `_vars_in_order(clause_used)` (every Var name appears at least
once, by construction). The renderer requires this lazily-computed
mapping; it does not require modifying `SLDStep`.

---

## 7. Edge cases

### 7.1 Empty body (fact)

Premise is the head atom (universally quantified if it has variables).
`render_step` emits zero `forallE` lines for ground facts (skips the
loop), zero `andI` lines (no body), and skips `impE`. It returns the
existing premise line directly. Demos 2 (c1), 4 (c1) and the puzzle
(c1, c2) all hit this path.

### 7.2 Single-body clause

Premise is `∀vars. body[0] → head` (no conjunction). One `forallE` per
universal, then `impE` of premise against the single body subproof
line. No `andI`. Demo 2's c2 and Demo 1's c3 hit this.

### 7.3 Multi-body clause

Premise is `∀vars. (b_1 ∧ ... ∧ b_k) → head`, left-associated. Renderer
builds the conjunction with `k-1` `andI` calls before the `impE`.
Demo 1's c4 (k=2) and Demo 3's c4 (k=2) hit this. Larger `k` is the
same pattern.

### 7.4 Recursive clause used multiple times

Each use is a separate `SLDStep` with a separate `clause_renamed` and
separate fresh metas via `FreshNameGen`. The renderer does not
deduplicate steps. The premise (one per unique clause) is reused
across multiple `forallE` chains, each with its own term arguments.
Demo 4 hits this: c2 used twice, two `forallE` chains off line 2.

### 7.5 Same logical variable in head and body

E.g. `mortal(X) :- human(X)`. The renaming step produces a single
fresh `?X_1` shared across the head and body of the renamed clause.
The premise quantifies that single variable once: `∀X. human(X) → mortal(X)`.
A single `forallE` instantiates X, giving `human(t) → mortal(t)` for
the same t in both places. Standard, no special handling.

### 7.6 Same Meta in multiple positions after substitution

After `_saturate`, a Meta resolves to its terminal value. Wherever
that Meta appears (head, body, recursive children) it grounds to the
same term. The renderer trusts the unifier's transitivity guarantee
(verified by the unifier's Hypothesis property test). No special
handling.

### 7.7 Equals atoms in clause heads or bodies

`Equals(t, u)` is matched by `KnowledgeBase.matching` via the `"="`
key (see `src/hlmr/ir/kb.py:_head_key`). The renderer treats `Equals`
exactly like `Atom` for the purposes of `forallE`/`andI`/`impE` —
the kernel's rules for those operate at the formula level and don't
care that the formula happens to be an `Equals`. **The renderer does
not use `eqRefl` or `eqSubst`.** Equality reasoning in M1 happens
only via clauses (e.g., a fact `f(0) = 0.`). If a query relies on
`X = X` reflexivity, the user must supply that as a clause; the
renderer does not synthesise it. Flag this as a deliberate design
decision: future milestones may extend it.

### 7.8 Query containing a Meta that gets bound

The standard case for `?- ancestor(?A, alice)`. `state.subst` after
SLD will have `?A → witness`. The renderer:
- Sets `proof.goal = apply_to_formula(saturated_subst, query)`.
- The final line equals that ground form.
- The renderer also returns the binding for the meta separately
  (via `manual_solve`'s API), but inside the `Proof` itself the meta
  is gone.

---

## 8. Module API

```
# src/hlmr/solve/render.py

class RenderError(Exception):
    """Raised when the renderer cannot produce a valid proof.
    Indicates a bug in the renderer or an unsaturated substitution."""

def render(state: SLDState, kb: KnowledgeBase, query: Atom | Equals) -> Proof:
    """Public renderer. Pre: state.goals == (). Post: kernel-checkable Proof
    whose final line is apply_to_formula(saturated(state.subst), query).
    Raises RenderError on failure."""

# Public re-exports from solve/__init__.py: render, RenderError.
# Private helpers inside render.py: _saturate, _build_step_tree,
# _build_premise_formula, _extract_var_map, _peel_forall, _emit, etc.
```

### 8.1 Integration with `manual_solve`

```
# src/hlmr/solve/__init__.py (later, when manual_solve is added)

def manual_solve(
    kb: KnowledgeBase,
    goal: Atom | Equals,
    picker: Callable[[list[Clause], SLDState], int],
) -> tuple[Substitution, Proof] | None:
    state = SLDState(goals=(goal,), subst={}, history=())
    gen = FreshNameGen()
    while state.goals:
        cs = candidates(state, kb)
        if not cs:
            return None
        idx = picker(cs, state)
        if idx is None:                   # user abort
            return None
        result = resolve(state, cs[idx], gen)
        if result is None:                # unification failed
            return None                   # picker chose a non-applicable clause
        state = result
    proof = render(state, kb, goal)
    if check_proof(proof) != Verified():
        raise RenderError("rendered proof rejected by kernel")
    return (saturate(state.subst), proof)
```

### 8.2 Failure mode

`render` raises `RenderError`, not `None`. Reasons: a Meta survives
saturation (incomplete substitution → renderer cannot emit a ground
`forallE` term), or `state.goals` is non-empty (precondition violation),
or `extract_var_map` finds a structural mismatch between
`clause_used` and `clause_renamed` (a bug in `_rename_clause`).
**The renderer never returns a deliberately-failing proof.** If we
cannot produce a valid proof, we raise.

---

## 9. What the implementer must NOT do

- **Do not skip `_saturate` on the final substitution.** A one-pass
  `apply_to_term` leaves `?A → ?X_1 → alice` as two hops; the
  `forallE` term lookup for `?A` will return `?X_1` (still a Meta) and
  the kernel will reject. The unifier's `_walk` chases internally but
  the *output* substitution is not necessarily transitively closed.
- **Do not emit `forallI`.** M1 has zero quantifier-introduction
  rules in the renderer's output. Every quantifier comes in via a
  premise and is eliminated by `forallE`. Using `forallI` requires
  eigenvariable bookkeeping that this renderer does not do.
- **Do not synthesise `eqRefl` or `eqSubst`.** Equality is opaque:
  `Equals` is just a binary atom shape with `_head_key = "="`.
- **Do not introduce assumptions or boxes.** All output is at
  `box_depth=0`. Rules that need boxes (`impI`, `notI`, `orE`,
  `existsE`, `PBC`) are out of scope.
- **Do not deduplicate premises by structural equality.** Two distinct
  KB clauses that happen to have the same premise form (e.g.
  identical facts duplicated by the user) should still each get one
  premise line — but in practice the parser will reject duplicates
  upstream. Use clause object identity (`id(...)`) for the
  premise-line lookup, not structural equality.
- **Do not reuse a Meta name across two uses of the same clause.**
  `FreshNameGen` already prevents this. The renderer's job is to
  trust it: do not "tidy up" by collapsing `?X_1` and `?X_2` even
  when they end up bound to the same term.
- **Do not ground metas before clause renaming introduces them.**
  Substitution is meaningful only after the metas exist. The order is
  fixed: rename-apart, unify, accumulate subst, render with the
  saturated-final subst applied at term-lookup time.
- **Do not assume premise-line numbers stay constant during emission.**
  Compute them once during the premise pass, store in
  `clause_premise_line`, and look them up by clause identity.
- **Do not emit dead premises.** Only emit clauses that appear in
  `history`. A clause loaded into the KB but never used in this proof
  should not be a premise — verbose, and the `final-line == grounded
  query` test still passes either way, but it pollutes the rendered
  proof.

---

## 10. Test strategy

**Per-demo end-to-end** (the gold-standard tests):

For each of demos 1–4:
1. Construct the KB programmatically.
2. Build a deterministic picker that follows the canonical solution.
3. Run `manual_solve` (or, while `manual_solve` is being implemented,
   a thin harness that invokes `resolve` in sequence then `render`).
4. Assert `check_proof(proof) == Verified()`.
5. Assert `proof.lines[-1].formula == apply_to_formula(saturated, query)`.
6. Assert `proof.goal == apply_to_formula(saturated, query)`.
7. Snapshot the line count and a few key formulas, so accidental
   regressions are visible.

**Property tests** (Hypothesis):

- *No metas in output.* For any randomly-generated successful trace,
  `_formula_contains_meta(line.formula) is None` for every line.
  (The kernel's §5.3 backstop catches this, but the renderer should
  never produce one — fail fast in the renderer's tests, not in the
  kernel's defense.)
- *Rule alphabet bound.* Every `RuleApp` in the rendered proof uses a
  rule from `{"forallE", "impE", "andI"}`. (Plus `Premise` and
  `Assumption` justifications, but `Assumption` should never appear.)
- *Premise correspondence.* Every `Premise` line corresponds to a
  clause in the input KB (set membership), and every clause appearing
  in `history` has a `Premise` line.
- *Final-line invariant.* `proof.lines[-1].formula ==
  apply_to_formula(saturated, query)`.
- *Saturation idempotence.* `_saturate(_saturate(s)) == _saturate(s)`.
  (Sanity for the helper.)
- *Var-map totality.* For every `step` and every name returned by
  `_vars_in_order(step.clause_used)`, `extract_var_map(...)`
  contains that name.
- *Kernel acceptance.* For every randomly-generated successful trace,
  `check_proof(render(...)) == Verified()`. This is the cheap
  end-to-end soundness check.

**Adversarial unit tests:**

- Fact with variables (e.g. `parent(X, X).`): premise is
  `∀X. parent(X, X)`. SLD should bind `X` and `forallE` should
  ground correctly.
- Clause that uses a variable only in the body (e.g. `q :- p(X).`):
  premise is `∀X. (p(X) → q)`. Standard.
- Clause body atoms that share a variable: `r(X) :- p(X), q(X).`
  Premise is `∀X. ((p(X) ∧ q(X)) → r(X))`. The two body subproofs
  must produce *the same* ground form for X.
- Same clause used three times in one trace (deeper recursion than
  Demo 4): three independent fresh-meta sets, three `forallE`
  chains, three `impE` lines. Same premise reused.

---

## 11. Closing notes from the design pass

**Hardest case to work out by hand:** Demo 1 (kinship, recursive). The
two-step body decomposition for c4 — building `(parent(alice, bob) ∧
ancestor(bob, carol))` by combining one premise (line 1) and one
recursively-derived line (line 7) — is where the algorithm's
recursion structure has to be exactly right. Demo 4's recursion is
linear (single-body clause); Demo 1's c4 is the first place a
multi-body recursive clause forces the renderer to interleave
*premise-derived* body atoms (parent(alice, bob)) with
*subproof-derived* body atoms (ancestor(bob, carol)) inside one `andI`.

**Edge case that caused me to revise the algorithm:** Equals atoms in
clause heads/bodies (§7.7). My first instinct was to emit `eqRefl`
for the trivial `t = t` case and `eqSubst` for rewriting; but neither
is needed, and adding them would push the renderer's rule alphabet
past the M1 minimum. The principled answer is that equality reasoning
in M1 happens entirely through user-supplied clauses, not through
kernel equality rules. Flagged in §7.7 and §9 so the implementer
doesn't reintroduce them out of misplaced helpfulness.

**What I'd want clarified about the kernel rule API before
implementation starts:**

- The `forallE` rule expects `extra["term"]` to be a `Term`. The
  serialiser at `src/hlmr/ir/serialise.py` wraps it as
  `{"_type": "term", "value": ...}` for JSON; in-memory it's a raw
  `Term`. Confirming that `RuleApp.extra["term"]` should hold the
  raw `Term` (not a JSON dict) is a one-line check the implementer
  should make against the kernel's `_forallE` reader before assuming
  it. (The M0 proofs at `proofs/m0/07_forall_instantiate.json` and
  the kernel's `_forallE` show the in-memory side: the JSON shape is
  a serialiser concern, not a kernel concern.)
- `andI`'s `line_refs` order: the kernel uses
  `(left_ref, right_ref) → And(left, right)`. Confirmed by reading
  `_andI`. The renderer must therefore pass body atoms in the same
  order they appear in the clause body.
- No clarification needed for `impE`, `forallE`, `Premise` — all
  uncontroversial.
