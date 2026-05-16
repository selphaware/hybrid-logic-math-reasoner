# PARSER_AUDIT.md

**Author:** Claude Opus 4.7
**Purpose:** Audit the state of M2 parser-extension prerequisites before any code is written. Identify what is already in place, what is missing, and where the PRD §11 spec leaves real design choices that need user input.
**Status:** Phase 1 deliverable. STOP. Awaiting user acknowledgement before Phase 2.

---

## A. IR state (PRD §6.1, §6.3)

### A.1 Typed metavariables — §6.1 NOT implemented

`src/hlmr/ir/formula.py` line 49–60:

```python
@dataclass(frozen=True)
class Meta(Term):
    name: str
```

No `kind` field. None of `MetaKind`, `Categorical`, `Integer`, `Rational`, `FiniteDomain` exist in the IR. §6.1 is unbuilt.

Consequence: PRD §11 item 4 ("Typed metavariables — surface syntax `?X : Integer`") cannot be implemented without first extending the IR. Any parser code for typed-meta syntax would have nowhere to write the kind to.

### A.2 `Const` tightening — §6.3 PARTIALLY implemented

`src/hlmr/ir/formula.py` line 23–34:

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

The type signature and runtime `bool`/`float` rejection are in place. `Const(Fraction(...))` is the supported rational type — that's what the parser must produce for `3/4`-style literals.

### A.3 JSON schema version — §6.3 schema bump NOT done

`src/hlmr/ir/serialise.py` line 26: `SCHEMA_VERSION = 1`. The strict-equality check at line 238–241 still raises on `version != 1`. PRD §6.3 says M2 should accept both 1 and 2 and emit 2 always. This is not done.

This **only** matters for typed-meta serialisation (§6.1). Since §6.1 isn't implemented, no v2 proof JSONs exist yet, so the schema bump is downstream of §6.1.

---

## B. Parser state (current grammar)

`src/hlmr/parse/grammar.lark` is the M1 grammar. It accepts:

- Clauses with Horn-clause body (`p(X) :- q(X), r(X).`)
- Single-goal queries (`?- mortal(socrates).`)
- Equality (`X = Y`) in literal position
- LNAME predicates and functions (lowercase identifiers)
- VARIABLE (uppercase) and META (`?Uppercase`) terms
- INTEGER literals (non-negative)

It does NOT accept:

- Multi-goal queries (`?- a, b.`)
- Operator atoms (`X > 5`)
- Operator-form arithmetic terms (`x + y`, `x^2`)
- Rational literals (`3/4`)
- Negative literals (`-7`)
- Typed metavariables (`?X : Integer`)

A few empirical confirmations via `parse_query()`:

| Source | Result |
|---|---|
| `?- plus(?X, ?Y, 10).` | ✓ (LNAME predicate) |
| `?- ?X = 5.` | ✓ (Equals on int) |
| `?- ?X > 5.` | **ParseError** — `>` not in grammar |
| `?- prime(?P), ?P > 2.` | **ParseError** — `,` in query position not in grammar |
| `?- root_of(?X, x^2 - 5*x + 6).` | **ParseError** — `^`, `*`, `-` not in grammar |

The current grammar is roughly 50 lines. The M2 extension will roughly double it.

---

## C. Dispatcher contract — exact predicate and Func names

From `src/hlmr/dispatch/classify.py` lines 33–46:

```python
_COMPARISON_PREDS  = frozenset({"<", "<=", ">", ">=", "!="})
_TERNARY_PREDS     = frozenset({"plus", "minus", "times", "divides"})
_ARITH_OPERATORS   = frozenset({"+", "-", "*", "/", "^"})
```

The parser's output must use exactly these names. Specifically:

