# M2 Field Notes

Observations during hands-on use of M2 between milestone close and
M3 PRD design. The point is not bug reports — the test suite catches
bugs. The point is friction, surprises, design tensions, and
motivations for M3.

These notes were captured during the play-around phase immediately
following the M2 5c commit. Most observations are not defects;
they are M3 design inputs.

---

## REPL ergonomics

### Parser limits expose dispatcher capability the REPL can't access

The REPL parser was written for M1's first-order Horn-clause syntax
and doesn't accept symbolic operators (`+ - * / ^ < > <= >= !=`)
or comma-separated multi-goal queries. The dispatcher and renderer
fully support these — the four CLI demos exercise them via
programmatic IR — but they're unreachable from the REPL today.

Concrete: the first thing tried in the REPL was the quadratic
demo's query `?- root_of(?X, x^2 - 5*x + 6).`, which was rejected
with a parse error pointing at `^`. Documented in tutorial §6.5
but worth registering as real friction.

This is a high-priority near-term improvement (separate from M3's
scope). The REPL is currently effectively M1-only-with-predicate-
form-arithmetic. To experience M2's most interesting capabilities
interactively rather than only via CLI demos, the parser needs
extension. Folding it into M3 is defensible since M3 will need
richer syntax anyway, but the parser work itself is independent
of theory growth.

### `?- ?- query.` double-prefix behaviour is inconsistent

After `:query` switches to query mode, the prompt becomes `?-`. Typing
`?- balanced2(15).` at this prompt sometimes parses (the leading `?- `
is silently stripped) and sometimes errors with "in query mode use:
pick N, N, candidates, back, abort, or ?- goal.; got '...'". The
rule isn't obvious to a user. Worth either accepting consistently
(strip `?- ` if present in query mode) or rejecting consistently
with a clearer error.

### Duplicate clause additions silently succeed and conceal which rule is active

In `:edit` mode, typing the same rule twice — or adding two
versions of a rule with the same head predicate — produces multiple
"Added: ..." messages and multiple identical clause candidates with
the same internal name during query resolution.

This became a real problem during the integer-typing exploration:
adding a refined `even` rule alongside an earlier broken version
produced a candidate list showing both as `(rule, even_1)`. A user
picking option 1 by habit would silently get the original
broken-over-rationals version. This is no longer just visual noise
— it can mask which version of a rule is actually in use.

Recommend either deduplication on addition, distinct internal names
per syntactic instance, or a warning when a query matches multiple
clauses with the same name.

### Error message in query mode mixes command syntax

After `:query`, if a query is typed without the `?-` prefix mid-
session, the error reads:

> in query mode use: pick N, N, candidates, back, abort, or ?- goal.

This mixes resolution-step commands (`pick N`, `back`, `abort`)
with query-entry syntax (`?- goal.`). A new user reads this and
reasonably wonders "why does it list `?- goal.` as allowed when
that's exactly what I typed?" Better framing might separate
"currently in mid-resolution" from "ready for a new query" since
the allowed inputs differ.

### Picker UI is mandatory even when only one candidate exists

When SLD finds exactly one matching clause, the system still asks
the user to pick from a list of one. Fine for the pedagogical model
but slow for trivial queries. Consider auto-picking when there's
exactly one candidate, or add an `:autopick` mode for users
running through many examples.

---

## Proof readability

### Compositional proofs read beautifully

Three compositional theories were exercised end-to-end during play:

- `half_balanced(15, 5)` — 8-line proof combining KB resolution,
  arithmetic dispatch, and propositional combination.
- `quadruple(3, 12)` — 15-line proof with two-level rule composition,
  two arithmetic dispatches, all flowing into one coherent proof.
- `same_ratio_solving_d(2, 3, 4, 6)` — 10-line proof for ratio
  equivalence via cross-multiplication.

In each, the structure of the proof mirrors the structure of the
mathematical reasoning: prove inner facts first, combine via outer
rules. This is HLMR working at its design intent. A student could
read these proofs and follow the argument; the kernel verified
every step independently.

### Substitution-bound terms appear with `Fraction(...)` repr in proofs

When the dispatcher returns a rational witness, the rendered proof
shows it as `Fraction(5, 2)` rather than `5/2`. Technically correct
but reads less naturally for pedagogical proofs. This is a renderer
cosmetic issue — fix would be a small extension to term
pretty-printing. Doesn't affect any logic.

### Internal meta naming is detailed but readable

The "Solved" line for `quadruple(3, 12)` showed eight metas resolved
(`?X_1 = 3, ?M_3 = 6, ?X_4 = 3, ?Y_5 = 6, ...`) with redundancy
because each rule application produces fresh metas. Standard SLD
behaviour, handled correctly, but worth noting that the "Solved"
line gets longer with deeper rule composition. Could be filtered
to show only query-level metas (?X, ?Y as the user typed them) by
default, with all-internal-metas available via a flag.

