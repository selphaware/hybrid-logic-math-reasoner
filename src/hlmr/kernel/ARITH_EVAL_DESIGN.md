# `arithEval` kernel rule — design

**Status:** Design v1.1 (Opus 4.7). Conservative-default revision: 0^0 rejects. No code in this document; pseudocode only.
**Implements:** `prd_milestone_2.md` §6.4 (Task A in §13.2).
**Target reader:** Sonnet 4.6 implementing against this spec, in `src/hlmr/kernel/rules.py` and `src/hlmr/kernel/errors.py`.
**Companion designs:** `src/hlmr/dispatch/DISPATCH_DESIGN.md` (Task B), `src/hlmr/solve/RENDER_M2_DESIGN.md` (Task C). Both consume `arithEval`'s contract; neither has been written yet.

---

## 1. Purpose

`arithEval` is the only kernel change permitted in M2. It is a 23rd ND
rule that closes the gap between SLD/dispatcher-found witnesses (numbers
that satisfy linear-arithmetic, finite-domain, or polynomial constraints)
and the kernel's existing rule alphabet, which has no notion of
"5 > 2 is true."

**Headline observation.** Every M2 demo's arithmetic content is a
ground numeric atom — every number is an `int` or `Fraction` literal,
every operator is one of `+ - * / ^`, every comparison is one of
`< <= > >= !=` (or the predicate forms `plus minus times divides`, or
the `Equals` IR node between two arithmetic terms). The atoms are
self-evidently true or false by recursive evaluation in Python's exact
arithmetic. `arithEval` is the rule that performs that evaluation and
accepts iff the atom evaluates to true.

**The rule has no premises.** It is the arithmetic analogue of `eqRefl`:
zero line refs, zero box refs, no `extra` payload. Truth is read off
the line's formula in isolation. This keeps the trust surface tiny —
the rule's correctness reduces to "the evaluator is sound."

**Out of scope.** Non-ground arithmetic (anything containing `Var` or
`Meta`); transcendentals; reals beyond exact rationals; algorithms over
non-arithmetic predicates. These all reject as `MalformedArithmetic`.

---

## 2. How `arithEval` fits in `check_proof`

The existing pipeline in `src/hlmr/kernel/check.py:check_proof` runs
five phases:

1. Empty-proof check.
2. **§5.3 `UnresolvedMeta` check** — walks every line's formula; if any
   `Meta` is present, returns `UnresolvedMeta` immediately.
3. Structural sanity (line numbers, box depths, premise/assumption
   placement).
4. Per-line rule dispatch via `RULES.get(app.rule)`.
5. Final-depth-zero and goal-match checks.

`arithEval` slots into phase 4 as a new `RULES["arithEval"]` entry. It
is reached **only after** the §5.3 `Meta` walk has rejected any
formula containing a `Meta`. So `arithEval`'s own evaluator can assume
no `Meta` is present in the input — but the soundness argument does
not rely on that, and the evaluator independently rejects `Meta`
(returns "non-evaluable") as defence in depth (§9.5).

The structural pass (phase 3) already enforces that `arithEval` lines
are at depth 0 (any rule application at depth > 0 must be inside a box,
which works fine for `arithEval` too — boxes are not forbidden, they
just are not required and M2's renderer will not produce them).

---

## 3. Rule semantics

### 3.1 The contract

`arithEval` accepts exactly when the line's formula is a **ground,
syntactically-arithmetic atom that evaluates to True under exact integer
and rational arithmetic.**

Concretely, the rule checker `_arithEval(line, proof)` returns:

- `None` (success) iff `line.formula` is in the evaluable-atom set
  (§5) and the recursive evaluator (§6) returns the boolean `True` for
  it.
- `EvaluationFalse(line.number, line.formula)` iff the formula is in
  the evaluable-atom set and the evaluator returns `False`.
- `MalformedArithmetic(line.number, line.formula, reason)` for every
  other case — non-evaluable formula shape, non-numeric `Const`, `Var`
  in arithmetic position, division by zero, ill-typed exponent, wrong
  arity, etc. The `reason` string is a debugging aid; tests assert the
  error class, not the reason.
- `WrongRefCount("arithEval", 0, n_lines, 0, n_boxes)` iff
  `app.line_refs` or `app.box_refs` is non-empty. The rule takes no
  references.

The conclusion of the rule **is** the line's formula; there is no
"input formula plus a derived conclusion" relationship. This matches
`eqRefl`, which also reads truth off the formula alone.

### 3.2 Why this is sound

The set of evaluable atoms (§5) is restricted to syntactic shapes whose
truth in the standard model of arithmetic over ℤ and ℚ is **decidable
by recursive evaluation in Python's exact arithmetic** (`int` plus
`fractions.Fraction`). Python's `int` is unbounded-precision; `Fraction`
is exact rational. Evaluation is therefore not an approximation — it
returns the actual mathematical truth value. Full argument in §9.

### 3.3 What is NOT a contract

- **Completeness over arithmetic.** `arithEval` does not claim to
  prove every true arithmetic statement. It proves only ground
  evaluable instances. `forall x. x = x` is not within its scope; that
  is a job for `forallI` + `eqRefl`. `(forall x. x + 0 = x)` likewise.
- **A theory of arithmetic.** The KB may contain Horn clauses about
  arithmetic (e.g. Peano `even/1`); those resolve via SLD as in M1.
  `arithEval` does not interact with KB clauses except by being one
  more rule the renderer can emit.
- **Quantifier elimination.** `arithEval` rejects any non-ground
  atom (anything containing `Var` or `Meta`), with no attempt at
  quantifier elimination.
- **Hidden simplification.** The rule does not normalise `Equals(2+3, 7)`
  to `Equals(5, 7)`; it just evaluates both sides. The renderer is free
  to emit the simplified form `Equals(Const(5), Const(7))` if it wants
  — that is also evaluable. Both shapes are accepted.

---

## 4. RuleApp shape

