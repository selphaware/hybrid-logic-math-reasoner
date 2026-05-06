# HLMR Strategic Direction — Proof-Checked Theory Growth Engine

**Status:** Standing reference for the long-term vision (v1.1 — added §6.9 and §11.7 on contested mathematical content)
**Audience:** Anyone reading the HLMR repo who wants to understand where M3+ is heading
**Companion to:** `prd.md` (canonical project spec; this document defers to it on architectural commitments and milestone scope)
**Last updated:** 2026-05-06

---

## 1. One-sentence direction

> HLMR should evolve into a **proof-checked theory growth engine**:
> starting from axioms and proved theorems, it generates typed
> conjectures, filters and tests them, proves what it can using the
> M0–M2 machinery, and admits only kernel-checked theorems back
> into a growing reusable library.

The first concrete realisation is M3 (equivalence relations); the
direction extends across M4–M6+ to additional bounded domains.

---

## 2. The loop

```text
Start with a theory seed:
  - signature (sorts, predicates, functions)
  - axioms
  - definitions
  - already-proved theorems (if any)

Then repeatedly:
  1. Generate candidate conjectures, typed and structured.
  2. Filter nonsense: ill-typed, trivial, duplicate-modulo-renaming.
  3. Try to refute via countermodel search.
  4. Try to prove surviving conjectures using HLMR's proof machinery.
  5. Kernel-check every proposed proof.
  6. If verified, admit the theorem to the library with metadata.
  7. Use the expanded library to generate and prove deeper theorems.
  8. Re-rank theorems by usefulness; iterate.
```

In pseudocode:

```python
def theory_growth_loop(theory: TheoryLibrary,
                       budget: GrowthBudget) -> GrowthReport:
    candidates = generate_typed_conjectures(
        signature=theory.signature,
        templates=theory.templates,
        known_theorems=theory.theorems,
        budget=budget,
    )

    for conjecture in candidates:
        if not type_checks(conjecture, theory.signature):
            continue
        if is_trivial(conjecture):
            continue
        if is_duplicate_modulo_renaming(conjecture, theory):
            continue

        countermodel = try_find_countermodel(conjecture, theory)
        if countermodel is not None:
            theory.record_refuted(conjecture, countermodel)
            continue

        proof = try_prove(conjecture, theory,
                          budget=budget.proof_budget)
        if proof is None:
            theory.record_open(conjecture)
            continue

        result = check_proof(proof)
        if result.ok:
            theory.add_theorem(conjecture, proof)
        else:
            theory.record_failed_proof(conjecture, result)

    return build_growth_report(theory)
```

The invariant that makes the whole approach viable:

> **Only kernel-checked proofs create new theorems.**

Search may be wrong, incomplete, biased, or flat-out hallucinatory.
None of that admits a single false theorem to the library.

---

## 3. What this is

A **bounded, auditable, theory-growth workbench** where every
accepted theorem has a checked proof. The system "learns" because
its verified library grows over time, not because a neural model
updates weights.

The intended scale is small theories that can plausibly be grown
end-to-end:

- equivalence relations (M3 demo)
- partial orders (M4)
- toy geometry over `Point`/`Line` (M5)
- monoids and groups, simple number theory, finite combinatorics
  (M6+)

The intended user is someone who wants to explore the consequences
of a small axiom set in a verifiable way — a student, a researcher
working on a specific algebraic structure, a curriculum designer
building a guided derivation.

The system's growth output is a **reusable, replayable, kernel-
checked theorem library**, not a one-shot answer.

---

## 4. What this is not

The direction must not drift into discarded framings:

- **Not "all of mathematics."** Gödel forbids it for any consistent
  theory strong enough to express arithmetic.
- **Not a Mathlib clone.** See §11 for the substantive comparison.
- **Not a Lean or Coq replacement.** Different foundations, different
  scale, different community model.
- **Not a frontier neural prover.** No transformer, no learned tactic
  policy at the foundation level. An optional small ranker may earn
  its place much later (gated on logged-corpus volume, per
  `prd.md` §9), but the system must work fully without it.
- **Not an automated theorem prover for unrestricted math.** The
  fragment is bounded by the M0–M2 architectural commitments:
  first-order logic with sorts, linear arithmetic, finite domains,
  symbolic algebra dispatched to SymPy.
