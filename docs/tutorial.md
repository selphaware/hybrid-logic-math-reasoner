# HLMR M2 — A Tutorial

This tutorial takes you from a fresh checkout to fluent use of HLMR's M2
capabilities: mixed logical-and-arithmetic queries, kernel-verified proofs
through Z3 and SymPy, and the system's deliberate limits.

The audience is someone learning logic or formal methods who wants a
working theorem prover small enough to read end-to-end. No prior HLMR
experience is assumed; familiarity with first-order logic and natural
deduction will help you read the proofs.

---

## 1. What HLMR is

HLMR is a small theorem prover with two interlocking commitments:

- **The kernel is the only trust boundary.** A 600-line module
  implements 23 natural-deduction rules and nothing else. Every claimed
  proof — no matter how it was constructed — runs through this kernel
  before being reported as verified. Construction may be wrong;
  verification cannot.

- **The fragment is bounded.** First-order Horn-clause logic with
  quantifiers (M0–M1), plus linear arithmetic over ℤ and ℚ, finite-domain
  constraints, and symbolic algebraic equations dispatched to SymPy (M2).
  Anything outside that fragment — transcendentals, non-linear real
  analysis, geometry, set theory beyond finite sets — is honestly
  rejected rather than guessed at.

The intended user is a student or researcher exploring the consequences
of a small axiom set in a verifiable way. Every theorem HLMR admits comes
with a Fitch-style proof you can audit step by step. See
[`docs/strategic_direction.md`](strategic_direction.md) for the long
version of the vision: M3 onwards, the system grows reusable theorem
libraries from small axiom seeds via conjecture generation, countermodel
search, and proof attempts on the survivors.

What HLMR is **not**: not a Mathlib clone, not a Lean replacement, not a
neural prover, not "all of mathematics." Different foundations,
different scale, different community model. Scope discipline is
load-bearing.

---

## 2. Installation and first run

```bash
git clone <repo-url> hlmr
cd hlmr
python -m venv env_hlmr
.\env_hlmr\Scripts\Activate.ps1   # Windows / PowerShell
# or: source env_hlmr/bin/activate # Linux / macOS

pip install -e ".[test]"
```

The install brings in `lark` (parser), `prompt_toolkit` (REPL),
`z3-solver`, and `sympy`. Z3 and SymPy are M2 runtime dependencies;
M0 and M1 only need stdlib.

Now run the canonical M2 demo:

```bash
python -m hlmr demo prime_search
```

Expected output:

```text
Solved: ?P = 5
1. prime(5)                             Premise
2. >(5, 2)                              arithEval
3. <(5, 6)                              arithEval
4. !=(5, 4)                             arithEval
5. (prime(5) & >(5, 2))                 andI 1, 2
6. ((prime(5) & >(5, 2)) & <(5, 6))     andI 5, 3
7. (((prime(5) & >(5, 2)) & <(5, 6)) & !=(5, 4))  andI 6, 4
```

The query was `?- prime(?P), greater_than(?P, 2), less_than(?P, 6),
not_equal(?P, 4).` — find a prime strictly between 2 and 6 that is not
4. The only answer is 5. The system found it, the kernel verified the
proof, and the seven lines on your screen are the full audit trail.

That proof JSON is also written to `proofs/m2/prime_search.json` for
later inspection.

---

## 3. Anatomy of a Fitch proof

Read line 1 first. `prime(5)` is justified as `Premise`: it was supplied
to the system as a fact in the knowledge base, so the proof is allowed
to assume it. Proofs always start with their premises explicit.

Lines 2–4 use a rule called `arithEval`. This is the M2 addition to the
kernel: a rule that accepts a ground arithmetic atom (no variables, no
unknowns, just numbers and operators) iff that atom is true under exact
integer/rational evaluation. So:

- Line 2: `5 > 2` → evaluator computes `5 > 2 = True` → accept.
- Line 3: `5 < 6` → `True` → accept.
- Line 4: `5 != 4` → `True` → accept.

`arithEval` takes no premises and no references to earlier lines. Truth
is read off the formula in isolation. (See
[`src/hlmr/kernel/ARITH_EVAL_DESIGN.md`](../src/hlmr/kernel/ARITH_EVAL_DESIGN.md)
§3 for the formal contract.)

Lines 5–7 use `andI` (and-introduction): given two earlier lines, derive
their conjunction. The chain is left-associated:

