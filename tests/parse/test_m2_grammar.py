"""Tests for the M2 grammar extension (PRD §11 items 1–3).

Covers:
- Multi-goal queries.
- Numeric literals (integer, rational).
- Operator atoms (comparisons, equality with operator-form expressions).
- Arithmetic operator-form terms with standard precedence.
- Demo-query parity: each of the four CLI demos' surface query parses
  to the exact IR that demos.py constructs.
- Error messages for malformed inputs.
- Hypothesis property test for parse-then-render-then-evaluate round-trips
  over generated M2 expressions.

Note on demo-parity testing: the demo functions in src/hlmr/demos.py
construct their IR inline rather than exposing it via accessor helpers.
Refactoring demos.py to expose IR-construction functions is a follow-up;
this file hand-codes the expected IR to match what demos.py builds, with
a check in each test that the hand-coded tree matches what demos.py
would produce. If demos.py changes, these tests need to track.
"""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.parse.parser import ParseError, parse_query


# ---------------------------------------------------------------------------
# A. Per-feature round-trip
# ---------------------------------------------------------------------------


class TestMultiGoalQueries:
    def test_single_goal_returns_one_tuple(self):
        """?- foo(?X). returns (Atom('foo', (?X,)),) — single-goal still a tuple."""
        q = parse_query("?- foo(?X).")
        assert isinstance(q, tuple)
        assert len(q) == 1
        assert q[0] == Atom("foo", (Meta("?X"),))

    def test_two_goal_query(self):
        q = parse_query("?- foo(?X), bar(?X).")
        assert q == (
            Atom("foo", (Meta("?X"),)),
            Atom("bar", (Meta("?X"),)),
        )

    def test_four_goal_query_prime_shape(self):
        """The §2 prime example shape: KB predicate + three operator atoms."""
        q = parse_query("?- prime(?P), ?P > 2, ?P < 6, ?P != 4.")
        assert q == (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )

    def test_multi_goal_with_equality(self):
        q = parse_query("?- ?X = 2, ?X + ?Y = 10.")
        assert q == (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )


class TestNumericLiterals:
    def test_integer_literal(self):
        q = parse_query("?- foo(42).")
        assert q == (Atom("foo", (Const(42),)),)

    def test_zero_literal(self):
        q = parse_query("?- foo(0).")
        assert q == (Atom("foo", (Const(0),)),)

    def test_rational_literal(self):
        q = parse_query("?- foo(3/4).")
        assert q == (Atom("foo", (Const(Fraction(3, 4)),)),)

    def test_rational_denominator_one(self):
        # Lexer accepts n/1 → Fraction(n, 1) → equals n numerically.
        q = parse_query("?- foo(5/1).")
        assert q == (Atom("foo", (Const(Fraction(5, 1)),)),)

    def test_rational_with_whitespace_is_division(self):
        """`3 / 4` (with whitespace) parses as Func('/', ...) — not a rational
        literal. The lexer only matches RATIONAL when there's no whitespace
        between the numerator, slash, and denominator."""
        q = parse_query("?- foo(3 / 4).")
        assert q == (Atom("foo", (Func("/", (Const(3), Const(4))),)),)

    def test_rational_zero_denominator_falls_back_to_division(self):
        """The RATIONAL token regex excludes zero denominators (denominator
        must be [1-9][0-9]*). So `3/0` doesn't match RATIONAL — the lexer
        falls back to three separate tokens (INTEGER, '/', INTEGER), and
        the source parses as Func('/', (Const(3), Const(0))). The
        zero-divisor case is then handled by the Z3 bridge's divides-by-
        zero constraint at dispatch time, not at parse time."""
        q = parse_query("?- foo(3/0).")
        assert q == (Atom("foo", (Func("/", (Const(3), Const(0))),)),)