- **Not brute-force conjecture discovery.** Conjectures are generated
  through structured templates and informed recombination, never
  unstructured enumeration.

If a feature can only be justified by appeal to one of the above,
push back.

---

## 5. Why this works architecturally

The growth loop is viable because of HLMR's existing architectural
commitments — it does not require any of them to be relaxed:

- **The kernel is the only trusted component.** A conjecture
  generator may emit nonsense, a tactic may pursue a dead end, a
  countermodel finder may miss a refutation, an external solver may
  return a bad witness — none of that becomes accepted truth unless
  the kernel checks the proof. The growth loop is *all construction*;
  the kernel is *all verification*.
- **The IR is the single bus.** Theorems, axioms, and conjectures
  are all the same `Formula` types. There is no separate
  representation that lets unverified content sneak past the
  trust boundary.
- **Construction and verification are separated.** Conjecture
  generation is construction. Proof search is construction.
  Countermodel search is filtering. Kernel checking is the only
  thing that creates "admitted" status.
- **Soundness over completeness.** False negatives (conjectures
  the system fails to prove that are in fact true) are acceptable
  and expected. False positives (claiming a theorem is verified
  when its proof is invalid) are catastrophic and prevented by
  routing every proof through the kernel.

These commitments are already in place by end of M2. The growth
loop is *additive* — new modules around the existing architecture,
not modifications to it.

---

## 6. Core concepts

### 6.1 Theory signature

A theory signature defines the language of a domain.

```text
Equivalence relations:
  Sorts:      Obj
  Predicates: R(Obj, Obj)

Partial orders:
  Sorts:      Obj
  Predicates: leq(Obj, Obj), eq(Obj, Obj)

Toy geometry:
  Sorts:      Point, Line
  Predicates: incident(Point, Line),
              between(Point, Point, Point),
              collinear(Point, Point, Point),
              neq(Point, Point)
```

M3 introduces lightweight argument-position sort tags so the
conjecture generator can reject ill-typed candidates. Full
multi-sort logic is parked as an M4 design decision (see `prd.md`
§7.6 and §12).

### 6.2 Axiom base

A theory seed contains axioms and definitions. Start small.

```text
equivalence_relation:
  reflexive:   ∀x.       R(x, x)
  symmetric:   ∀x y.     R(x, y) → R(y, x)
  transitive: ∀x y z.   R(x, y) ∧ R(y, z) → R(x, z)
```

Do not begin with full Hilbert geometry or any axiom system that
requires more than a handful of axioms to state. Tiny seeds make
the loop's behaviour visible; large seeds hide it.

### 6.3 Typed conjecture generation

The generator only proposes statements that make sense according
to the theory signature.

Invalid (rejected by sort-checking):

```text
between(A, line_l, C)
parallel(point_a, point_b)
incident(line_l, point_a)
```

Valid:

```text
between(A, B, C)
incident(A, l)
collinear(A, B, C)
```

Generation works through typed templates:

```text
P → Q                                        (implication)
P ∧ Q → R                                    (conjunction antecedent)
∀ vars. assumptions → conclusion             (universal)
P(x, y) → P(y, x)                            (symmetry shape)
P(x, y) ∧ P(y, z) → P(x, z)                  (transitivity shape)
P → Q  ⇒  Q → P  /  ¬Q → ¬P                  (converse, contrapositive)
P(x) holding for all examples seen           (generalisation)
```

The generator must reject conjectures with free variables in the
conclusion that aren't bound or existentially introduced. The
following is bad:

```text
∀ A B. incident(A, l) → incident(B, m)
```

`l` and `m` are unbound; this isn't a well-formed universal
statement.

### 6.4 Creative search

"Creative" does not mean unconstrained. It means structured
mechanisms for proposing candidates the templates wouldn't reach
on their own:

- **Recombination of existing theorems.** Given two proved theorems
  with shared predicates, try chaining them. This is the mechanism
  that makes the library *grow*: theorem N+1 is built from the first
  N, not invented from scratch.

  ```text
  Given:  between(A,B,C) → collinear(A,B,C)
          collinear(A,B,C) → collinear(C,B,A)
  Generate: between(A,B,C) → collinear(C,B,A)
  ```