- Line 5: combine line 1 and line 2 → `prime(5) & 5>2`.
- Line 6: combine line 5 and line 3 → `(prime(5) & 5>2) & 5<6`.
- Line 7: combine line 6 and line 4 → `((prime(5) & 5>2) & 5<6) & 5!=4`.

The final line is the conjunction of all four query goals with `?P`
substituted to 5. That final formula is what the kernel calls the
proof's `goal`, and what `check_proof` matches against the last
line's formula before reporting `Verified`.

A few things to notice:

**The rule alphabet is tiny.** Six rule names appear in M2 proofs:
`Premise`, `forallE`, `andI`, `impE`, `arithEval`, `eqRefl`. M0/M1
proofs use the first four; M2 adds the last two. The kernel implements
23 rules total but the renderer only emits these six — anything else
in a rendered M2 proof is a bug. Conservatism in the rendered alphabet
makes proofs easier to read and easier to trust.

**Every line is independently checkable.** The kernel walks the
proof line by line, applying each rule's checker to each line's
formula and references. A line that doesn't typecheck against its
rule fails the whole proof. There is no implicit machinery that
fixes things up. This matters because it means you, reading this
proof, are doing the same thing the kernel just did: checking each
inference against a rule you can name.

**The arithmetic and the logic share one proof format.** Line 1
came from the knowledge base via SLD resolution. Lines 2–4 came from
Z3. Lines 5–7 stitch them together. All seven are kernel-verified
the same way. There is no separate "arithmetic verifier" alongside
the logical kernel — `arithEval` is just another ND rule.

---

## 4. Writing your own queries — the REPL

The four demos run programmatic IR construction. To type queries
yourself, start the REPL:

```bash
python -m hlmr repl
```

```text
HLMR REPL — session 2026-05-10T13-34-46_807670b1
M2: M2 arithmetic enabled
Type ':help' for commands.

kb>
```

The `kb>` prompt is **knowledge-base mode**: any line ending in `.` is
a clause that gets added to the KB. The `:query` command switches to
query mode (`?- ` prompt). Some commonly useful meta-commands:

```text
:load examples/m1/kinship.pl   load clauses from a .pl file
:show kb                        list current KB
:show last                      display the last successful proof
:export proof.json              save the last proof
:solver                         show the most recent dispatcher decision
:query / :edit                  switch between query and KB mode
:quit                           exit
```

### A pure-logic query

Load the kinship example and ask who's an ancestor of `carol`:

```text
kb> :load examples/m1/kinship.pl
  Loaded 4 clause(s) from 'examples/m1/kinship.pl'.

kb> :query
Switched to query mode. Type '?- goal.' to query.

?- ancestor(?A, carol).

Goal (1 remaining): ancestor(?A, carol)
Candidates:
  1. ancestor(X, Y) :- parent(X, Y).  (rule, ancestor_1)
  2. ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).  (rule, ancestor_2)

> 2
... (further picks for the body atoms)

Solved: ?A = alice
Proof: 12 lines, kernel-verified.
```

You picked the recursive `ancestor` clause; the system unified its head
with your goal, then asked you to resolve each body atom in turn.
`parent(alice, bob)` and `ancestor(bob, carol)` discharge the body, and
the renderer assembles a 12-line ND proof through `forallE`, `andI`, and
`impE`. This is exactly M1 behaviour — adding M2 doesn't change anything
about how KB-only queries work.

### A pure-arithmetic query

```text
?- plus(2, 3, ?Z).

Dispatching: plus(2, 3, ?Z) (z3)

Solved: ?Z = 5
Proof: 1 lines, kernel-verified.

?- :show last
1. plus(2, 3, 5)                        arithEval
```

No KB clauses needed. The dispatcher saw `plus/3` (an arithmetic
predicate per [DISPATCH_DESIGN §4.2](../src/hlmr/dispatch/DISPATCH_DESIGN.md)
rule C3), routed to Z3, got the binding `?Z = 5`, constructed the
ground atom `plus(2, 3, 5)`, and verified it via `arithEval`. One line,
done.

The dispatcher uses **verify-before-return**: whatever Z3 says, the
kernel double-checks before any binding is reported as solved. If Z3
ever returned a witness the kernel rejects, the dispatcher would crash
with `SolverKernelDisagreement` rather than emit an unverified proof.
That's the M2 trust story made operational.

### A query with one unknown

```text
?- minus(?X, 3, 7).

Dispatching: minus(?X, 3, 7) (z3)

Solved: ?X = 10
Proof: 1 lines, kernel-verified.
```