```text
RuleApp(
    rule="arithEval",
    line_refs=(),       # MUST be empty
    box_refs=(),        # MUST be empty
    extra={},           # MUST be empty (no payload required or read)
)
```

Pattern: same as `eqRefl`.

The implementer should call `_check_refs(line, proof, expected_lines=0,
expected_boxes=0)` first thing. The existing `WrongRefCount` error
already covers the zero-refs violation.

The rule does **not** call `_require_extra` because `extra` is empty.
A non-empty `extra` is permissible (the kernel ignores it), but the
renderer in M2 will produce empty `extra` for `arithEval` lines.

---

## 5. The set of evaluable atoms

A formula `f` is **evaluable** iff it matches one of these patterns
**and** every term position in it is an evaluable term (§6).

### 5.1 Comparison atoms (binary)

| Predicate | Semantics under evaluation |
|---|---|
| `Atom("<",  (a, b))`  | `eval(a) < eval(b)`  |
| `Atom("<=", (a, b))` | `eval(a) <= eval(b)` |
| `Atom(">",  (a, b))`  | `eval(a) > eval(b)`  |
| `Atom(">=", (a, b))` | `eval(a) >= eval(b)` |
| `Atom("!=", (a, b))` | `eval(a) != eval(b)` |

Arity must be exactly 2. Arity 1, 3, or 0 → `MalformedArithmetic`.

### 5.2 Predicate-form ternary atoms

| Predicate | Semantics under evaluation |
|---|---|
| `Atom("plus",    (a, b, c))` | `eval(a) + eval(b) == eval(c)` |
| `Atom("minus",   (a, b, c))` | `eval(a) - eval(b) == eval(c)` |
| `Atom("times",   (a, b, c))` | `eval(a) * eval(b) == eval(c)` |
| `Atom("divides", (a, b, c))` | `eval(b) != 0 and Fraction(eval(a))/Fraction(eval(b)) == eval(c)` |

Arity must be exactly 3. Other arities → `MalformedArithmetic`.

> **Naming note for parser/dispatcher.** The `divides` predicate name
> here means "quotient": `divides(a, b, c) ⟺ a / b = c`. This conflicts
> with the conventional number-theoretic meaning of "divides"
> (`a | b ⟺ ∃k. a*k = b`). `prd_milestone_2.md` §6.2 fixes the
> quotient meaning, and `arithEval` implements that. If a future
> milestone wants the divisibility predicate, it must use a different
> name (e.g. `divisible_by`) — this is a parser/dispatcher concern, not
> an `arithEval` concern, and the rule is agnostic.

### 5.3 Equality atoms (`Equals` IR node)

| Form | Semantics under evaluation |
|---|---|
| `Equals(lhs, rhs)` | `eval(lhs) == eval(rhs)` |

Both `lhs` and `rhs` must be evaluable terms (§6). The IR's `Equals`
is a distinct formula kind from `Atom`; the rule pattern-matches on
both.

> **Overlap with `eqRefl`.** Reflexive cases like `Equals(Const(7),
> Const(7))` are accepted by both rules (`eqRefl` requires syntactic
> identity; `arithEval` evaluates and finds 7 = 7). Both are sound.
> The renderer chooses one — likely `eqRefl` for syntactically
> reflexive cases, `arithEval` only when the two sides are
> syntactically distinct (e.g. `Equals(Func("+", (Const(3), Const(4))),
> Const(7))`).

### 5.4 Anything else rejects

Any other top-level formula shape (`And`, `Or`, `Not`, `Implies`,
`Iff`, `ForAll`, `Exists`, `Bot`, an `Atom` with an unrecognised
predicate name, an `Atom` with an arithmetic predicate name but wrong
arity, an `Atom` with `args` containing a non-evaluable term, an
`Equals` with a non-evaluable side) → `MalformedArithmetic`.

In particular, an `Atom` like `Atom("ancestor", (Const(2), Const(3)))`
— a regular Horn-clause predicate that happens to contain numeric args
— rejects with `MalformedArithmetic`. `arithEval` is not a generic
"this line is true" rule.

---

## 6. The set of evaluable terms

A term `t` evaluates to a numeric value (an `int` or `Fraction`) iff
it matches one of these recursive cases. Every other term is
**non-evaluable** and contributes to a `MalformedArithmetic` rejection
when it appears in an evaluable atom's term position.

| Term shape | Evaluation |
|---|---|
| `Const(value=v)` where `v` is `int` and not `bool`             | `v` |
| `Const(value=v)` where `v` is `Fraction`                       | `v` |
| `Func("+", (a, b))`                                            | `eval(a) + eval(b)` |
| `Func("-", (a, b))`                                            | `eval(a) - eval(b)` |
| `Func("-", (a,))` (unary negation, arity 1)                    | `-eval(a)` |
| `Func("*", (a, b))`                                            | `eval(a) * eval(b)` |
| `Func("/", (a, b))`, with `eval(b) != 0`                       | `Fraction(eval(a)) / Fraction(eval(b))` |
| `Func("^", (a, b))`, `eval(b)` is `int` (not `bool`), and not (`eval(a)` is 0 and `eval(b) < 0`) | see §6.1 |

Anything else — `Var`, `Meta`, `Const(str)`, `Const(bool)`,
`Const(float)`, `Const` of any other type, `Func` with a non-arithmetic
name, arithmetic `Func` with the wrong arity, arithmetic `Func` whose
recursive subterm is non-evaluable, division by zero, `0^negative`,
non-integer exponent — is **non-evaluable**.

The rule expresses "non-evaluable" by returning a sentinel from the
internal evaluator (e.g. `None`); the outer `_arithEval` checker
translates that into `MalformedArithmetic`.

### 6.1 The exponent operator `^`

The exponent `b` must evaluate to an `int` (and not `bool`). The base
`a` may evaluate to `int` or `Fraction`. The result type follows:

- `int ** non_negative_int` → `int`  (Python builtin, exact)
- `Fraction ** int` (any sign) → `Fraction`  (Python `Fraction.__pow__`, exact)
- `int ** negative_int` — Python's `int.__pow__` returns `float` here,
  which is a soundness disaster (`2 ** -1 == 0.5`, a float). The
  evaluator must coerce the base to `Fraction` first when `b < 0`:
  `Fraction(eval(a)) ** eval(b)`. Result is `Fraction`.