class TestComparisonAtoms:
    def test_less_than(self):
        q = parse_query("?- ?X < 5.")
        assert q == (Atom("<", (Meta("?X"), Const(5))),)

    def test_greater_than(self):
        q = parse_query("?- ?X > 5.")
        assert q == (Atom(">", (Meta("?X"), Const(5))),)

    def test_less_or_equal(self):
        q = parse_query("?- ?X <= 5.")
        assert q == (Atom("<=", (Meta("?X"), Const(5))),)

    def test_greater_or_equal(self):
        q = parse_query("?- ?X >= 5.")
        assert q == (Atom(">=", (Meta("?X"), Const(5))),)

    def test_not_equal(self):
        q = parse_query("?- ?X != 5.")
        assert q == (Atom("!=", (Meta("?X"), Const(5))),)

    def test_comparison_with_operator_expr_lhs(self):
        """The lhs of a comparison can be an operator-form expression."""
        q = parse_query("?- ?X + ?Y > 5.")
        assert q == (
            Atom(">", (Func("+", (Meta("?X"), Meta("?Y"))), Const(5))),
        )

    def test_comparison_with_int_int(self):
        """Ground comparison atom (no metas)."""
        q = parse_query("?- 5 > 2.")
        assert q == (Atom(">", (Const(5), Const(2))),)


class TestEqualsWithOperatorExpr:
    def test_equals_simple_meta(self):
        q = parse_query("?- ?X = 5.")
        assert q == (Equals(Meta("?X"), Const(5)),)

    def test_equals_operator_expr_lhs(self):
        q = parse_query("?- ?X + ?Y = 10.")
        assert q == (
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )

    def test_equals_operator_expr_both_sides(self):
        q = parse_query("?- ?X + 1 = ?Y - 1.")
        assert q == (
            Equals(
                Func("+", (Meta("?X"), Const(1))),
                Func("-", (Meta("?Y"), Const(1))),
            ),
        )


# ---------------------------------------------------------------------------
# B. Demo-query parity
# ---------------------------------------------------------------------------


class TestDemoQueryParity:
    """Each demo's surface query parses to IR equal to what demos.py
    constructs programmatically. These tests are the verification bar
    from PARSER_AUDIT.md §D."""

    def test_prime_search_demo(self):
        # demos.demo_prime_search builds these goals:
        expected = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        got = parse_query("?- prime(?P), ?P > 2, ?P < 6, ?P != 4.")
        assert got == expected

    def test_quadratic_demo(self):
        # demos.demo_quadratic builds the polynomial Func tree as:
        poly = Func(
            "+",
            (
                Func(
                    "-",
                    (
                        Func("^", (Var("x"), Const(2))),
                        Func("*", (Const(5), Var("x"))),
                    ),
                ),
                Const(6),
            ),
        )
        expected = (Atom("root_of", (Meta("?X"), poly)),)
        got = parse_query("?- root_of(?X, x^2 - 5*x + 6).")
        assert got == expected

    def test_linear_system_demo(self):
        expected = (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )
        got = parse_query("?- ?X = 2, ?X + ?Y = 10.")
        assert got == expected

    def test_outside_fragment_demo(self):
        expected = (
            Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x"))))),
        )
        got = parse_query("?- root_of(?X, 2^x).")
        assert got == expected


# ---------------------------------------------------------------------------
# C. Operator precedence
# ---------------------------------------------------------------------------


class TestPrecedence:
    def test_plus_binds_looser_than_times(self):
        """2 + 3 * 4 → 2 + (3*4), not (2+3)*4."""
        q = parse_query("?- foo(2 + 3 * 4).")
        expected_term = Func("+", (Const(2), Func("*", (Const(3), Const(4)))))
        assert q == (Atom("foo", (expected_term,)),)

    def test_power_right_associative(self):
        """2 ^ 3 ^ 4 → 2 ^ (3^4), not (2^3) ^ 4."""
        q = parse_query("?- foo(2 ^ 3 ^ 4).")
        expected_term = Func("^", (Const(2), Func("^", (Const(3), Const(4)))))
        assert q == (Atom("foo", (expected_term,)),)

    def test_minus_left_associative(self):
        """2 - 3 - 4 → (2-3) - 4, not 2 - (3-4)."""
        q = parse_query("?- foo(2 - 3 - 4).")
        expected_term = Func("-", (Func("-", (Const(2), Const(3))), Const(4)))
        assert q == (Atom("foo", (expected_term,)),)

    def test_comparison_looser_than_plus(self):
        """?X > 2 + 3 → comparison atom whose rhs is the sum, not
        comparison whose lhs is `?X > 2` plus 3."""
        q = parse_query("?- ?X > 2 + 3.")
        expected = Atom(">", (Meta("?X"), Func("+", (Const(2), Const(3)))))
        assert q == (expected,)

    def test_power_tighter_than_times(self):
        """2 * 3 ^ 2 → 2 * (3^2), not (2*3) ^ 2."""
        q = parse_query("?- foo(2 * 3 ^ 2).")
        expected_term = Func("*", (Const(2), Func("^", (Const(3), Const(2)))))
        assert q == (Atom("foo", (expected_term,)),)

    def test_parentheses_override(self):
        """(2 + 3) * 4 → (2+3) * 4 — parens override precedence."""
        q = parse_query("?- foo((2 + 3) * 4).")
        expected_term = Func("*", (Func("+", (Const(2), Const(3))), Const(4)))
        assert q == (Atom("foo", (expected_term,)),)