`minus(a, b, c)` means `a - b = c`, so HLMR solved for `a = 10`. Same
shape as `plus`; works for `times` and `divides` likewise.

### A simple equation

```text
?- ?X = 5.

Dispatching: ?X = 5 (z3)

Solved: ?X = 5
Proof: 1 lines, kernel-verified.

?- :show last
1. (5 = 5)                              eqRefl
```

Notice the proof uses `eqRefl` (reflexivity of equality), not
`arithEval`. Once `?X` was bound to `5`, the ground atom became
`Equals(5, 5)` — both sides syntactically identical — and the renderer
preferred `eqRefl` to `arithEval`. Both rules accept this case;
`eqRefl` reads more naturally for trivial reflexive equalities. (See
[RENDER_M2_DESIGN §4.4](../src/hlmr/solve/RENDER_M2_DESIGN.md) for the
policy.)

### A query that fails — underdetermined

```text
?- plus(?X, ?Y, 10).

Dispatching: plus(?X, ?Y, 10) (z3)

Query underdetermined: Underdetermined: partial binding {?X = 10, ?Y = 0}; unbound: ?Y, ?X
```

There are infinitely many `(?X, ?Y)` pairs summing to 10. Z3 returned
one (`(10, 0)`) but the dispatcher's add-negation-and-recheck step found
a second satisfying assignment, so the outcome is `Underdetermined`
rather than `UniqueSolution`. The system reports the partial binding
honestly and refuses to render a proof — which is correct, because no
particular assignment is *the* answer.

This is the M2 underdetermination outcome made visible. It generalises
the M1 `(subst, None)` return for queries where SLD finds a saturated
substitution that still contains free metavariables. The principle: the
system never picks one of many equally-valid witnesses without a
specific reason to.

### Multi-goal queries and arithmetic operators

The M2 parser accepts three forms of syntax that the M1 parser did not:
comma-separated multi-goal queries, comparison and arithmetic operator
atoms (`<`, `<=`, `>`, `>=`, `!=`, `+`, `-`, `*`, `/`, `^`), and
rational literals (e.g. `3/4` lexed as `Const(Fraction(3, 4))`).

The `prime_search` demo from §2 can now be typed directly in the REPL:

```text
kb> prime(2).
  Added: prime(2).
kb> prime(3).
  Added: prime(3).
kb> prime(5).
  Added: prime(5).
kb> prime(7).
  Added: prime(7).
kb> :query
Switched to query mode. Type '?- goal.' to query.

?- prime(?P), ?P > 2, ?P < 6, ?P != 4.

Goal (4 remaining): prime(?P)
Candidates:
  1. prime(2).  (fact, prime_1)
  2. prime(3).  (fact, prime_1)
  3. prime(5).  (fact, prime_1)
  4. prime(7).  (fact, prime_1)

> 3
Dispatching: >(5, 2) (z3)
Dispatching: <(5, 6) (z3)
Dispatching: !=(5, 4) (z3)

Solved: ?P = 5
Proof: 7 lines, kernel-verified.
Type ':show last' to display, ':export proof.json' to save.
```

Picking candidate 3 (`prime(5)`) binds `?P` to 5 and automatically
dispatches the three remaining goals. Comparison goals never prompt for
candidate selection — they route to Z3, which confirms each one, and the
kernel records an `arithEval` line. Only KB-routed goals show a candidates
list.

Polynomial expressions in `root_of` also work:

```text
?- root_of(?X, x^2 - 5*x + 6).
Dispatching: root_of(?X, +(-(^(x, 2), *(5, x)), 6)) (sympy)

Multiple solutions found. Pick one:
  [0] {?X = 2}
  [1] {?X = 3}

> 0

Solved: ?X = 2
Proof: 1 lines, kernel-verified.
```

Arithmetic expressions use standard precedence: `^` binds tightest, then
`*`/`/`, then `+`/`-`. The `Dispatching:` line shows the internal
prefix-form IR; `+(-(^(x,2), *(5,x)), 6)` is the prefix encoding of
`(x^2 - 5x) + 6`, matching the surface expression by standard
left-association of `+`/`-`.

**What is not yet supported:** typed metavariable annotations — `?X :
Integer`, `?X : Rational`, `?X : {2, 3, 5}`. A bare `?X` is a
metavariable with no declared kind, which is the M1 behaviour. Typed-meta
syntax requires an IR extension (`Meta.kind` field) that will ship in a
separate session.

---

## 5. The four demos in detail