Edge cases:

- `0 ** 0` — **rejected**. Python returns `1` here, but the value of
  `0^0` is genuinely contested: defined as 1 in combinatorics, discrete
  mathematics, and polynomial rings; undefined in real analysis (the
  limit of `x^y` as both vary doesn't exist). Mathematicians disagree.
  The conservative-default principle from `prd.md` §4 and
  `prd_milestone_2.md` §4 ("classification is conservative — anything
  ambiguous is rejected rather than guessed") applies at the kernel
  level: silently inheriting Python's `1` would commit the kernel to
  one side of a contested convention. `_eval_term` returns `None` for
  `0 ** 0`, causing `MalformedArithmetic`. See §13 (non-goals) for
  guidance on naming a future operator that fixes a convention
  explicitly.
- `0 ** negative_int` — undefined (1/0 in disguise). The evaluator
  returns non-evaluable → `MalformedArithmetic`.
- Non-integer exponent (e.g. `^` with a `Fraction` exponent) — rejects
  even if the exponent is rational with denominator 1
  (`Fraction(2, 1)`). The rule accepts only `int`-typed exponents,
  full stop. Rationale: keeps the soundness story simple — no
  "convert Fraction(2,1) to int 2" round-tripping.

### 6.2 Why no `bool`

Python's `bool` is a subclass of `int`. Without an explicit guard,
`Const(True)` would evaluate as 1 and silently pass arithmetic
comparisons. `Const.__post_init__` rejects `bool` at construction
(per `prd_milestone_2.md` §6.3), but the evaluator independently
rejects `Const(value=v)` when `isinstance(v, bool)` is true. Defence
in depth.

---

## 7. The evaluation algorithm

Pseudocode. Sonnet implements directly, in `src/hlmr/kernel/rules.py`,
as private helpers `_eval_term` and `_eval_atom` plus the public
checker `_arithEval`. No new file.

```
def _eval_term(t: Term) -> int | Fraction | None:
    """Return the numeric value of t, or None if t is non-evaluable."""

    match t:
        case Const(value=v):
            if isinstance(v, bool):           # bool is int subclass — reject
                return None
            if isinstance(v, float):          # defence-in-depth (§6.3 also blocks)
                return None
            if isinstance(v, int):
                return v
            if isinstance(v, Fraction):
                return v
            return None                       # str, anything else

        case Func(name="+", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None: return None
            return va + vb

        case Func(name="-", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None: return None
            return va - vb

        case Func(name="-", args=(a,)):       # unary negation (arity 1)
            va = _eval_term(a)
            if va is None: return None
            return -va

        case Func(name="*", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None: return None
            return va * vb

        case Func(name="/", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None: return None
            if vb == 0: return None           # division by zero
            return Fraction(va) / Fraction(vb)

        case Func(name="^", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            if va is None or vb is None: return None
            if isinstance(vb, bool) or not isinstance(vb, int):
                return None                   # exponent must be int (not bool)
            if va == 0 and vb <= 0:
                return None                   # 0^0 contested; 0^negative undefined
            if vb < 0:
                return Fraction(va) ** vb     # forces Fraction result
            return va ** vb                   # int^int -> int; Fraction^int -> Fraction

        case _:                               # Var, Meta, unknown Func, wrong arity
            return None
```

```
def _eval_atom(f: Atom | Equals) -> bool | None:
    """Return the boolean value of a ground arithmetic atom, or None
    if non-evaluable."""

    match f:
        case Atom(pred="<",  args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va < vb)
        case Atom(pred="<=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va <= vb)
        case Atom(pred=">",  args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va > vb)
        case Atom(pred=">=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va >= vb)
        case Atom(pred="!=", args=(a, b)):
            va, vb = _eval_term(a), _eval_term(b)
            return None if (va is None or vb is None) else (va != vb)

        case Atom(pred="plus", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None: return None
            return va + vb == vc
        case Atom(pred="minus", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None: return None
            return va - vb == vc
        case Atom(pred="times", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None: return None
            return va * vb == vc
        case Atom(pred="divides", args=(a, b, c)):
            va, vb, vc = _eval_term(a), _eval_term(b), _eval_term(c)
            if va is None or vb is None or vc is None: return None
            if vb == 0: return None
            return Fraction(va) / Fraction(vb) == vc

        case Equals(lhs=lhs, rhs=rhs):
            vl, vr = _eval_term(lhs), _eval_term(rhs)
            if vl is None or vr is None: return None
            return vl == vr

        case _:
            return None     # unknown Atom predicate, non-Atom/non-Equals shape,
                            # wrong arity for an arithmetic predicate, etc.
```

```
def _arithEval(line: ProofLine, proof: Proof) -> RuleError | None:
    if err := _check_refs(line, proof, expected_lines=0, expected_boxes=0):
        return err
    f = line.formula
    if not isinstance(f, (Atom, Equals)):
        return MalformedArithmetic(
            line.number, f, "arithEval requires Atom or Equals, got " + type(f).__name__,
        )
    result = _eval_atom(f)
    if result is None:
        return MalformedArithmetic(line.number, f, "non-evaluable arithmetic atom")
    if result is False:
        return EvaluationFalse(line.number, f)
    return None  # result is True — accept
```

### 7.1 Why a sentinel-`None` design rather than exceptions

The existing rule-checker contract is `RuleError | None` — `None` for
success, error otherwise. The internal evaluator returns
`int | Fraction | None` (terms) or `bool | None` (atoms), where `None`
means "syntactically not evaluable." Translating the inner `None` into
`MalformedArithmetic` happens at exactly one point (the outer
checker). This avoids exception-driven control flow and matches the
style of the other 22 rules.

### 7.2 Termination

Each recursive call descends one node of a finite IR term/formula tree.
Termination is structural; no fixpoint, no work-list. Worst-case time
is linear in the size of the formula. Worst-case Python integer
arithmetic time is bounded by the bit-length of the largest
intermediate value, which can in principle be exponential in the
formula size for nested exponents — but this is bounded by the
formula's syntactic size, not by an unbounded loop.

---

## 8. API surface

### 8.1 Module layout

- `src/hlmr/kernel/rules.py` — gains `_eval_term`, `_eval_atom`,
  `_arithEval`, plus a new entry in the module-level `RULES` dict:
  `"arithEval": _arithEval`. No new file in `kernel/`. The 22 existing
  rule checkers are unchanged.
- `src/hlmr/kernel/errors.py` — gains two error dataclasses (§9.1).
  Existing error types unchanged.
- `src/hlmr/kernel/check.py` — **unchanged**. The §5.3 `Meta` walk
  already runs before per-line dispatch; the structural pass already
  permits zero-ref/zero-box rule applications.

### 8.2 Imports

Inside `rules.py`, add:

```python
from fractions import Fraction
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
```

`Meta` is imported only so the evaluator can pattern-match it as
"non-evaluable." The kernel already references the IR types it needs;
adding `Const` and `Func` for evaluation is a natural extension.

`from fractions import Fraction` is the only new stdlib import. No
third-party dependencies. `kernel/` still imports only stdlib and
`hlmr.ir.*`. `test_kernel_isolation.py` continues to pass.

### 8.3 What the rest of the codebase calls

Nothing outside the kernel imports `_eval_term` or `_eval_atom`. They
are private helpers. The dispatcher (`dispatch/`) and the renderer
(`solve/render.py`) interact with `arithEval` only through the
kernel's public `check_proof` interface — they emit a `ProofLine` with
`justification = RuleApp("arithEval", (), (), {})` and trust the
kernel to verify it.

> **Coordination note for the dispatcher.** `dispatch/` may want to
> "pre-verify" a witness internally before handing it to the renderer
> — e.g. take Z3's `?P = 5` and check `arithEval` accepts every
> resulting ground atom. The dispatcher does this by constructing a
> trivial one-line `Proof` and calling `check_proof` on it. The
> dispatcher does **not** import the private `_eval_term` /
> `_eval_atom` helpers; the boundary stays clean. This is the
> "verify before return" step listed in `prd_milestone_2.md` §15
> (witness verification round-trip risk).

### 8.4 Why no `extra` payload

For every other rule, `extra` carries information the rule needs that
isn't on the conclusion line: an eigenvariable for `forallI`, an
instantiation term for `forallE`, a substitution template for
`eqSubst`. `arithEval`'s conclusion is its own input — the formula
itself fully determines truth. Nothing else is needed. Adding an
unused `extra` field would invite implementation drift (someone might
later read it and base behaviour on it, which would be wrong). Keep
it empty.

The implementer should **not** call `_require_extra`. The renderer
emits `extra={}` for all `arithEval` lines. If `extra` is non-empty,
the kernel ignores it.

---

## 9. Soundness argument

**Claim.** If `_arithEval(line, proof)` returns `None` for a line
`L`, then the formula `L.formula` is true in the standard model of
arithmetic over ℤ and ℚ extended with the operators `+ - * / ^_int`
and the relations `= < <= > >= !=`.

**Proof structure.** `_arithEval` returns `None` only when
`_eval_atom(L.formula)` returns the boolean `True`. So the claim
reduces to:

**Lemma.** If `_eval_atom(f)` returns `True`, then `f` is true.
**Lemma.** If `_eval_term(t)` returns `v ∈ ℤ ∪ ℚ`, then `v` is the
intended-mathematical value of the term `t` under the standard
interpretation.

Both lemmas hold by structural induction on the term/formula. The
inductive cases reduce to claims about Python's arithmetic
implementations.

### 9.1 Python `int` is exact

Python's built-in `int` type is **arbitrary-precision**: there is no
overflow. `+ - *` on `int` are exact for any operands the system
memory can store. Comparisons (`< <= > >= == !=`) likewise.

This is unlike C-style fixed-width integers; HLMR cannot suffer
silent overflow under `_eval_term` because the underlying
implementation does not silently overflow.

### 9.2 Python `Fraction` is exact

`fractions.Fraction(num, den)` stores `num` and `den` as Python
`int`s in lowest terms (the constructor calls `gcd` and normalises
sign). Arithmetic operations return new `Fraction` instances in
lowest terms. Equality `==` compares numerator and denominator after
normalisation. Comparisons are based on cross-multiplication of
unbounded `int`s.

Therefore `Fraction` arithmetic is exact rational arithmetic. No
rounding, no precision loss, no NaN, no infinity.

### 9.3 Mixed `int` / `Fraction` arithmetic

`Fraction.__add__(int)` (and the reverse via `__radd__`) coerces the
`int` operand to `Fraction(int_value, 1)` and proceeds. Same for
`-`, `*`, `/`. Result is always `Fraction`. Equality `Fraction(2,1)
== int(2)` is `True` in Python (this is `Fraction.__eq__`'s
contract).

The evaluator's mixed-type behaviour:

- `Func("+", (Const(2), Const(Fraction(3, 2))))` evaluates to
  `2 + Fraction(3, 2)` = `Fraction(7, 2)`. Exact.
- `Equals(Const(2), Const(Fraction(2, 1)))` evaluates `2 ==
  Fraction(2, 1)` = `True`. Correct.
- `Atom(">", (Const(Fraction(3, 2)), Const(1)))` evaluates `Fraction(3, 2)
  > 1` = `True`. Correct.

### 9.4 Division `/`

`_eval_term` for `Func("/", (a, b))` rejects `vb == 0` (returns
`None`) and otherwise computes `Fraction(va) / Fraction(vb)`. The
explicit coercion to `Fraction` is **necessary**: without it,
`int / int` in Python returns `float` (e.g. `1 / 2 == 0.5`, a
float). Floats are unsound for proof checking (rounding error). The
coercion ensures `int / int` produces a `Fraction` result (e.g.
`Fraction(1, 2)`), exact.

The same coercion applies in the `divides` predicate evaluation.

### 9.5 Power `^`

§6.1 covers the cases:

- Non-integer exponent → reject.
- `int ** non_negative_int`: Python returns `int`, exact.
- `Fraction ** int` (any sign): Python's `Fraction.__pow__` returns
  `Fraction`, exact.
- `int ** negative_int`: Python's built-in returns `float` —
  unsound. The evaluator coerces to `Fraction(va) ** vb`, returning
  `Fraction`. Exact.
- `0 ** negative_int`: undefined. Reject.
- `0 ** 0`: **reject**. Python returns `1`, but the mathematical value
  of `0^0` is contested between conventions (combinatorics: 1; real
  analysis: undefined). Accepting either value would require the
  kernel to assert a contested mathematical statement, which is
  incompatible with the soundness-over-completeness commitment and
  with the conservative-default principle in `prd.md` §4 and
  `prd_milestone_2.md` §4. The evaluator returns non-evaluable; the
  rule rejects with `MalformedArithmetic`. A future milestone that
  needs `0^0 = 1` (e.g. polynomial rings, generating functions) must
  introduce an explicit convention-naming operator (see §13).

### 9.6 What if a `float` somehow appears

`Const.__post_init__` (`prd_milestone_2.md` §6.3) rejects `float`
values at construction time. But the soundness of `arithEval` does
not rely on `__post_init__`. The evaluator independently checks
`isinstance(v, float)` and returns `None` (non-evaluable), causing
`MalformedArithmetic`. So even if a future bug or a third-party
construction path bypassed `__post_init__`, no proof line containing
a float-valued `Const` could be accepted by `arithEval`. The kernel
remains sound.

This is an explicit defence-in-depth choice. The kernel does not
trust the IR's construction guards; it re-verifies on use.

### 9.7 What if a `bool` somehow appears

Python's `bool` is an `int` subclass: `isinstance(True, int)` is
`True`. Without an explicit `isinstance(v, bool)` guard, the
evaluator would see `Const(True)` and treat it as `Const(1)` —
silently accepting `Atom(">", (Const(True), Const(0)))` as "true."
This is not a soundness violation (`True > 0` does evaluate to
`True` in Python), but it conflates the boolean and integer domains
and is a category error.

The evaluator rejects `Const(value=v)` when `isinstance(v, bool)`,
returning `None`. Defence in depth, paralleling §9.6.

### 9.8 What if a `Meta` somehow appears

Phase 2 of `check_proof` (§5.3) walks every line's formula and
returns `UnresolvedMeta` if any `Meta` term is present. So
`_arithEval` runs only on `Meta`-free formulas. But: defence in
depth — `_eval_term`'s `case _` catches `Meta` (it doesn't match any
arithmetic pattern), returns `None`, and the outer rule returns
`MalformedArithmetic`. So even if a future kernel-internal change
broke the §5.3 ordering, `arithEval` would still refuse to accept
non-ground atoms.

This means **`arithEval`'s soundness does not depend on §5.3.**
Independent of every other invariant in the kernel, `arithEval`
accepts only ground evaluable atoms.

### 9.9 What if a `Var` appears

Same as `Meta`: `_eval_term`'s `case _` catches it; the rule rejects.

### 9.10 What about negative-zero rationals, NaN, infinity

Not possible. `Fraction` does not have negative zero (`Fraction(-0,
1) == Fraction(0, 1)`), NaN, or infinity. `int` does not either.
The only way to get those values is to inject a `float`, which
the evaluator rejects (§9.6).

### 9.11 What if Python's stdlib `int` or `Fraction` had a soundness bug

The kernel inherits the soundness of CPython's arithmetic. CPython's
unbounded-integer and `Fraction` implementations are extremely
well-tested; a soundness bug in them is below the noise floor of
this design. If one were ever found, every Python-implemented
theorem prover would be affected and the fix would propagate from
upstream.

This is the same trust assumption the kernel already makes — Python
itself is part of the trusted base — and `arithEval` does not extend
it.

---

## 10. Failure modes

Two new error types in `src/hlmr/kernel/errors.py`. Both are frozen
dataclasses, follow the existing error-shape conventions
(`@dataclass(frozen=True)`, subclass of `RuleError`).

### 10.1 `MalformedArithmetic`

```python
@dataclass(frozen=True)
class MalformedArithmetic(RuleError):
    line: int
    formula: Formula
    reason: str
```

Returned when the formula is not in the evaluable set (§5) — wrong
predicate, wrong arity, non-arithmetic `Func` in a term position,
non-numeric `Const`, `Var`/`Meta` present, `bool` value, `float`
value, division by zero, ill-typed exponent, etc.

`reason` is a debugging aid, free-form, not part of the test
contract. Tests assert `isinstance(err, MalformedArithmetic)`.
`reason` may be inspected for human debugging but does not appear
in test assertions.

### 10.2 `EvaluationFalse`

```python
@dataclass(frozen=True)
class EvaluationFalse(RuleError):
    line: int
    formula: Formula
```

Returned when the formula is in the evaluable set, evaluation
succeeds, but the boolean result is `False`. Examples: `Atom(">",
(Const(2), Const(5)))`, `Equals(Const(2), Const(3))`, `Atom("plus",
(Const(2), Const(3), Const(7)))`.

This is **distinct from `MalformedArithmetic`**: `EvaluationFalse`
means "the rule could check this, and the answer is False." The
caller can reason about that — e.g. a malicious renderer that emits
`Atom(">", (Const(2), Const(5)))` as an `arithEval` line is caught
specifically by `EvaluationFalse`, not `MalformedArithmetic`.

The two error classes are also exported from `errors.py` so tests
and other kernel-adjacent code can import them.

### 10.3 `WrongRefCount` (existing error type, reused)

`_arithEval` calls `_check_refs(line, proof, 0, 0)` first. If
`app.line_refs` or `app.box_refs` is non-empty, the existing
`WrongRefCount("arithEval", 0, n_lines, 0, n_boxes)` error is
returned. No new error type for this case.

---

## 11. Worked examples

The following enumerate accept and reject cases. Each is a concrete
`ProofLine` whose `justification` is `RuleApp("arithEval", (), (),
{})` — only the `formula` varies. The "Result" column is what
`_arithEval` returns.

### 11.1 Accept cases

| # | Formula | Result | Reasoning |
|---|---|---|---|
| A1 | `Atom(">", (Const(5), Const(2)))` | `None` | `5 > 2` is `True`. |
| A2 | `Atom("<=", (Const(3), Const(3)))` | `None` | `3 <= 3` is `True`. |
| A3 | `Atom("!=", (Const(7), Const(4)))` | `None` | `7 != 4` is `True`. |
| A4 | `Equals(Func("+", (Const(3), Const(4))), Const(7))` | `None` | `3 + 4 == 7`. |
| A5 | `Equals(Const(7), Func("+", (Const(3), Const(4))))` | `None` | Symmetry; `7 == 7`. |
| A6 | `Atom("plus", (Const(2), Const(3), Const(5)))` | `None` | Predicate form; `2 + 3 == 5`. |
| A7 | `Atom("times", (Const(6), Const(7), Const(42)))` | `None` | `6 * 7 == 42`. |
| A8 | `Atom("minus", (Const(10), Const(3), Const(7)))` | `None` | `10 - 3 == 7`. |
| A9 | `Atom("divides", (Const(1), Const(2), Const(Fraction(1, 2))))` | `None` | `1/2 == 1/2`. |
| A10 | `Equals(Const(Fraction(2, 4)), Const(Fraction(1, 2)))` | `None` | Fractions normalise; `1/2 == 1/2`. |
| A11 | `Atom("<", (Const(2 ** 100), Const(2 ** 100 + 1)))` | `None` | Big integers; Python `int` exact. |
| A12 | `Equals(Func("^", (Const(2), Const(10))), Const(1024))` | `None` | `2 ** 10 == 1024`. |
| A13 | `Equals(Func("^", (Const(2), Const(-1))), Const(Fraction(1, 2)))` | `None` | `Fraction(2) ** -1 == 1/2`. |
| A14 | `Equals(Func("-", (Const(5),)), Const(-5))` | `None` | Unary negation; `-5 == -5`. |
| A15 | `Equals(Const(Fraction(7, 2)), Func("/", (Const(7), Const(2))))` | `None` | Mixed Const/operator equality; `7/2 == 7/2`. |

### 11.2 Reject cases — `EvaluationFalse`

The formula is well-formed and ground, but the result is `False`.

| # | Formula | Result | Reasoning |
|---|---|---|---|
| F1 | `Atom(">", (Const(2), Const(5)))` | `EvaluationFalse` | `2 > 5` is `False`. |
| F2 | `Equals(Const(2), Const(3))` | `EvaluationFalse` | `2 == 3` is `False`. |
| F3 | `Atom("plus", (Const(2), Const(3), Const(7)))` | `EvaluationFalse` | `2 + 3 != 7`. |
| F4 | `Equals(Func("-", (Const(5),)), Const(5))` | `EvaluationFalse` | `-5 == 5` is `False`. |
| F5 | `Atom("!=", (Const(7), Const(7)))` | `EvaluationFalse` | `7 != 7` is `False`. |

### 11.3 Reject cases — `MalformedArithmetic`

The formula is not in the evaluable set.

| # | Formula | Result | Reasoning |
|---|---|---|---|
| M1 | `Atom(">", (Var("X"), Const(2)))` | `MalformedArithmetic` | `Var` non-evaluable. |
| M2 | `Atom(">", (Meta("?X"), Const(2)))` | (`UnresolvedMeta` from §5.3, BEFORE arithEval runs) | §5.3 catches Meta first. If §5.3 ordering changes, defence-in-depth in `_eval_term` returns `None` → `MalformedArithmetic`. |
| M3 | `Atom("foo", (Const(2), Const(3)))` | `MalformedArithmetic` | Unknown predicate. |
| M4 | `Atom("plus", (Const(2), Const(3)))` | `MalformedArithmetic` | Wrong arity for `plus` (need 3). |
| M5 | `Atom(">", (Const(2),))` | `MalformedArithmetic` | Wrong arity for `>` (need 2). |
| M6 | `Equals(Const("alice"), Const(2))` | `MalformedArithmetic` | `Const(str)` non-evaluable. |
| M7 | `Equals(Func("/", (Const(1), Const(0))), Const(0))` | `MalformedArithmetic` | Division by zero in subterm. |
| M8 | `Equals(Func("^", (Const(2), Const(Fraction(1, 2)))), ...)` | `MalformedArithmetic` | Non-int exponent (rational). |
| M9 | `Equals(Func("^", (Const(0), Const(-1))), ...)` | `MalformedArithmetic` | `0 ** -1` undefined. |
| M10 | `Atom("plus", (Const(True), Const(0), Const(1)))` | `MalformedArithmetic` | `bool` rejected even though `bool` is `int` subclass. |
| M11 | `Atom(">", (Const(2.5), Const(1)))` (constructed via a path bypassing `Const.__post_init__`) | `MalformedArithmetic` | `float` rejected by evaluator. |
| M12 | `And(Atom(">", (Const(5), Const(2))), Atom("<", (Const(1), Const(2))))` | `MalformedArithmetic` | Top-level shape `And`, not `Atom` or `Equals`. |
| M13 | `ForAll("x", Atom(">", (Var("x"), Const(0))))` | `MalformedArithmetic` | Top-level `ForAll`. (Quantified arithmetic uses `forallI`/`forallE` over `arithEval` body lines, not `arithEval` directly.) |
| M14 | `Equals(Func("^", (Const(0), Const(0))), Const(1))` | `MalformedArithmetic` | `0^0` contested between mathematical conventions (combinatorics vs real analysis); kernel rejects on conservative-default grounds. Mirrors M9. |

### 11.4 Reject cases — `WrongRefCount`

`_check_refs(line, proof, 0, 0)` rejects before `_eval_atom` is called.

| # | RuleApp shape | Result |
|---|---|---|
| R1 | `RuleApp("arithEval", (3,), (), {})` | `WrongRefCount("arithEval", 0, 1, 0, 0)` |
| R2 | `RuleApp("arithEval", (), ((1, 4),), {})` | `WrongRefCount("arithEval", 0, 0, 0, 1)` |

---

## 12. Coordination notes for downstream design

### 12.1 For the dispatcher (`dispatch/DISPATCH_DESIGN.md`, Task B)

- The dispatcher classifies a goal as "arithmetic-routable" iff the
  goal's predicate name is in §5.1 ∪ §5.2, or the goal is an `Equals`
  whose sides contain only operators from §6 and `Const(int|Fraction)`
  / `Var` / `Meta` leaves. If a `Var` or `Meta` is present, the
  dispatcher's job is to bind it to a numeric witness (via Z3 or
  SymPy) and produce a ground residual that `arithEval` accepts.