---

## Fragment boundaries

### M2's arithmetic operates over ℚ, not ℤ

M2's dispatcher routes to Z3 with `z3.Real` variables (per Session
5a's "always Real" simplification, documented in z3_bridge.py).
SymPy uses `domain=S.Reals`. Both find rational solutions readily.

Predicate definitions that intuitively assume ℤ get rational
witnesses. `even(N) :- times(K, 2, N).` admits K = N/2 for any N
because ℚ is closed under division by 2. `?- even(5).` succeeds
with K = 5/2.

The IR has typed metavariables (`prd_milestone_2.md` §6.1) but the
dispatcher doesn't propagate them. They exist as data; they are
not used to constrain solver calls.

This is the strongest M3 motivation surfaced during play-around:
typed dispatch is needed for any integer-domain reasoning (number
theory, divisibility, parity, prime, counting). Without it, M2 can
only express integer-domain predicates via enumeration of ground
facts, which sacrifices inference structure.

### Across-goal constraint propagation is not in M2

Goals in a query body or query tuple are processed one at a time,
left-to-right. The dispatcher does not look ahead to see whether
later goals will constrain unknowns left underdetermined by an
earlier goal.

Concrete examples encountered:

- `balanced(Total) :- plus(X, Y, Total), times(X, 2, Y).` queried
  with `?- balanced(15).` returns Underdetermined on the first body
  atom `plus(X, Y, 15)` even though pairing with `times(X, 2, Y)`
  would pin X=5, Y=10.
- `balanced2(Total) :- times(X, 2, Y), plus(X, Y, Total).` (same
  body atoms reordered) hits the same boundary on the first atom.
- `same_ratio(A, B, C, D) :- times(A, D, AD), times(B, C, BC),
  AD = BC.` queried with `?- same_ratio(2, 3, 4, ?X).` returns
  Underdetermined on the first body atom.

Workaround: structure rules so each body atom is determinate given
prior bindings. `half_balanced(Total, Half) :- ...` and
`same_ratio_solving_d(A, B, C, D) :- ...` succeed because the rule
head's arguments fix enough variables before the body runs.

The pattern: HLMR M2 handles theories where the rule's variable-flow
structure is determinate-by-construction. Mathematically equivalent
rules can have very different operational behaviour. Documented in
`RENDER_M2_DESIGN.md` §6.3 (the linear_system rephrasing) but worth
registering that the discipline propagates to user-written theories
as well.

M3 implication: across-goal constraint propagation — or minimally,
"join all body atoms into one solver call" — is a natural M3+
capability. The Z3 bridge can already handle conjoined constraints
(it does for the prime_search demo where four atoms are sent
together); the missing piece is the search-side machinery that
decides when to defer dispatch until more constraints accumulate.

### Int-vs-rational behaviour observed directly

Two queries confirmed the boundary:

- `?- times(?X, 4, 12).` returns `?X = 3`, displayed as integer.
- `?- times(?X, 4, 11).` returns `?X = 11/4`, displayed as Fraction.

Same dispatcher, same kernel, different witness type. Z3 returns
rational; the bridge collapses denominator-1 rationals to int per
the Session 5a normalisation (`_z3_val_to_python`). The `Fraction`
case shows as such in proofs.

---

## Definition discipline

### Definitions need to specify the intended domain — for every variable

The `even(5)` example is the canonical case. "N is even iff there
exists K such that 2K = N" is logically consistent but defines
different predicates over ℤ vs ℚ. M2 operates in ℚ, so the
predicate is universally true unless integer-typed witnesses are
explicitly required.

The naive workaround — enumerate integers as facts and constrain
the input — is **not enough**:

    integer(0). integer(1). integer(2). integer(3). integer(4). integer(5).
    even(N) :- integer(N), times(K, 2, N).

`?- even(5).` still succeeds with K = Fraction(5, 2). The reason:
the rule constrains N (the input) to be an enumerated integer, but
not K (the witness). Z3 finds K = 5/2 satisfying times(K, 2, 5)
because nothing required K to be in the integer list.

The correct rule must constrain every variable that should be
integer-typed:

    even(N) :- integer(N), integer(K), times(K, 2, N).

Now SLD forces a pick of integer(K), instantiates K as a specific
integer, and dispatches a fully-ground times atom to Z3 — which
returns unsat for every K in the enumeration when N=5. SLD then
exhausts choices and returns no solution.

The lesson: in an untyped system, every variable that should be
integer-typed must be independently constrained. Missing one
silently re-introduces the rational-witness problem. The system
gives no warning that a meta is free-typed; the user must mentally
track typing themselves.

This makes typed metavariable dispatch the strongest M3 motivation
surfaced during play-around. With typed metas, the predicate
definition could enforce typing structurally — the type signature
carries the constraint, the dispatcher configures Z3 with z3.Int
variables automatically, and there is no way to accidentally let
a rational through.