The CLI ships four demos that exercise the full M2 capability. Each
runs end-to-end: dispatcher classifies, solver finds witnesses,
kernel verifies, renderer emits ND proof. Run them with `python -m
hlmr demo <name>`.

### 5.1 `prime_search` — the canonical mixed-goal example

This is the §2 motivating example of the M2 PRD: combine a logical KB
with arithmetic constraints and find a single witness that satisfies
both.

**KB**: `prime(2). prime(3). prime(5). prime(7).`

**Query**: `prime(?P), ?P > 2, ?P < 6, ?P != 4.`

**Output** (reproduced exactly from `python -m hlmr demo prime_search`):

```text
Solved: ?P = 5
1. prime(5)                             Premise
2. >(5, 2)                              arithEval
3. <(5, 6)                              arithEval
4. !=(5, 4)                             arithEval
5. (prime(5) & >(5, 2))                 andI 1, 2
6. ((prime(5) & >(5, 2)) & <(5, 6))     andI 5, 3
7. (((prime(5) & >(5, 2)) & <(5, 6)) & !=(5, 4))  andI 6, 4
```

**What happened, step by step:**

1. The dispatcher saw four goals in the query tuple and processed them
   left-to-right.
2. Goal 1 `prime(?P)` classified as a KB predicate. The demo's clause
   picker selected `prime(5)` from the four candidates, binding `?P` to
   `5`.
3. Goals 2–4 are arithmetic comparisons. After substitution, they became
   `5 > 2`, `5 < 6`, `5 != 4` — all ground. The dispatcher's
   ground-atom short-circuit (DISPATCH §11.5) verified each via
   `arithEval` directly without invoking Z3. Each became one line in
   the proof.
4. The renderer collected the four per-goal lines and emitted the
   `andI` chain to produce the conjunction.
5. `check_proof` walked the seven-line proof, checked every rule
   application, and returned `Verified`. The system reports success.

**Why this proof is interesting:**

Look at lines 1, 2–4, and 5–7 separately. Line 1 is logical: it came
from the KB via Horn-clause resolution — first-order machinery
unchanged from M1. Lines 2–4 are arithmetic: ground numeric atoms
verified by the new M2 rule. Lines 5–7 are propositional: standard
`andI` left-association from M0. Three different proof-construction
mechanisms produced lines that flow into one ND proof and verify
through one small kernel.

This is what "hybrid logic-math reasoner" means in practice. The
kernel doesn't know or care that line 1 came from SLD and line 2 came
from Z3; it just checks each line against its rule.

The picker in this demo is hard-coded to choose `prime(5)`. In the
REPL, you would pick interactively, and might first try `prime(2)` —
which would succeed for goal 1 but then `2 > 2` fails at goal 2,
returning `NoSolution`. You'd then try `prime(3)`, which succeeds:
`3 > 2`, `3 < 6`, `3 != 4` are all true, so `?P = 3` is also a valid
answer. The system isn't restricted to ?P=5; that's just what this
demo's picker happens to choose.

### 5.2 `quadratic` — symbolic algebra and `MultipleSolutions`

**KB**: empty.

**Query**: `root_of(?X, x^2 - 5*x + 6).`

**Output**:

```text
Solved: ?X = 2
1. (+(-(^(2, 2), *(5, 2)), 6) = 0)      arithEval
```

**What happened:**

`root_of/2` is a SymPy-routed predicate: it asks for the real roots of
the polynomial in its second argument. SymPy returned the finite set
{2, 3}. The dispatcher's outcome was `MultipleSolutions` with both
candidates pre-verified (SymPy's roots get plugged back into the
polynomial and checked against zero via `arithEval`).

The demo's `solver_picker` is hard-coded to pick index 0, which gave
`?X = 2`. The proof has one line: substituting 2 into the polynomial
and asserting the result equals 0. Reading the prefix-form output:
`(2^2 - 5*2) + 6 = 0` evaluates to `(4 - 10) + 6 = 0`, which is true.

**Why this is interesting:**

Two things make this demo non-trivial:

First, SymPy is doing genuine symbolic algebra — finding the roots of a
quadratic by factoring or applying the quadratic formula. The kernel
doesn't translate any of SymPy's internal proof; it just checks that the
witnesses SymPy produced satisfy the constraint. This is the
verify-before-return pattern in action.