- **Mutation of known statements.** Given `P → Q`, generate
  `Q → P`, `¬Q → ¬P`, `P ∧ R → Q`, `P → Q ∨ R`, and so on. Most
  mutations will be false. That is fine if filters and countermodel
  search reject them.

- **Missing-lemma generation from failed proofs.** When proof search
  for target `T` gets stuck at "have `P`, need `Q`," propose `P → Q`
  as a sub-conjecture. If proved, retry `T`. This makes proof
  failure *informative* — failures generate new conjectures rather
  than dead-ending.

- **Generalisation from examples.** When several specific instances
  of a pattern have been proved, propose the universal generalisation.

- **Analogy.** When predicate `P` and predicate `Q` have similar
  axiom structure, transport theorems about `P` to candidates
  about `Q`.

### 6.5 Counterexample search

Before expensive proof search, try to refute. For finite or
finitely-approximated domains, enumerate small models or route to
Z3 model search via the M2 bridge.

Example false conjecture:

```text
∀ A B C. collinear(A, B, C) → between(A, B, C)
```

A countermodel exists: three points all on a line, none "between"
the other two in the geometric sense. The countermodel finder
returns the witness model; the conjecture is recorded as
`refuted_by_countermodel` with the witness, not silently discarded.

The loop becomes:

```text
Generate conjecture
  → Try to kill it
  → If not killed, try to prove it
  → If proved, admit it
  → If neither killed nor proved, mark open
```

### 6.6 Proof search

Proof search reuses the M0–M2 machinery: SLD resolution, kernel
rules, dispatcher. M3 adds:

- **Tactic priority list.** Try axioms first, then short library
  theorems, then longer ones, then generic ND moves.
- **Iterative deepening.** Per-attempt time and depth budgets.
- **Premise selection.** With a library of 50 theorems, blind
  search is hopeless. Cheap heuristic that goes a long way:
  predicate-symbol overlap between the goal and theorem statements.
  Better heuristic: usefulness score (§6.8) biased toward theorems
  that have unlocked previous proofs.
- **Lemma mining.** As described in §6.4 — failed proofs become new
  conjectures.
- **Optional learned ranker.** A small specialised model for
  conjecture or premise ranking, trained on the corpus of logged
  growth-loop steps. Gated on having ≥5,000 logged steps. The
  system must work fully without it.

Search is allowed to be incomplete. False negatives (failing to
find a proof that exists) are acceptable. False positives are not.

### 6.7 Theorem library

A proved theorem becomes a reusable library entry with metadata:

```json
{
  "name": "between_implies_reverse_collinear",
  "domain": "toy_geometry",
  "statement": "forall A B C. between(A,B,C) -> collinear(C,B,A)",
  "variables": {
    "A": "Point",
    "B": "Point",
    "C": "Point"
  },
  "dependencies": [
    "between_implies_collinear",
    "collinear_reverse"
  ],
  "proof_hash": "sha256:...",
  "proof_status": "kernel_checked",
  "usable_as_lemma": true,
  "usefulness_score": 0.42,
  "created_by": "theory_growth_loop",
  "created_at": "2026-05-06T14:32:11Z"
}
```

The proof itself remains exportable and replayable through the
kernel. No theorem is ever stored as merely "believed."

Status values:

```text
kernel_checked              — admitted; usable as lemma
external_checked            — verified by an external system (rare; M6+)
refuted_by_countermodel     — false; recorded with witness
open                        — proof attempt timed out, status unknown
failed_proof_attempt        — proof search exhausted without success
duplicate                   — equivalent to existing theorem under renaming
trivial_rejected            — rejected by triviality filter
outside_fragment            — required reasoning beyond HLMR's fragment
```

There is a meaningful distinction between a *proved archive
theorem* and an *active reusable lemma*. Not every kernel-checked
theorem should be high-priority for premise selection; the
usefulness score (§6.8) is what surfaces the genuinely reusable
ones.

### 6.8 Theorem usefulness scoring

Without usefulness filtering, the library fills with true but
useless theorems:

```text
P → P
P ∧ Q → P
R(x, y) → R(x, y)
```

The triviality filter catches the most obvious cases, but plenty
of "true but uninteresting" theorems slip through. Usefulness
scoring surfaces the ones worth promoting to the active reusable
lemma set.