### Reading rendered rules surfaces typing bugs before queries do

The rendered IR for the refined `even` rule reads:

    (forall N. (forall K. ((integer(N) & times(K, 2, N)) -> even(N))))

K is in the universal quantifier but does not appear in the
conjunction's `integer(...)` clause. Anyone reading this carefully
sees immediately that K is unconstrained — it only appears in the
times relation. The rule, fully unfolded, says: "for every N and K,
if N is in our integer list and K*2 = N, then even(N)." That admits
the rational witness because nothing pins K.

The tutorial §3 teaches readers to walk a Fitch proof line by line
and check each inference. Equally important: read the *rules*
before querying them. The rendered IR makes the typing gaps
visible if you look.

Worth a small tutorial addition: a section on reading rule
statements with attention to which variables are constrained.

### Domains where M2's rational fragment works cleanly

Domains where M2's arithmetic is mathematically correct without
typing workarounds:

- Linear functions and equations
- Ratios, proportions, cross-multiplication (e.g.
  `same_ratio_solving_d`)
- Compositional arithmetic chains (e.g. `quadruple = double ∘ double`)
- Goal-by-goal-determinate constraint chains where each step pins
  down enough to make the next step solvable

Domains that need integer-typed dispatch and currently require
enumeration workarounds:

- Even/odd, parity
- Divisibility predicates expressing "B is an integer multiple of A"
- Prime, composite
- Modular arithmetic
- Combinatorics over finite sets of integers

---

## Bugs found and fixed during play-around

### Z3 bridge divides-by-zero crash (fixed)

Query `?- divides(7, 0, ?Q).` caused a `SolverKernelDisagreement`
crash with a Python exception trace exposed to the user.

Root cause: the Z3 bridge translated `divides(a, b, c)` as
`a/b == c` (rational division). The bridge's design comment claimed
"Z3 will return unsat on divide-by-zero in any model that tries
it." This was empirically false — Z3's theory of rationals defines
`x/0 = 0` as a total function (convention), so Z3 returned sat with
witness `?Q = 0`.