- After binding, the dispatcher SHOULD verify each ground arithmetic
  atom by constructing a one-line `Proof` with that atom as the
  formula and `arithEval` as the justification, and calling
  `check_proof`. If verification fails, the dispatcher has produced a
  bad witness — this is a development-time crash, not a production
  silent failure (per `prd_milestone_2.md` §4 architectural commitment
  "Solver disagreement with the kernel").
- The dispatcher does NOT import `_eval_term` or `_eval_atom`. It
  goes through `check_proof`.

> **Witness-verification failure: two distinct cases.** As of v1.1,
> `arithEval` rejects some ground atoms whose syntactic shape is
> nominally evaluable but whose mathematical value is contested
> (currently just `0^0`; future revisions may add others). This
> creates two distinct failure modes during the dispatcher's
> verify-before-return step that `DISPATCH_DESIGN.md` (Task B) must
> distinguish:
>
> 1. **Solver/kernel disagreement (development-time crash).** The
>    dispatcher's solver claims a witness satisfies a constraint that
>    is fully within `arithEval`'s evaluable set, but `arithEval`
>    rejects it. Example: a Z3 model claims `?P = 5` satisfies `?P > 2`,
>    but `arithEval` returns `EvaluationFalse` on `Atom(">", (Const(5),
>    Const(2)))`. This is a true solver/kernel disagreement and indicates
>    a bug in either the solver bridge, the witness extraction, or the
>    kernel — it must crash loudly during development per
>    `prd_milestone_2.md` §4 ("disagreements crash during development,
>    not in production"). The crash signal is `EvaluationFalse` on a
>    fully-evaluable atom, OR `MalformedArithmetic` on an atom whose
>    syntactic shape lies wholly within `arithEval`'s evaluable set.
> 2. **Sound rejection on a contested edge case (treat as
>    `OutsideFragment`).** The dispatcher's solver claims a witness
>    that produces an atom on a known sound-rejection edge — for
>    example, `?B = 0` satisfying `?A^?B = 1` with `?A = 0`, yielding
>    `Func("^", (Const(0), Const(0)))`. `arithEval` rejects this with
>    `MalformedArithmetic` not because the witness is wrong but
>    because the kernel deliberately does not commit to a value for
>    `0^0`. This is **not** a dispatcher bug; it is a real signal that
>    the witness falls outside `arithEval`'s convention-agnostic
>    fragment. The dispatcher should classify the original goal as
>    `OutsideFragment` (or, if the constraint admits other witnesses
>    that are uncontested, request an alternative witness) rather than
>    crashing.
>
> The recommended distinction in `DISPATCH_DESIGN.md`: a
> `MalformedArithmetic` rejection on an `^` atom (or any other
> operator that future revisions add to the contested-edge list) is
> sound rejection → fall through to `OutsideFragment`; otherwise
> (`EvaluationFalse` on any atom, or `MalformedArithmetic` on an atom
> whose shape is fully within the evaluable set with no contested
> operators) it is solver/kernel disagreement → crash. The exact
> classification table is `DISPATCH_DESIGN.md`'s deliverable; this
> design fixes only the kernel side.

### 12.2 For the renderer (`solve/RENDER_M2_DESIGN.md`, Task C)

- An arithmetic-origin SLD step (a step where the dispatcher resolved
  a goal rather than a clause) becomes a single `arithEval` line in
  the rendered proof.
- The line's `formula` is the ground atom (after applying the final
  substitution to the original goal).