Scoring inputs:

- proof reuse frequency (how often this theorem appears as a
  dependency in other proofs)
- proof shortening (does using this theorem reduce average proof
  length for downstream theorems?)
- statement simplicity (Occam-style preference)
- low dependency cost (theorems that depend on few others are
  cheaper to verify and reuse)
- non-triviality (penalise tautological or near-tautological
  shapes)
- whether it unlocks previously-failed proofs
- whether it appears in multiple distinct proof paths

These signals are accumulated as the library grows and the loop
runs more iterations. Early in a theory's growth, the score is
necessarily noisy; later it stabilises.

### 6.9 Conventions as declared axioms

Some mathematical statements are contested between conventions
rather than universally true. The textbook example is `0^0`:
combinatorics, discrete maths, polynomial rings, and most
programming languages define it as 1; real analysis treats it as
undefined because the limit of `x^y` as both vary doesn't exist.
Both positions are correct within their domain. Other examples
in the same shape: the result of `mod` with negative operands
(C-style truncation versus Python-style floor); the empty
product (usually 1, but contextual); indexing conventions for
sums and products; branch-cut choices for `√` and `log`; the
behaviour of operations on empty sets, empty sequences, or zero
arguments. In each case, multiple internally-consistent
conventions exist and working mathematicians genuinely disagree
about which to adopt as default.

The principle: **the kernel never silently asserts a contested
statement.** When a conjecture or a proof step requires such a
statement, the kernel rejects, and the convention enters the
proof through a declared axiom in the theory seed. This keeps
the trust boundary clean (no domain-awareness in trusted code,
no configuration flags that could be misset) and makes every
admitted theorem self-documenting (its dependency chain shows
exactly which conventions it rests on).

Concretely, for `0^0`:

- The kernel's `arithEval` rule rejects `0^0` with
  `MalformedArithmetic` (per `prd_milestone_2.md` §6.4).
- A combinatorics theory seed that needs `0^0 = 1` declares it
  as an axiom (e.g. `axiom pow_zero_zero: 0^0 = 1`).
- A real-analysis theory seed simply doesn't declare it; any
  conjecture requiring `0^0` either fails to prove or finds a
  proof route that avoids the case.
- Any theorem that uses the convention cites `pow_zero_zero` in
  its dependency list. A reader can see at a glance which
  theorems are convention-dependent and decide for themselves
  whether to accept the convention.

For the M3 growth loop this creates a natural feedback path.
When proof search fails because a needed step requires a
convention not in the current axiom set, the system has options:

- Record the conjecture as `failed_proof_attempt` and move on —
  the safe default.
- Mine the missing convention as a sub-conjecture (per §6.4),
  attempt to prove it from existing axioms, and if that fails,
  record the convention itself as `open` — known to be needed
  for downstream theorems but not derivable from current axioms.
- Surface the open convention to the user: "Conjecture C
  requires `0^0 = 1` to be admitted as an axiom. Adopt this
  convention for the current theory? [yes / no / defer]" If
  accepted, the convention joins the axiom set as a
  *user-declared decision*, and the original conjecture goes
  back into the proof queue.

The third option — interactive convention adoption — is what
makes the system pedagogically transparent. The user sees that
adopting a convention is a choice they're making, not a hidden
assumption baked into the prover. The resulting library carries
that choice as a declared axiom any reader can inspect.

The pattern generalises. For any contested case, the design rule
is the same: kernel rejects on contested ground, theory seeds
declare conventions as axioms, the growth loop surfaces missing
conventions to the user as auditable decisions. This applies
uniformly to:

- Arithmetic edge cases (`0^0`, `0!`, integer division semantics
  with negative operands, `mod` semantics).
- Operator behaviour at boundary inputs (empty sets, empty
  sequences, the empty product, the empty sum).
- Order-of-arguments choices for non-commutative operations
  where multiple sensible conventions exist.
- Branch choices for multi-valued operations (`√`, `log`,
  fractional powers).
- Default behaviour of partial functions on inputs where they
  are not naturally defined.

In every case, the layer above the kernel is where flexibility
lives, where it is visible and audited. The kernel itself stays
uncompromisingly conservative.

---

## 7. Search as the central design problem

Search has two distinct halves with different shapes — this is
the most important architectural insight for M3.