- Comparison atoms: `Atom("<", (a, b))`, `Atom(">", ...)`, `Atom("<=", ...)`, `Atom(">=", ...)`, `Atom("!=", (a, b))`
- Ternary atoms (already work — they're LNAMEs): `Atom("plus", (a, b, c))`, `Atom("minus", ...)`, `Atom("times", ...)`, `Atom("divides", ...)`
- `root_of` (already works): `Atom("root_of", (target, poly))`
- Equality: `Equals(lhs, rhs)` IR node (already exists)
- Operator Funcs: `Func("+", (a, b))`, `Func("-", (a, b))`, `Func("-", (a,))` (unary), `Func("*", (a, b))`, `Func("/", (a, b))`, `Func("^", (a, b))`

Notes:
- The `=` symbol in source becomes the `Equals` IR node — **not** `Atom("=", ...)`. M1 already does this; the M2 grammar must do the same for the new equality contexts.
- `!=` becomes `Atom("!=", ...)` (NOT a `Not(Equals(...))`). Consistent with the classifier's expectations.
- The polynomial-in-`root_of` uses arithmetic-operator Funcs internally, not LNAME functions. E.g. `root_of(?X, x^2 - 5*x + 6)` produces `Atom("root_of", (Meta("?X"), Func("+", (Func("-", ...), Const(6)))))`.

---

## D. Demo IR shapes (verification bar)

The parser must produce IR equal **by Python `==`** to what `demos.py` constructs. Hand-computed for each demo:

### D.1 `prime_search`

```hlmr
?- prime(?P), ?P > 2, ?P < 6, ?P != 4.
```

Expected parse result (tuple of four atoms):

```python
(
    Atom("prime", (Meta("?P"),)),
    Atom(">",  (Meta("?P"), Const(2))),
    Atom("<",  (Meta("?P"), Const(6))),
    Atom("!=", (Meta("?P"), Const(4))),
)
```

### D.2 `quadratic`

```hlmr
?- root_of(?X, x^2 - 5*x + 6).
```

Expected parse result (one-element tuple wrapping a single goal):

```python
(
    Atom("root_of", (
        Meta("?X"),
        Func("+", (
            Func("-", (
                Func("^", (Var("x"), Const(2))),
                Func("*", (Const(5), Var("x"))),
            )),
            Const(6),
        )),
    )),
)
```

This requires (a) `^` tighter than `*`, (b) `*` tighter than `+`/`-`, (c) `+`/`-` left-associative — the parsed tree for `x^2 - 5*x + 6` is `((x^2 - 5*x) + 6)`, not `(x^2 - (5*x + 6))`.

### D.3 `linear_system`

```hlmr
?- ?X = 2, ?X + ?Y = 10.
```

Expected parse result (tuple of two `Equals`):

```python
(
    Equals(Meta("?X"), Const(2)),
    Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
)
```

Notes: `=` produces the `Equals` IR node (not `Atom("=", ...)`). The expression `?X + ?Y = 10` parses as `Equals(Func("+", (?X, ?Y)), Const(10))` — `=` is at lower precedence than `+`.

### D.4 `outside_fragment`

```hlmr
?- root_of(?X, 2^x).
```

Expected parse result:

```python
(
    Atom("root_of", (
        Meta("?X"),
        Func("^", (Const(2), Var("x"))),
    )),
)
```

This is a single-goal query that wraps in a 1-tuple. The polynomial `2^x` has a `Var("x")` in exponent position — perfectly parseable; the dispatcher's classifier rejects it as `TRANSCENDENTAL`.

---

## E. Tutorial REPL claims

Queries the tutorial shows as REPL input that **must work** after the extension:

| Section | Query | Status today |
|---|---|---|
| §4 (kinship) | `?- ancestor(?A, carol).` | ✓ works (M1) |
| §4 (plus) | `?- plus(2, 3, ?Z).` | ✓ works (LNAME) |
| §4 (minus) | `?- minus(?X, 3, 7).` | ✓ works (LNAME) |
| §4 (Equals) | `?- ?X = 5.` | ✓ works (M1) |
| §4 (Underdetermined) | `?- plus(?X, ?Y, 10).` | ✓ works (LNAME) |

The §4 "Limits of the REPL parser" subsection (lines 296–317 of tutorial.md) explicitly documents what doesn't work:

- `?- ?X > 5.` (operator atoms)
- `?- prime(?P), gt(?P, 2).` (multi-goal)
- `?- root_of(?X, x^2 - 5*x + 6).` (operator-form polynomial)

After the M2 parser extension lands, **this subsection of the tutorial becomes stale** — the limits it documents are gone. It needs revision (or deletion). I will flag this in the handoff but **not** edit the tutorial in this session — that's a separate writing task once the implementation is verified.

The user's failing REPL session (the trigger for this work) was:

```
kb> prime(2).      ← already works
kb> prime(3).      ← already works
kb> prime(5).      ← already works
kb> prime(7).      ← already works
kb> :query
?- prime(?P), ?P > 2, ?P < 6, ?P != 4.   ← FAILS today; must work after fix
?- ?X = 2, ?X + ?Y = 10.                 ← FAILS today; must work
?- root_of(?X, x^2 - 5*x + 6).            ← FAILS today; must work
```

Phase 4 verifies these all parse, dispatch, and produce kernel-verified proofs matching the corresponding CLI demos.

---

## F. Scope decision

**In scope this session: PRD §11 items 1, 2, 3.**

- Item 1: Multi-goal queries via comma. `parse_query` returns `tuple[Atom | Equals, ...]` always.
- Item 2: Numeric literals — integer (already in M1 lexer) plus rational `n/m`. No negative literals (see G.3).
- Item 3: Operator atoms — comparisons (`<`, `<=`, `>`, `>=`, `!=`), arithmetic operator-form terms (`+`, `-`, `*`, `/`, `^`), with standard precedence and associativity.

**Out of scope this session: PRD §11 item 4 (typed metavariables).**

Reason: Item 4 requires §6.1 IR prerequisites (`MetaKind`, `Meta.kind` field) that are NOT in the codebase. Building the parser side first would write IR objects with a `kind` field that doesn't exist on `Meta`. The §6.1 IR change is a separate, non-trivial work item involving:

1. `formula.py`: add `MetaKind` hierarchy and `kind` field on `Meta` with `Categorical()` default.
2. `serialise.py`: bump schema to v2 with backward-compatible reading of v1.
3. Test suite: confirm 998 tests still pass (some may serialise Meta and need to handle the new field).
4. Demos: confirm `Meta("?P")` still constructs the equivalent of `Meta("?P", Categorical())` and that demo IR comparisons still hold.
5. **Then** the parser can add the typed-meta production.

This is its own focused session. Splitting items 1–3 from item 4 is consistent with the PRD's enumeration (items are independently scoped) and unblocks the user's failing REPL queries immediately. The follow-up typed-meta session can run in parallel with M3 design work; the user's REPL fluency is the urgent need.

---

## G. Open design questions — proposed resolutions

These are choices the PRD §11 spec doesn't fully nail down. I propose a resolution for each; the user should acknowledge or override before I proceed to Phase 2.

### G.1 `parse_query` return type — breaking change?

PRD §11 item 1 says:

> Output type: `tuple[Atom | Equals, ...]` instead of the single `Atom | Equals` from M1. `parse_query` is updated accordingly; existing single-literal queries continue to parse into a one-element tuple for forward compatibility.

The constraint in this session's prompt says:

> M1 parser tests (45 in `test_parser.py`) all continue to pass.

These conflict for the 7 M1 tests in `test_parser.py` that directly assert what `parse_query` returns (lines 166–198). Example today:

```python
assert q == Atom("mortal", (Const("socrates"),))
```

After the change: `q` is `(Atom("mortal", ...),)` — a 1-tuple. The assertion needs updating to `assert q == (Atom("mortal", ...),)`.

**Proposed resolution**: follow the PRD. Update the 7 `parse_query` assertions in `test_parser.py` to expect 1-tuples for single-goal queries. The other 38 tests (which test `parse_clause` and `parse_kb`) are unaffected.

Alternative: keep `parse_query` returning single literals and add a new `parse_query_goals` returning tuples. Cleaner test-compat story but diverges from PRD spec and leaves two functions where one suffices.

**Recommendation: take the breaking change.** It is the PRD's explicit instruction and produces a cleaner API. The test updates are mechanical (wrap the expected literal in a 1-tuple).

Callers needing updates beyond test_parser.py:
- `src/hlmr/repl/interactive.py:_run_query_loop` — already accepts a single goal; will need to either accept tuple or have the caller (REPL command handler) iterate.
- `src/hlmr/repl/commands.py` — constructs `Command("query", {"goal": atom})` from `parse_query`'s output; needs to handle tuple.
- `src/hlmr/demos.py` — doesn't call `parse_query`. Unaffected.

The REPL update is small but non-trivial; it must thread the tuple through the existing query loop. This work belongs in this session.

### G.2 Rational literal syntax — `3/4` token vs operator division

PRD §11 item 2 says "`3/4` parse[s] as `Const(int)` or `Const(Fraction)`." But `/` is also a binary operator (item 3), so `3 / 4` could parse as `Func("/", (Const(3), Const(4)))`.

**Proposed resolution**: special lexer token. `INTEGER "/" INTEGER` with no intervening whitespace lexes as a `RATIONAL` token → `Const(Fraction(n, m))`. With whitespace (`3 / 4`), the lexer sees `INTEGER` `/` `INTEGER` and parses as `Func("/", ...)`.

Edge cases:
- `3/4` → `Const(Fraction(3, 4))` ✓
- `3 / 4` → `Func("/", (Const(3), Const(4)))` ✓ (different IR; semantically equal under arithEval)
- `?X / 2` → `Func("/", (Meta("?X"), Const(2)))` ✓
- `3/0` → lexer accepts the token, but constructing `Fraction(3, 0)` raises `ZeroDivisionError`. The transformer can catch this and raise `ParseError("rational literal has zero denominator")`. Alternative: reject at lexer via regex `[1-9][0-9]*`. **Recommendation: reject at lexer** — `/0` in rational literal position is a typo, not a meaningful constant.

Implementation: `RATIONAL: /(0|[1-9][0-9]*)\/[1-9][0-9]*/` as a separate token defined BEFORE INTEGER in the lexer.

### G.3 Unary minus and negative literals — defer

PRD §11 item 2 says "`-7` parses as `Const(int)`." But `-7` is also valid surface syntax for `Func("-", (Const(7),))` (unary minus applied to `7`).

None of the four demos use negative literals or unary minus — the polynomial `x^2 - 5*x + 6` uses binary subtraction only.

**Proposed resolution: defer unary minus and negative literals to a future session.** Numeric literals are non-negative integers and `n/m` rationals (with positive `m`). If a query needs negation, the user writes `0 - 7` or `0 - x`.

This avoids the ambiguity between `Const(-7)` and `Func("-", (Const(7),))` and avoids a tricky grammar precedence problem (`x - -7` would need careful disambiguation). The four demos verify cleanly without unary minus.

If the user wants unary minus shipped this session, I can add it — but the cleaner choice is to defer it and re-evaluate after seeing what queries the user actually wants to type.

### G.4 Test file location

The prompt suggests `tests/parse/test_m2_grammar.py`. The current tests/ directory is flat (no subdirectories — all test files at `tests/test_*.py`).

**Proposed resolution**: flat layout. Create `tests/test_m2_grammar.py` alongside `tests/test_parser.py`. Matches existing convention; no need to introduce a subdirectory for one file.

If the user prefers `tests/parse/test_m2_grammar.py`, I'll create the subdirectory plus an `__init__.py`. Either works.

### G.5 Operator precedence summary (no resolution needed; this is documentation)

Standard arithmetic precedence, encoded via Lark grammar levels:

| Level | Operators | Associativity |
|---|---|---|
| 6 (loosest) | `=` (Equals) | none — `a = b = c` is a parse error |
| 5 | `<`, `<=`, `>`, `>=`, `!=` | none — `a < b < c` is a parse error |
| 4 | `+`, `-` (binary) | left |
| 3 | `*`, `/` | left |
| 2 (tightest, operator) | `^` | right — `2^3^4` parses as `2^(3^4)` |
| 1 | parenthesised, primary terms | — |

`a = b = c` and `a < b < c` are non-associative parse errors rather than parsed left-to-right because (a) the IR has no chained equality/comparison and (b) the dispatcher's classifier expects exactly two arguments per comparison atom.

---

## H. Implementation sketch (for Phase 2 reference, after audit acknowledgement)

Two-file change plus test file:

1. **`src/hlmr/parse/grammar.lark`** — extend with operator productions, multi-goal query rule, rational token. Roughly 40 new lines.

2. **`src/hlmr/parse/parser.py`** — extend transformer with new methods for each new grammar production. Update `parse_query` to always return a tuple. Roughly 60 new lines.

3. **`src/hlmr/repl/interactive.py`** — `_run_query_loop` accepts tuple goal. Roughly 15 lines.

4. **`src/hlmr/repl/commands.py`** — `Command("query", ...)` args holds a tuple. Roughly 5 lines.

5. **`tests/test_parser.py`** — update 7 `parse_query` assertions to expect 1-tuples.

6. **`tests/test_m2_grammar.py`** — new file, roughly 200 lines: per-feature, demo-parity, precedence, error, property tests.

Verification: run the user's three failing REPL queries; confirm each succeeds. Compare each rendered proof against the corresponding CLI demo's proof.

---

## Summary for user review

Three things to confirm before Phase 2:

1. **Scope decision (F)**: items 1–3 of PRD §11 in scope; item 4 (typed metas) deferred to a focused session after §6.1 IR work lands. **Accept?**

2. **Breaking change to `parse_query` (G.1)**: change return type to tuple as PRD specifies; update 7 M1 test assertions accordingly. The cleaner alternative is a new `parse_query_goals` function preserving M1 API; the PRD prefers the breaking change. **Accept the breaking change, or prefer the alternative?**

3. **Rational literal lexing (G.2)**: `3/4` (no spaces) lexes as a rational token; `3 / 4` (with spaces) parses as `Func("/", ...)`. **Accept?**

The other proposed resolutions (G.3 defer unary minus, G.4 flat test layout, G.5 standard precedence) are noted as proposals; the user can override any of them but they're less load-bearing than 1–3.

After acknowledgement (or override) I proceed to Phase 2.