- `RuleApp` shape: `RuleApp("arithEval", (), (), {})`. Empty refs,
  empty extra.
- The rule alphabet for M2 expands from M1's `{Premise, forallE,
  andI, impE}` to `{Premise, forallE, andI, impE, arithEval}`.
- For mixed-goal queries (the §2 prime example), KB-resolved goals
  produce M1-style premise/forallE/impE lines and dispatcher-resolved
  goals produce `arithEval` lines, interleaved in goal order.
- Renderer property test (per `prd_milestone_2.md` §10.1): every
  rendered line's rule name is in the M2 alphabet. No rule outside
  the alphabet appears.

### 12.3 For tests (`tests/test_kernel_arith_eval.py`)

This file does not exist yet; Sonnet will create it during M2
implementation. Required coverage:

1. Every accept case in §11.1 (A1–A15) — assert `_arithEval` returns
   `None` (success) when wrapped in a one-line `Proof` and run through
   `check_proof`.
2. Every `EvaluationFalse` reject in §11.2 — assert `check_proof`
   returns `CheckFailure` with `reason` an instance of
   `EvaluationFalse`.
3. Every `MalformedArithmetic` reject in §11.3 — assert `check_proof`
   returns `CheckFailure` with `reason` an instance of
   `MalformedArithmetic` (M2 itself yields `UnresolvedMeta` via §5.3,
   not via `_arithEval`; that's a separate test asserting the
   ordering).
4. Every `WrongRefCount` reject in §11.4 — assert
   `WrongRefCount("arithEval", 0, ?, 0, ?)`.
5. **Soundness backstop**: a hand-built malicious one-line `Proof`
   claiming `Atom(">", (Const(2), Const(5)))` with `arithEval`
   justification — assert `check_proof` rejects with
   `EvaluationFalse`. Mirrors M0's `99_BAD_*` proofs and M1's
   renderer kernel-rejection test.
6. **Const guard**: `Const(3.14)` raises `TypeError` at construction
   (per `prd_milestone_2.md` §6.3). Independent of `arithEval`, but
   §14.8 of the M2 PRD lists this in DoD.
7. **Property test (Hypothesis)**: for randomly-generated ground
   arithmetic atoms (terms drawn from `int` and `Fraction` constants
   plus the operator set, atoms drawn from the predicate set),
   evaluate with `arithEval` AND with a reference Python expression
   (built directly from the same `int`s and `Fraction`s). Assert the
   two agree on every example. This is the soundness regression for
   the evaluator itself — if `arithEval` ever accepts a different
   atom-set than direct Python evaluation, the property test fails.

---

## 13. Non-goals

Explicit out-of-scope items, surfaced because future implementers may
be tempted to extend `arithEval`:

1. **Quantified arithmetic.** `(forall x. x + 0 = x)` is **not** in
   the evaluable set. Quantifier elimination is a job for `forallI` /
   `existsI` over `arithEval` body lines, when the dispatcher can
   provide a witness. `arithEval` itself rejects any atom with a
   quantifier or variable.
2. **Real arithmetic beyond ℚ.** `√2`, `π`, `e` are not in the
   evaluable set. Dispatcher classifies as `OutsideFragment`.
3. **Numerical approximation.** Float, `Decimal`, `nsolve`-style
   floating results are not in the evaluable set. Soundness-incompatible.
4. **Modular arithmetic.** `mod`, `div` (integer-quotient), `gcd`,
   `lcm` are not in the operator set. A future M6+ number-theory
   milestone may add them as new evaluable operators or as KB
   predicates; that is a separate design decision.
5. **Comparison of mixed types.** Python compares `int` with
   `Fraction` cleanly (§9.3); the rule supports this. But comparison
   of `Fraction` with `Const(str)` is non-evaluable, even if the
   string parses as a number. Strings stay strings.
6. **Implicit conversion.** `arithEval` does not coerce `Const("3")`
   into `Const(3)`. Strings are non-evaluable. The parser is
   responsible for producing `Const(int)` when it sees a numeric
   literal, per `prd_milestone_2.md` §11.
7. **Side-effecting evaluation.** `_eval_term` and `_eval_atom` are
   pure functions. No I/O, no global state, no caching. Determinism
   is required for kernel consistency.
8. **`0^0` in either direction.** Supporting `0^0 = 1` (the
   combinatorics convention) or `0^0` as a value at all is a
   deliberate future decision, not an oversight. The bare `^` operator
   stays convention-agnostic: it accepts only cases where ℤ/ℚ
   arithmetic is uncontested. If a future milestone needs combinatorial
   `0^0 = 1` (e.g. for polynomial-ring identities, generating
   functions, or finite-difference calculus), it must introduce an
   explicit operator that names its convention in its name — for
   example a `pow_combinatorial` predicate, a `nat_pow` operator, or a
   KB-side definitional clause. The kernel rule for that operator
   would document its chosen convention and reject the cases its
   convention does not cover. `^` itself does not silently take a
   side.

---

## 14. Summary for the implementer

What Sonnet should produce, against this design:

1. **`src/hlmr/kernel/errors.py`** — add two frozen dataclass error
   types: `MalformedArithmetic(line: int, formula: Formula, reason:
   str)` and `EvaluationFalse(line: int, formula: Formula)`. Both
   subclass `RuleError`. No other changes.

2. **`src/hlmr/kernel/rules.py`** — add three private helpers and
   register the rule:
   - `_eval_term(t: Term) -> int | Fraction | None` per §7.
   - `_eval_atom(f: Atom | Equals) -> bool | None` per §7.
   - `_arithEval(line: ProofLine, proof: Proof) -> RuleError | None`
     per §7.
   - `RULES["arithEval"] = _arithEval` in the dispatch dict.
   - `from fractions import Fraction` and import `Atom`, `Const`,
     `Equals`, `Func`, `Meta`, `Term`, `Var` from `hlmr.ir.formula`.

3. **`src/hlmr/kernel/check.py`** — **no changes**. The §5.3 walk and
   structural pass already handle `arithEval` lines.

4. **`tests/test_kernel_arith_eval.py`** — new file covering the
   accept/reject matrix in §11 plus the property test in §12.3 (7).

5. **`tests/test_kernel_isolation.py`** — should continue to pass
   unchanged. The new imports (`fractions.Fraction`, IR types already
   imported) are stdlib + `hlmr.ir.*`; no new untrusted-module
   dependencies.

Implementation should be small: roughly 80 lines in `rules.py` (two
helpers + the checker), 15 lines in `errors.py` (two dataclasses),
~150 lines of tests. The full diff for the kernel itself is under
100 lines.

---

## 15. Checklist against `prd_milestone_2.md` §6.4

| §6.4 deliverable | Where in this doc |
|---|---|
| Exact rule semantics | §3 |
| Set of ground evaluable atoms | §5 (atoms) and §6 (terms) |
| Evaluation algorithm | §7 |
| Behaviour on non-arithmetic `Func`, `Var`, `Meta` | §6, §9.8, §9.9 |
| Soundness argument | §9 |
| Python `int`/`Fraction` arithmetic relationship | §9.1–9.3 |
| Edge cases (extreme magnitudes, division by zero, int/rational coercion) | §9.4, §9.10, §11 |
| `float` defence-in-depth | §9.6 |
| Failure modes / specific error types | §10 |
| `MalformedArithmetic`, `EvaluationFalse` | §10.1, §10.2 |
| API surface — `RuleApp.extra` content | §4, §8.4 |
| Worked examples — accept and reject | §11 |

All §6.4 items addressed. Ready for review.