Second, the `MultipleSolutions` outcome is real. If you call this demo
with `solver_picker=lambda sols: 1` instead, you get `?X = 3` and an
analogous proof. The dispatcher pre-verifies both witnesses; either is
sound to render. (See
[`src/hlmr/dispatch/DISPATCH_DESIGN.md`](../src/hlmr/dispatch/DISPATCH_DESIGN.md)
§3.1 for the full partitioning logic, including how `MultipleSolutions`
narrows to `UniqueSolution` or `NoSolution` if some witnesses are
contested-shape rejections.)

In the REPL, `MultipleSolutions` becomes interactive: the system shows
you the numbered list and asks you to pick one:

```text
Multiple solutions found. Pick one:
  [0] {?X = 2}
  [1] {?X = 3}
choice: 0
```

### 5.3 `linear_system` — multi-goal andI chain

**KB**: empty.

**Query** (programmatic): `?X = 2, ?X + ?Y = 10.`

**Output**:

```text
Solved: ?X = 2, ?Y = 8
1. (2 = 2)                              eqRefl
2. (+(2, 8) = 10)                       arithEval
3. ((2 = 2) & (+(2, 8) = 10))           andI 1, 2
```

**What happened:**

Two goals, both arithmetic, processed in order:

1. `?X = 2` is a linear equation classified as Z3. Z3 returned
   `?X = 2`. After binding, the ground atom is `Equals(2, 2)`, which
   the renderer recognised as syntactically reflexive and emitted as
   `eqRefl`.
2. `?X + ?Y = 10` becomes `2 + ?Y = 10` after applying the running
   substitution. One free meta. Z3 returned `?Y = 8`. Ground atom:
   `Equals(2 + 8, 10)`. Sides are syntactically distinct but evaluate
   equal — `arithEval`.
3. The renderer chained the two lines with `andI` into the multi-goal
   conjunction.

**Why this is interesting:**

This demo exhibits two M2 features at once.

The `eqRefl`/`arithEval` policy: the renderer prefers `eqRefl` for
syntactically reflexive equalities (cleaner proofs, no need to evaluate),
and falls back to `arithEval` when sides differ structurally even if
they evaluate equal. (Both rules are sound; the choice is cosmetic
plus a small efficiency win for very large constants.)

The multi-goal `andI` chain: M2 introduced query tuples (multiple goals
in one query), and the renderer ends multi-goal proofs with a
left-associated `andI` chain combining the per-goal final lines into a
single conjunction. M1 single-goal proofs end at the goal's final line
with no chain. M0/M1 proofs are unaffected.

A subtlety: the goals must be ordered so each goal's free metas can be
bound by the time it's dispatched. The query `?X + ?Y = 10, ?X = 2` —
same constraints in opposite order — would dispatch `?X + ?Y = 10`
first, find two free metas, run the underdetermination check, and
return `Underdetermined`. The dispatcher processes goals one at a time;
constraint-propagation across goals is M3 work. (See
[RENDER_M2_DESIGN §6.3](../src/hlmr/solve/RENDER_M2_DESIGN.md) for the
analysis.)

### 5.4 `outside_fragment` — honest rejection

**KB**: empty.

**Query** (programmatic): `root_of(?X, 2^x).`

**Output**:

```text
Demo completed: query correctly rejected as OutsideFragment.
No proof produced — honest rejection of an unsupported query shape.
```

**What happened:**

`2^x` has a variable in the exponent — it's a transcendental, not a
polynomial. The dispatcher's classifier (DISPATCH §4.2 rule C4) detects
this syntactically before any solver is invoked, and returns
`OutsideFragment(TRANSCENDENTAL)`. No proof is rendered, no witness is
reported.

**Why this is interesting:**

The `outside_fragment` outcome is a first-class result, not an error.
Six possible outcomes total (DISPATCH §3.1):

| Outcome | Meaning |
|---|---|
| `UniqueSolution` | One witness verified |
| `MultipleSolutions` | Finitely many witnesses, all verified |
| `InfinitelyManySolutions` | Reserved for M3+ |
| `NoSolution` | Constraint is unsatisfiable |
| `Underdetermined` | Witness exists but isn't unique |
| `OutsideFragment` | Goal isn't in M2's decidable fragment |

`OutsideFragment` further breaks down by reason:

| Reason | Trigger |
|---|---|
| `TRANSCENDENTAL` | exp/log/trig or `^` with variable exponent |
| `CONTESTED_CONVENTION` | currently only `0^0` (see below) |
| `UNRECOGNISED_SHAPE` | goal predicate not in the M2 set |
| `NON_LINEAR_BEYOND_SYMPY` | SymPy's roots aren't exact rationals (irrational-algebraic) |
| `SOLVER_TIMEOUT` | Z3/SymPy exceeded timeout |
| `SOLVER_UNKNOWN` | Z3 returned `unknown` |