**Half one: conjecture search.** The space of "candidate
statements" is wildly larger than the space of "interesting
candidate statements." Naive enumeration of all well-typed
formulas up to depth 3 over a small signature already yields
thousands of candidates per second, almost all garbage. The
generator's job isn't to enumerate, it's to *propose well*. This
is what templates, recombination, lemma mining, and
counterexample-guided refinement exist for.

**Half two: proof search.** Once a conjecture survives filters and
countermodel attack, you actually need to prove it. The honest
answer here is iterative deepening over a tactic priority list,
with premise selection being the single biggest lever. With a
library of 50 theorems, blind search is hopeless; you want to
surface the 3–5 plausibly-relevant theorems for the current goal.

Both halves are construction, not verification. Search can be
wrong, incomplete, or biased — none of that touches soundness
because the kernel checks every proof. This is what makes the
whole approach viable.

The hard problem is neither soundness nor completeness. It is
**growth-loop productivity**: keeping the conjecture/proof loop
generating useful theorems rather than noise. The demonstration
that matters in M3 is not "we proved 12 theorems" but "theorem 12
used theorem 7 used theorem 3, and the average proof length
dropped after lemma reuse kicked in." That is growth. That is
what distinguishes this from a one-shot prover.

Specific design questions worth Opus attention before any M3
implementation:

- How does premise selection scale? Linear scan over the library
  is fine at 50 theorems, hopeless at 5,000. Indexing structure
  from day one, or evolve it as the library grows?
- How aggressively does lemma mining run? Every failed proof, or
  only failures that reach a certain depth? Mined lemmas can flood
  the conjecture queue if unbounded.
- What is the time-budget shape? Per conjecture? Per growth-loop
  iteration? Adaptive based on observed productivity?
- How is loop health measured without manual inspection? The
  growth report needs to be designed before the loop is built,
  not after.

---

## 8. Domain progression

The recommended order, weakest to strongest, is:

| Stage | Domain | Why first / why later |
|---|---|---|
| M3 | Equivalence relations | Tiny language, familiar axioms, manageable proof search, many provable conjectures, many false ones, usefulness scoring testable |
| M4 | Partial orders | Second domain to validate that M3's loop generalises; forces the multi-sort design decision |
| M5 | Toy geometry (G0/G1) | First true multi-sort domain (`Point`/`Line`); validates the chosen sort layer |
| M6+ | Monoids, groups, simple number theory, finite combinatorics, geometry sub-tracks | Engine exists; new domains are content work |

Equivalence relations is the right first POC because:

- The language is tiny (one binary predicate, one sort)
- The axioms are familiar to anyone with a logic background
- Many generated conjectures are provable
- Many are false (depending on what the symmetry/transitivity
  shapes generate), exercising countermodel search
- Proof search is manageable in time and depth budgets
- Usefulness scoring is testable on a meaningful library size
- Any productivity failures show up immediately rather than being
  hidden in scale

Do not begin with geometry. Geometry has too many moving parts
(sort decisions, axiom choices, graphics-free geometric intuition)
for a first POC.

---

## 9. Geometry roadmap (sub-track in M5+)

Geometry is its own multi-stage track that lives inside M5 and
M6+ rather than appearing as numbered top-level milestones:

```text
G0  Toy typed geometry: Point, Line, incident, between, collinear,
    neq. Goal: prove 5–10 small theorems.

G1  Betweenness and collinearity theory: order properties,
    countermodel testing.

G2  Congruence theory: segments, angles, congruence predicates.

G3  Triangle theory: triangle definitions, simple congruence
    results.

G4  Parallel-line theory: parallel predicate, controlled axioms.

G5  Hilbert/Tarski-style formal geometry subset: pick one formal
    axiomatisation. Do not mix informal Euclid with formal
    Hilbert/Tarski axioms.

G6  Geometry conjecture growth loop: typed conjecture generation
    plus proof search plus library growth, demonstrated on
    geometric content.
```

Important warning: Euclid's original axioms are historically
beautiful but formally awkward. For machine reasoning, use a
precise formal axiom system — Hilbert-style, Tarski-style,
Birkhoff-style, or coordinate geometry over a specified field.

M5 covers G0–G1. G2–G6 belong to M6+ as separate, sequential
sub-milestones.