The downstream layers all behaved correctly:
- arithEval correctly rejected `divides(7, 0, 0)` with
  MalformedArithmetic (Python's Fraction raises ZeroDivisionError).
- The dispatcher correctly identified Case 1 disagreement
  (MalformedArithmetic on a non-contested shape).
- The dispatcher correctly crashed with SolverKernelDisagreement
  per its design.

The kernel arbitration prevented an unsound proof. But the
user-visible behaviour was wrong — a query that should return
NoSolution instead crashed with an exception trace.

Fix landed in a focused Sonnet session: bridge translation now
adds an explicit non-zero divisor constraint when translating
`divides(a, b, c)`:

    z3.And(b != 0, a/b == c)

Z3's model space now aligns with arithEval's domain. Any sat
result has non-zero divisor; verify-before-return passes cleanly;
divide-by-zero queries return NoSolution as expected.

5 regression tests added covering ground-zero, meta-zero, all-meta,
happy-path-int, and happy-path-rational divisor cases. 998 tests
passing post-fix (was 993).

This is a meaningful play-around finding. The audit didn't catch
it because the dispatcher tests used mock bridges that returned
scripted results, not real Z3 with its actual divide-by-zero
semantics. The four CLI demos didn't exercise it. Tutorial §6
didn't have a section about it. Discovered by curiosity-driven
exploration ("what happens when the divisor is zero?") — exactly
what hands-on play-around is for.

---

## M3 motivations

Captured from this play-around phase, in priority order:

### 1. Typed metavariable dispatch (highest priority)

The IR has typed metas; the dispatcher doesn't use them. For any
integer-domain predicate to work cleanly, the dispatcher must
propagate type constraints to Z3 (use `z3.Int` for integer-typed
metas, `z3.Real` for rational-typed). Without this, integer-domain
theories require enumeration workarounds that are bounded, tedious,
and error-prone (every variable that should be integer-typed must
be independently constrained — missing one silently re-introduces
rational witnesses).

This is not a small change. The classifier needs to read meta
types, the bridge needs an alternative variable-creation path, the
parser eventually needs syntax for declaring meta types in queries,
and the type system has to be visible at every layer where users
write specifications. But it's the single largest unlock for HLMR's
pedagogical use case.

### 2. Across-goal constraint propagation

When a query body has multiple atoms that together constrain an
unknown that either alone leaves underdetermined, the dispatcher
should be able to defer dispatch until enough constraint accumulates.

Simplest version: collect all arithmetic body atoms into one solver
call and let Z3 / SymPy solve the conjoined system. This is what
the prime_search demo does at the query-tuple level (four atoms
sent together); the missing piece is doing it inside SLD bodies
when the goals are arithmetic.

Three concrete examples encountered: `balanced`, `balanced2`,
`same_ratio` — all hit Underdetermined on the first body atom even
though later atoms would have pinned the unknowns.

### 3. REPL parser extension for symbolic arithmetic syntax

The REPL is currently the bottleneck for hands-on M2 exploration.
Extending the Lark grammar to accept `+ - * / ^ < > <= >= !=` plus
comma-separated multi-goal queries would let users type the queries
the four CLI demos run programmatically.

Independent of M3's theory growth work but pairs naturally with it
(M3's user-facing surface will need richer syntax anyway).

### 4. Pretty-printing of rational constants in proofs

`Fraction(5, 2)` displayed as `5/2` in rendered proofs would
improve readability without changing any underlying logic. Pure
renderer cosmetic change.

### 5. Type-aware specification at theory-seed level (M3-specific)

The `even(5)` saga showed that even with explicit constraints,
typing bugs are easy to write and impossible to detect at
specification time. For M3's theory growth loop, this matters
doubly: if the equivalence-relations seed (or any seed) has the
same class of specification bug, M3's generated theorems can
inherit those bugs and look correct because the kernel verifies
them. M3 should consider type-checking specifications at seed
load time, not just relying on kernel verification of derived
proofs.

---

## Tutorial accuracy

### §6.4 corrected during play-around

The original §6.4 example (`root_of(?X, x^5 - x - 1)`) claimed
SymPy returned ConditionSet. In fact SymPy returns
FiniteSet({CRootOf(...)}) and the bridge rejects on element
inspection because CRootOf isn't an exact rational. Updated to
use `x^2 - 2` as the example with the actual mechanism explained.

### Other sections not yet validated by hands-on use

Tutorial §4 (REPL walkthroughs) and §5 (demo descriptions) match
what the CLI demos produce. Worth running through each interactive
example in §4 during continued exploration to catch any other
"documented vs actual" drift.

---

## Surprises

### The kernel correctly verifying a specification bug

The `even(5)` proof passed kernel verification. The kernel did its
job. The *specification* was wrong, in a subtle way that's easy to
miss, and the system has no way to flag the mistake. This is the
conservative-default principle from a different angle: the kernel
verifies what it is asked to verify; specification bugs live
entirely outside its scope. A typed system would catch this class
of bug at rule-definition time; an untyped system catches it only
by the user inspecting proofs and noticing the rational witness.

### The system silently accepted a wrong fix

A partial workaround for the `even(5)` issue (constraining N but
not K) ran cleanly and produced a "successful" 7-line proof of
`even(5)` with K = 5/2. The proof was internally sound; the rule
was logically consistent over ℚ; only the *intended typing* was
violated. Same lesson as above, sharpened: in untyped systems, you
get exactly what you specify, and what you specify may not be what
you intended.

### The compositional plumbing works end-to-end

Three different compositional theory shapes (`half_balanced`,
`quadruple`, `same_ratio_solving_d`) all produced kernel-verified
proofs. SLD threaded unification through multiple layers cleanly,
the dispatcher fired multiple times with different witnesses, and
the renderer produced coherent multi-step proofs. M2's plumbing
handles compositional theories, not just flat ones. M3's growth
loop builds on this foundation.

### The system's honesty about underdetermined cases is reassuring

Multiple Underdetermined returns during play, each with the witness
the dispatcher found and the unbound metas spelled out. Not crashes,
not silent successes, not curt "no" answers — precise statements
about what was and wasn't determined. The conservative-default
principle in user-visible form, as designed.

### Real bugs surface from genuine curiosity, not from testing

The divides-by-zero bug wasn't found by the audit, by any of the 993
tests, or by the four CLI demos. It surfaced when someone curious
asked "what happens when the divisor is zero?" — an intuitive
question that exercised a code path no test covered. This is what
the play-around phase is for and the strongest argument for taking
it seriously between major milestones.

---

## Successes worth registering

- 998 tests passing post-fix (993 pre-fix + 5 regression tests).
- All four M1 demos still produce kernel-verified proofs.
- All four M2 CLI demos run end-to-end with kernel-verified proofs
  (or honest OutsideFragment for #4).
- Three user-written compositional theories produced kernel-verified
  proofs through the REPL.
- One real bug found and fixed cleanly via the established
  Sonnet-implementation discipline.
- One tutorial accuracy issue found and fixed during play.
- Kernel isolation maintained throughout — no kernel changes during
  play-around or the focused fix.
- The trust boundary held: every observation about M2's behaviour
  could be traced to either a design choice or a documented
  limitation; the kernel never produced a false proof.

This is genuine, paid-for-by-discipline confidence in M2 as a
shipped milestone. The play-around phase validated what the test
suite asserted: M2 works as designed, including its rejections,
including its boundaries.