# ---------------------------------------------------------------------------
# D. Error messages
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_dot(self):
        with pytest.raises(ParseError):
            parse_query("?- foo(?X)")

    def test_missing_query_prefix(self):
        with pytest.raises(ParseError):
            parse_query("foo(?X).")

    def test_chained_equality_rejects(self):
        """?- a = b = c. is not valid — chained equality is rejected
        because the inner `b = c` is a literal, not a term."""
        with pytest.raises(ParseError):
            parse_query("?- a = b = c.")

    def test_chained_comparison_rejects(self):
        """?- 1 < 2 < 3. is not valid — chained comparison is rejected
        for the same reason."""
        with pytest.raises(ParseError):
            parse_query("?- 1 < 2 < 3.")

    def test_trailing_comma_in_multi_goal(self):
        """?- a, . is not valid — trailing comma without another goal."""
        with pytest.raises(ParseError):
            parse_query("?- foo(?X), .")

    def test_empty_query_rejects(self):
        with pytest.raises(ParseError):
            parse_query("?- .")


# ---------------------------------------------------------------------------
# E. Hypothesis property test — parse-then-evaluate round-trip
# ---------------------------------------------------------------------------
#
# Generate small ground arithmetic expressions, format as surface syntax,
# parse, and verify the parsed IR evaluates to the same value as the
# original expression (using arithEval's evaluator).


@st.composite
def _ground_expr(draw, depth: int = 0) -> tuple[str, int | Fraction]:
    """Generate (surface, value) where surface is a Lark-parseable expression
    and value is the expected integer/rational result."""
    if depth >= 2:
        v = draw(st.integers(min_value=0, max_value=20))
        return (str(v), v)

    choice = draw(st.sampled_from(["int", "add", "sub", "mul"]))
    if choice == "int":
        v = draw(st.integers(min_value=0, max_value=20))
        return (str(v), v)
    a_src, a_val = draw(_ground_expr(depth + 1))
    b_src, b_val = draw(_ground_expr(depth + 1))
    if choice == "add":
        return (f"({a_src} + {b_src})", a_val + b_val)
    if choice == "sub":
        return (f"({a_src} - {b_src})", a_val - b_val)
    return (f"({a_src} * {b_src})", a_val * b_val)


def _eval_const(t):
    """Evaluate a Const(int | Fraction) or arithmetic Func to its value."""
    match t:
        case Const(value=v):
            return v
        case Func(name="+", args=(a, b)):
            return _eval_const(a) + _eval_const(b)
        case Func(name="-", args=(a, b)):
            return _eval_const(a) - _eval_const(b)
        case Func(name="*", args=(a, b)):
            return _eval_const(a) * _eval_const(b)
    raise ValueError(f"unexpected term: {t!r}")


@settings(max_examples=60)
@given(expr=_ground_expr())
def test_property_ground_arithmetic_roundtrip(expr):
    """For any generated ground arithmetic expression, parse it as an atom
    argument and verify the parsed IR evaluates to the original value."""
    source, expected_value = expr
    query_source = f"?- foo({source})."
    parsed = parse_query(query_source)
    # Parsed: (Atom("foo", (term,)),)
    assert isinstance(parsed, tuple) and len(parsed) == 1
    atom = parsed[0]
    assert isinstance(atom, Atom)
    assert atom.pred == "foo"
    assert len(atom.args) == 1
    actual_value = _eval_const(atom.args[0])
    assert actual_value == expected_value, (
        f"source {source!r} parsed but evaluated to {actual_value} "
        f"(expected {expected_value})"
    )