---

## 10. Relationship to external systems

A natural question, given the ambition of theory growth, is
whether HLMR will eventually integrate with established formal
mathematics infrastructure — Mathlib, Lean, Coq, Isabelle/HOL, or
neural systems like AlphaProof. The honest answer is **no, not in
any meaningful integration sense**, and this section explains why
the apparent limitation is in fact the right scoping.

### 10.1 Mathlib and Lean

Lean is dependent type theory. HLMR is first-order logic with
sorts. These are not different syntactic conventions wrapping the
same underlying logic — they are fundamentally different
foundations.

A typical Mathlib theorem about, say, topological groups uses
universe polymorphism, dependent types indexing types by terms,
typeclass resolution, and quotient types. None of this translates
into first-order logic without losing the structure that made it
expressible in the first place. The Mathlib theorems that *would*
translate cleanly (basic algebraic identities, order theory,
finite combinatorics) are exactly the ones HLMR can re-derive
from its own axiom seeds via the growth loop, so importing them
adds nothing.

There are three *limited* ways Mathlib touches HLMR's world
without requiring integration:

- **As a benchmark.** "Can HLMR's growth loop on group theory
  recover the basic group-theoretic theorems Mathlib has
  formalised?" This is a meaningful comparison metric for M6+
  once group theory becomes a domain seed. It is a metric, not
  an integration.
- **As an oracle for conjecture filtering.** Before spending
  proof-search budget on a conjecture, optionally query "does
  Mathlib have an equivalent statement?" If yes, the conjecture
  is worth pursuing. This does not compromise HLMR's soundness
  because the kernel still verifies. But it is an optional UX
  feature, not a foundation.
- **As inspiration for axiomatisation.** When designing a theory
  seed for a new domain, looking at how Mathlib axiomatises the
  analogous structure helps avoid known pitfalls. This is normal
  background research, not technical integration.

None of these justify building a Mathlib bridge as a milestone.
They justify *referencing Mathlib in documentation* when HLMR
adds a domain that Mathlib has also formalised.

### 10.2 Coq, Isabelle/HOL

Same situation as Lean, with different specifics. Coq is also
dependent type theory; Isabelle/HOL is higher-order logic. Both
are strictly more expressive than HLMR's first-order fragment.
Translation in either direction is a research project, not a
feature. HLMR's pitch is not "smaller Coq" or "smaller
Isabelle" — it is "different kind of tool."

### 10.3 Neural systems (AlphaProof, GPT-style provers)

A different category of comparison. Systems like AlphaProof use
massive search with neural ranking on top of Lean to attack
competition mathematics (IMO problems and similar). HLMR's
bounded growth-loop architecture is the wrong shape for that
target. Different toolset, different goal.

The optional small ranker mentioned in `prd.md` §9 and §6.6 of
this document is *not* an attempt to compete with AlphaProof.
It is a learned re-ranking layer over already-bounded
template-driven generation. Its job is to surface the best of
the candidates the templates already produce, not to invent
candidates from a vast neural space.

### 10.4 Where HLMR has the genuine edge

HLMR's coherent pitch in the broader landscape:

- **Auditability.** Small kernel, in-repository, readable in a
  single sitting. Lean's kernel is small but the surrounding
  Mathlib ecosystem is gigantic. AlphaProof's neural component
  is opaque by construction.
- **Bounded scope.** A user can reason about exactly what HLMR
  can and cannot do without tracing through a million lines of
  formalisation.
- **Pedagogical visibility.** The growth loop produces a watchable
  artefact: theorems appearing one by one, with dependencies and
  reuse statistics. This is genuinely educational in a way that
  Mathlib's monolithic library is not.
- **Decidable fragments.** Linear arithmetic, finite domains,
  equational theories — HLMR handles these natively rather than
  embedding them in a more general framework.

The right framing is: if a user wants to formalise research
mathematics, they should use Lean. If they want to attack
competition problems, they should use AlphaProof or similar. If
they want to grow a verified library of consequences from a
small axiom set in a bounded domain, with a small kernel they
can audit and a watchable growth process — that is HLMR.

---

## 11. Development principles

### 11.1 Preserve the architectural commitments