The system reports *which* reason, not just "didn't work". When the
REPL polls `dispatcher.last_outside_fragment` after a `None` return,
it shows the user the specific classification and explanation. This
isn't graceful failure — it's a positive design commitment that the
tool is honest about its limits.

---

## 6. Boundaries — what HLMR won't do, and why

This section is as important as the four-demos walkthrough. The system
makes deliberate choices about what it refuses to attempt; understanding
those choices is essential to using HLMR well.

### 6.1 Transcendentals

```text
Query: root_of(?X, 2^x + 3*x - 5).
Dispatcher: REJECTED (TRANSCENDENTAL)
```

Anything with a `^` exponent that's a variable, or any unrecognised
function symbol like `sin`, `log`, `exp`, gets rejected. SymPy could
sometimes find numerical approximations to such roots, but a numerical
approximation is not a kernel-verifiable witness — `arithEval` works
on exact integers and rationals only. Rather than ship a proof that
relies on float arithmetic somewhere in its chain, HLMR rejects.

The conservative-default principle from
[`prd.md`](../prd.md) §4: "False rejections are acceptable; false
acceptances (claiming a verified proof when one is invalid) are
catastrophic." Transcendentals are out.

### 6.2 The 0^0 case — conventions as declared axioms

```text
Query: Equals(0^0, 1).
Kernel: rejects with MalformedArithmetic
```