Do not rewrite the kernel. Do not weaken proof checking. Do not
let conjecture generation bypass the IR. Do not allow generated
theorems to become premises unless their proof was kernel-checked.

These are restated in `prd.md` §4 and apply to every M3+
milestone without exception.

### 11.2 Construction and verification stay separate

Conjecture generation is construction. Proof search is
construction. Countermodel search is filtering. Kernel checking
is verification. Only verification creates accepted theorem
status.

### 11.3 Start tiny

The first POC is equivalence relations, not geometry. Each new
domain begins with the smallest plausible axiom seed. Resist the
temptation to seed M5 with a full Hilbert axiomatisation; G0/G1
exists for a reason.

### 11.4 Avoid unrestricted generation

Every conjecture must pass: type check, variable-binding check,
triviality check, duplicate-modulo-renaming check, depth and
variable-count budgets. The conjecture filter is the dam between
"infinite candidate space" and "manageable queue."

### 11.5 Log everything

Every generated conjecture is logged with: generation template,
type-check result, filter decisions, countermodel result, proof
attempt result, kernel-check result, final status, usefulness
score updates. These logs are the corpus for any future learned
ranker, and the raw material for growth reports. Schema-versioned
per `prd.md` §8.3.

### 11.6 Productivity is the metric, not theorem count

The success of a theory-growth run is measured by reuse and
proof shortening, not by raw theorem count. A library of 12
theorems where later proofs reuse earlier ones is a far better
result than a library of 200 disconnected facts.

### 11.7 Contested mathematical content stays out of the kernel

The kernel never silently asserts a statement on which
mathematicians genuinely disagree. Contested cases (`0^0`, `mod`
with negative operands, empty product behaviour, branch-cut
choices, and similar) are rejected at the kernel level and
admitted (or not) through declared axioms in the relevant theory
seed. See §6.9 for the full pattern.

This preserves the trust-boundary discipline — the kernel has no
notion of "domain" or "convention" and cannot be misconfigured
into a soundness violation — while leaving conventions fully
expressible at the axiom layer where they are visible, auditable,
and (in the M3 growth loop) interactively adoptable by the user.
The kernel stays uncompromisingly conservative; flexibility
lives one layer up.

---

## 12. Success criteria for the first POC (M3 demo)

A minimal successful M3 POC demonstrates:

1. A small theory seed (the three equivalence-relation axioms)
   loads correctly.
2. Typed conjectures are generated within depth and variable
   budgets.
3. Invalid, trivial, and duplicate conjectures are filtered with
   measurable rejection rates.
4. Some false conjectures are rejected by countermodel search
   (or by proof failure).
5. Some true conjectures are proved.
6. Every accepted proof is kernel-checked.
7. Proved theorems are stored with proof hashes and dependency
   metadata.
8. A later proof uses an earlier generated theorem (the critical
   growth signal).
9. A growth report shows library expansion over time.

Example growth report shape:

```text
Theory: equivalence_relation
Seed axioms: 3
Generated conjectures: 250
Filtered trivial: 90
Filtered duplicates: 40
Countermodels found: 35
Proof attempts: 85
Kernel-checked theorems added: 12
Active reusable lemmas: 5
Average proof length before lemma reuse: 9.2
Average proof length after lemma reuse: 5.1
```

The key signal:

> The system did not merely prove isolated theorems. It used newly
> proved theorems to prove further theorems, and the average proof
> length dropped measurably as a result.

That is growth. That is what M3 has to demonstrate.

---

## 13. Long-term ambition

The long-term ambition is not "all of mathematics" and not
"compete with Mathlib." It is:

> For a chosen formal domain, HLMR can grow a useful theorem
> library from a small axiom base through checked
> conjecture/proof cycles, with the growth process itself being
> a watchable, auditable, replayable artefact.

Suitable domains, in roughly increasing difficulty:

- equivalence relations (M3)
- partial orders (M4)
- toy geometry (M5)
- monoids and groups (M6+)
- simple number theory over M2's arithmetic (M6+)
- finite-domain combinatorics (M6+)
- formal-geometry subsets (M6+)
- domain-specific reasoning libraries (M6+)

This is where HLMR becomes genuinely interesting. Not as a
Mathlib clone. Not as a frontier prover. As a **bounded
theory-growth laboratory** with a small trustworthy core.