`0^0` evaluates to `1` in Python (and most programming languages, and
combinatorics, and polynomial rings). It is **undefined** in real
analysis (the limit of `x^y` as both vary doesn't exist). Both
positions are correct within their domain; mathematicians genuinely
disagree about which to adopt as default.

The kernel takes neither side. `arithEval` rejects `0^0` with
`MalformedArithmetic` (see
[`ARITH_EVAL_DESIGN.md`](../src/hlmr/kernel/ARITH_EVAL_DESIGN.md) §6.1
for the rationale). This isn't an oversight; it's a design commitment
about the trust boundary. Silently inheriting Python's `1` would
commit the kernel to one side of a contested convention, baking a
mathematical opinion into the trusted code.

The principle generalises:
[`docs/strategic_direction.md`](strategic_direction.md) §6.9 calls it
"conventions as declared axioms":

> The kernel never silently asserts a contested statement. When a
> proof step requires such a statement, the kernel rejects, and the
> convention enters the proof through a declared axiom in the theory
> seed. This keeps the trust boundary clean (no domain-awareness in
> trusted code, no configuration flags that could be misset) and
> makes every admitted theorem self-documenting (its dependency
> chain shows exactly which conventions it rests on).

A combinatorics library that needs `0^0 = 1` would declare it as an
axiom (`axiom pow_zero_zero: 0^0 = 1`); a real-analysis library
wouldn't, and any proof requiring it would either fail or find a
route that avoids the case. This pattern lands properly in M3+; for
M2, the kernel rejection is the user-visible behaviour.

### 6.3 Underdetermined queries

```text
Query: plus(?X, ?Y, 10).
Outcome: Underdetermined: partial binding {?X = 10, ?Y = 0}; unbound: ?Y, ?X
```

When a goal has multiple satisfying assignments, the dispatcher's
add-negation-and-recheck step detects it and refuses to commit. The
system reports the partial binding it found (one specific witness,
plus the metas that aren't uniquely determined) and returns
`(subst, None)` — substitution but no proof.

Why no proof? Because rendering a Fitch proof for `?X = 10, ?Y = 0`
would assert that *this* assignment is the answer, when in fact any
`(a, 10-a)` pair would do. The system declines to fabricate a
spurious uniqueness claim.

This is also how HLMR handles "infinitely many solutions" cases. M2
unifies infinite-solution and finite-but-non-unique cases under
`Underdetermined`; M3 may distinguish them.

### 6.4 Equations with irrational solutions

```text
Query: root_of(?X, x^2 - 2).
Outcome: OutsideFragment(NON_LINEAR_BEYOND_SYMPY)
```

SymPy *does* solve `x^2 - 2` — it returns the finite set {-√2, √2}.
The HLMR SymPy bridge then inspects each root and tries to convert it to
an exact `int` or `fractions.Fraction`. That conversion fails for √2: it
is irrational and cannot be represented exactly in HLMR's arithmetic
fragment. The bridge synthesises a rejection rather than forwarding the
root, and the dispatcher reports `OutsideFragment(NON_LINEAR_BEYOND_SYMPY)`.

The connection to §3: `arithEval` verifies arithmetic atoms by exact
integer/rational evaluation. Even if the bridge passed √2 through, the
kernel could not evaluate `(√2)^2 - 2 = 0` soundly — it has no notion of
irrational constants. The bridge's rejection is the conservative-default
principle propagating from the kernel upward: don't construct a witness
that can't kernel-verify.

This applies to the whole class of polynomials with irrational-algebraic
solutions: cubics like `x^3 - 2` (cube root of 2), quartics like
`x^4 - 5x^2 + 6` (roots ±√2 and ±√3), quintics like `x^5 - x - 1`
(roots expressible only as `CRootOf`, no closed form in radicals at all).
All produce `OutsideFragment(NON_LINEAR_BEYOND_SYMPY)` via the same
element-inspection path in the bridge, regardless of what SymPy's
symbolic solver returns. (See
[`src/hlmr/solvers/sympy_bridge.py`](../src/hlmr/solvers/sympy_bridge.py)
`_finite_set_to_result` for the exact rejection logic.)

### 6.5 Typed metavariable syntax

The M2 parser extension (§4) brought operators, multi-goal queries, and
rational literals into the REPL. The one remaining parser limit is typed
metavariable annotations.

The bare `?X` form works as always. What the parser does not yet accept
is a kind declaration after the metavariable name:

```text
?- root_of(?X : Integer, x^2 - 5*x + 6).   ← parse error
?- prime(?P : {2, 3, 5, 7}).                ← parse error
```

A typed annotation would let you declare the search domain explicitly —
useful when a metavariable appears in several goals with conflicting
solver routes. The reason it isn't supported yet is an IR gap: the
`Meta` dataclass has no `kind` field and `MetaKind` doesn't exist. The
surface syntax and the dispatcher extensions are straightforward once
the IR is in place; they'll ship together in a focused session.

In the meantime, use bare `?X` and let the dispatcher's classification
rules determine the solver route automatically. If the route is
surprising, `:solver` after a query shows the classification decision
(see §7).

---

## 7. Inspecting dispatcher state with `:solver`

When a query doesn't behave as expected, `:solver` shows what the
dispatcher decided for the most recent goal it processed:

```text
?- plus(?X, ?Y, 10).
Dispatching: plus(?X, ?Y, 10) (z3)
Query underdetermined: ...

?- :solver
  Classification: route=z3
  Outcome: Underdetermined: partial binding {?X = 10, ?Y = 0}; unbound: ?Y, ?X
```

The output has three useful pieces:

- **Classification**: which route the goal was sent to (`kb`, `z3`,
  `sympy`, `rejected`). If your query was unexpectedly routed to KB,
  the predicate name might be in the KB; if it was rejected, the
  classifier didn't recognise the shape.
- **Outcome**: the specific dispatch result, formatted to be readable.
  For `OutsideFragment` outcomes, the reason and explanation are
  spelled out.
- **Outside-fragment**: shown when the most recent dispatch returned
  `OutsideFragment`; gives the same info as the outcome line for
  rejections, useful when scanning multiple recent dispatches.

For routine debugging:

- Got an unexpected `Outside-fragment` rejection? Check whether your
  predicate name matches one of the recognised arithmetic predicates
  (`<`, `<=`, `>`, `>=`, `!=`, `plus`, `minus`, `times`, `divides`,
  `root_of`) or your KB.
- Got an `Underdetermined` outcome on a query you expected to solve?
  You probably have more free metas than the constraint can pin down.
  Add another constraint, or query each meta separately.
- Got a `NoSolution` you didn't expect? The constraint really is
  unsatisfiable as stated; double-check the predicate semantics
  (e.g. `divides(a, b, c)` means `a / b = c`, not "a divides b").

Per-call lifecycle: `dispatcher.last_outside_fragment` and
`dispatcher.last_dispatch_result` are cleared at the start of every
`dispatch()` call and set at the end. So `:solver` always reflects the
most recent dispatch — a stale rejection from earlier in the session
won't bleed through into a successful query's `:solver` output. (See
[DISPATCH_DESIGN §11.3](../src/hlmr/dispatch/DISPATCH_DESIGN.md) for
the lifecycle contract.)

---

## 8. Where M2 ends and M3 begins

M2 ships the engine: the dispatcher, the bridges, the kernel rule, the
renderer extension. With M2, you can ask mixed logical-arithmetic
questions and get kernel-verified answers.

M2 does not yet do **automated theorem proving**. The M1 picker is
manual: you pick clauses; the system unifies. M2 added automatic
dispatch for arithmetic goals, but the search through the KB itself
is still user-driven. There is no proof search that tries clause
combinations on your behalf.

M3 is where that changes. M3 is the **theory growth engine**: starting
from a small axiom seed (the canonical demo is the three
equivalence-relation axioms), the system generates typed conjectures,
filters trivial/duplicate/ill-typed ones, refutes false ones via
countermodel search, attempts proof on the survivors, and admits only
kernel-checked theorems to a growing library. The success metric isn't
"we proved 12 theorems" but "theorem 12 used theorem 7 used theorem 3,
and the average proof length dropped after lemma reuse kicked in."

The architecture stays the same. The kernel is unchanged. The
conjecture generator, countermodel finder, proof-search engine, and
library-management are all *constructors* — they may be wrong,
incomplete, or biased without compromising soundness, because every
candidate proof still routes through the M0/M1/M2 verification stack.
M3 is additive, not a refactor.

For the long version, see
[`docs/strategic_direction.md`](strategic_direction.md) §1–§6. M3
through M6 are sketched there; M3 is the next milestone with a written
PRD.

---

## 9. References

Specs and designs (in the order you'd read them):

- [`prd.md`](../prd.md) — the canonical project spec. Read this first
  if you want to understand the architectural commitments that shape
  every milestone.
- [`prd_milestone_2.md`](../prd_milestone_2.md) — M2 spec; §3.3 lists
  the demos, §6 the IR/parser/kernel additions, §14 the
  definition-of-done checklist.
- [`docs/strategic_direction.md`](strategic_direction.md) — M3+ vision;
  §1–§6 the theory growth concept, §6.9 and §11.7 the conventions-
  as-axioms principle.

Implementation designs (Opus 4.7 design docs that the Sonnet
implementation builds against):

- [`src/hlmr/kernel/ARITH_EVAL_DESIGN.md`](../src/hlmr/kernel/ARITH_EVAL_DESIGN.md)
  — the `arithEval` rule. Precise contract, soundness argument, edge
  cases (0^0, 0^negative, non-integer exponents).
- [`src/hlmr/dispatch/DISPATCH_DESIGN.md`](../src/hlmr/dispatch/DISPATCH_DESIGN.md)
  — the dispatcher. Six outcomes, classification rules, Case 1/Case 2
  solver-kernel disagreement, contested-shape detection,
  `OutsideFragment` taxonomy.
- [`src/hlmr/solve/RENDER_M2_DESIGN.md`](../src/hlmr/solve/RENDER_M2_DESIGN.md)
  — the renderer extension. Six-rule alphabet, `eqRefl`/`arithEval`
  policy, multi-goal `andI` chain, depth-zero invariant.

Code starting points (in order of architectural depth):

- `src/hlmr/ir/` — the formula and proof types. Pure data; no logic.
- `src/hlmr/kernel/` — the trusted core. 23 ND rules.
  `test_kernel_isolation.py` enforces the no-imports-outside-stdlib-and-ir
  invariant.
- `src/hlmr/solve/` — SLD resolution, the renderer.
- `src/hlmr/dispatch/` — the M2 dispatcher; `classify.py` is pure
  classification, `route.py` runs the dispatch loop.
- `src/hlmr/solvers/` — the Z3 and SymPy bridges. The only files in
  the codebase that import `z3` or `sympy`.
- `src/hlmr/repl/`, `src/hlmr/parse/`, `src/hlmr/cli.py` — the user
  surface.

Tests:

- `tests/test_demos_m2.py` — the four demos as integration tests.
- `tests/test_render_m2.py` — renderer behaviour, including soundness
  backstops where a malicious renderer is caught by the kernel.
- `tests/test_dispatch_route.py` — the dispatcher with mock bridges.
- `tests/test_solvers_real.py` — the dispatcher with real bridges,
  end-to-end through Z3 and SymPy.
- `tests/test_kernel_arith_eval.py` — exhaustive accept/reject cases
  for the new kernel rule.

Run the full suite:

```bash
pytest tests/ -q
# 993 tests; ~3 minutes locally.
```

If everything's green, you have a working theorem prover that's
honest about its limits and small enough to read end-to-end. That's
the goal.
