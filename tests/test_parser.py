"""Tests for src/hlmr/parse/parser.py."""
from __future__ import annotations

import pytest

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.parse import ParseError, parse_clause, parse_file, parse_kb, parse_query

# ---------------------------------------------------------------------------
# Helpers for round-trip tests
# ---------------------------------------------------------------------------


def _term_str(t) -> str:
    """Minimal surface-syntax serializer for Terms — test use only."""
    from hlmr.ir.formula import Const, Func, Meta, Var
    match t:
        case Var(name=n):
            return n
        case Meta(name=n):
            return n  # includes leading "?"
        case Const(value=v):
            return str(v)
        case Func(name=n, args=args):
            return f"{n}({', '.join(_term_str(a) for a in args)})"


def _lit_str(f) -> str:
    """Minimal surface-syntax serializer for Atom|Equals — test use only."""
    match f:
        case Atom(pred=p, args=()):
            return p
        case Atom(pred=p, args=args):
            return f"{p}({', '.join(_term_str(a) for a in args)})"
        case Equals(lhs=lhs, rhs=rhs):
            return f"{_term_str(lhs)} = {_term_str(rhs)}"


def _clause_str(c: Clause) -> str:
    head = _lit_str(c.head)
    if c.body:
        body = ", ".join(_lit_str(b) for b in c.body)
        return f"{head} :- {body}."
    return f"{head}."


# ---------------------------------------------------------------------------
# parse_clause — facts
# ---------------------------------------------------------------------------


def test_clause_simple_fact() -> None:
    c = parse_clause("human(socrates).")
    assert c.name == "human_1"
    assert c.head == Atom("human", (Const("socrates"),))
    assert c.body == ()


def test_clause_multi_arg_fact() -> None:
    c = parse_clause("parent(alice, bob).")
    assert c.head == Atom("parent", (Const("alice"), Const("bob")))
    assert c.body == ()


def test_clause_zero_arity_fact() -> None:
    c = parse_clause("raining.")
    assert c.head == Atom("raining", ())
    assert c.body == ()


def test_clause_integer_constant() -> None:
    c = parse_clause("even(0).")
    assert c.head == Atom("even", (Const(0),))


def test_clause_nested_func() -> None:
    c = parse_clause("even(s(s(0))).")
    expected = Atom("even", (Func("s", (Func("s", (Const(0),)),)),))
    assert c.head == expected


def test_clause_equality_as_head() -> None:
    c = parse_clause("0 = 0.")
    assert c.name == "eq_1"
    assert c.head == Equals(Const(0), Const(0))
    assert c.body == ()


# ---------------------------------------------------------------------------
# parse_clause — variable conventions
# ---------------------------------------------------------------------------


def test_clause_uppercase_var() -> None:
    c = parse_clause("mortal(X) :- human(X).")
    assert c.head == Atom("mortal", (Var("X"),))
    assert c.body == (Atom("human", (Var("X"),)),)


def test_clause_underscore_var() -> None:
    c = parse_clause("p(_foo).")
    assert c.head == Atom("p", (Var("_foo"),))


def test_clause_lowercase_is_const() -> None:
    c = parse_clause("parent(alice, bob).")
    assert isinstance(c.head.args[0], Const)
    assert isinstance(c.head.args[1], Const)


def test_clause_multi_body_rule() -> None:
    c = parse_clause("ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).")
    assert c.head == Atom("ancestor", (Var("X"), Var("Y")))
    assert len(c.body) == 2
    assert c.body[0] == Atom("parent", (Var("X"), Var("Z")))
    assert c.body[1] == Atom("ancestor", (Var("Z"), Var("Y")))


def test_clause_body_equality() -> None:
    c = parse_clause("same(X, Y) :- X = Y.")
    assert c.head == Atom("same", (Var("X"), Var("Y")))
    assert c.body == (Equals(Var("X"), Var("Y")),)


def test_clause_name_uses_head_pred() -> None:
    c = parse_clause("in_list(X, Y) :- member(X, Y).")
    assert c.name == "in_list_1"


# ---------------------------------------------------------------------------
# parse_clause — ParseError cases
# ---------------------------------------------------------------------------


def test_clause_empty_raises() -> None:
    with pytest.raises(ParseError):
        parse_clause("")


def test_clause_missing_dot_raises() -> None:
    with pytest.raises(ParseError):
        parse_clause("human(socrates)")


def test_clause_meta_in_head_raises() -> None:
    with pytest.raises(ParseError, match="metavariable"):
        parse_clause("mortal(?X).")


def test_clause_meta_in_body_raises() -> None:
    with pytest.raises(ParseError, match="metavariable"):
        parse_clause("p(X) :- q(?X).")


def test_clause_bad_syntax_raises() -> None:
    with pytest.raises(ParseError):
        parse_clause(":-.")  # rule with no head


# ---------------------------------------------------------------------------
# parse_query
# ---------------------------------------------------------------------------


def test_query_ground() -> None:
    q = parse_query("?- mortal(socrates).")
    assert q == Atom("mortal", (Const("socrates"),))


def test_query_meta() -> None:
    q = parse_query("?- ancestor(?X, alice).")
    assert q == Atom("ancestor", (Meta("?X"), Const("alice")))


def test_query_equality() -> None:
    q = parse_query("?- X = Y.")
    assert q == Equals(Var("X"), Var("Y"))


def test_query_ground_equality() -> None:
    q = parse_query("?- 0 = 0.")
    assert q == Equals(Const(0), Const(0))


def test_query_zero_arity() -> None:
    q = parse_query("?- raining.")
    assert q == Atom("raining", ())


def test_query_missing_prefix_raises() -> None:
    with pytest.raises(ParseError):
        parse_query("mortal(socrates).")


def test_query_missing_dot_raises() -> None:
    with pytest.raises(ParseError):
        parse_query("?- mortal(socrates)")


# ---------------------------------------------------------------------------
# parse_kb
# ---------------------------------------------------------------------------


def test_kb_empty_source() -> None:
    kb = parse_kb("")
    assert kb == KnowledgeBase(())


def test_kb_single_fact() -> None:
    kb = parse_kb("human(socrates).")
    assert len(kb.clauses) == 1
    assert kb.clauses[0].name == "human_1"
    assert kb.clauses[0].head == Atom("human", (Const("socrates"),))


def test_kb_auto_names_per_predicate() -> None:
    src = "human(socrates).\nhuman(bob).\nmortal(X) :- human(X)."
    kb = parse_kb(src)
    assert kb.clauses[0].name == "human_1"
    assert kb.clauses[1].name == "human_2"
    assert kb.clauses[2].name == "mortal_1"


def test_kb_comments_stripped() -> None:
    src = (
        "% this is a comment\n"
        "human(socrates). % inline comment\n"
        "% another comment\n"
        "mortal(X) :- human(X).\n"
    )
    kb = parse_kb(src)
    assert len(kb.clauses) == 2


def test_kb_blank_lines_ok() -> None:
    src = "\n\nhuman(socrates).\n\n\nmortal(X) :- human(X).\n\n"
    kb = parse_kb(src)
    assert len(kb.clauses) == 2


def test_kb_syntax_error_raises() -> None:
    src = "human(socrates).\nbad syntax here\nmortal(X) :- human(X)."
    with pytest.raises(ParseError):
        parse_kb(src)


def test_kb_meta_in_clause_raises() -> None:
    src = "human(?X).\n"
    with pytest.raises(ParseError, match="metavariable"):
        parse_kb(src)


def test_kb_kinship_full() -> None:
    src = (
        "parent(alice, bob).\n"
        "parent(bob, carol).\n"
        "ancestor(X, Y) :- parent(X, Y).\n"
        "ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).\n"
    )
    kb = parse_kb(src)
    assert len(kb.clauses) == 4
    assert kb.clauses[0].name == "parent_1"
    assert kb.clauses[1].name == "parent_2"
    assert kb.clauses[2].name == "ancestor_1"
    assert kb.clauses[3].name == "ancestor_2"
    # Verify multi-body rule
    rec = kb.clauses[3]
    assert len(rec.body) == 2


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------


def test_parse_file_round_trip(tmp_path) -> None:
    src = (
        "% kinship KB\n"
        "parent(alice, bob).\n"
        "mortal(X) :- human(X).\n"
    )
    f = tmp_path / "test.pl"
    f.write_text(src, encoding="utf-8")
    kb = parse_file(str(f))
    assert len(kb.clauses) == 2
    assert kb.clauses[0].head == Atom("parent", (Const("alice"), Const("bob")))
    assert kb.clauses[1].name == "mortal_1"


def test_parse_file_pathlib(tmp_path) -> None:
    src = "even(0).\neven(s(s(N))) :- even(N).\n"
    f = tmp_path / "even.pl"
    f.write_text(src, encoding="utf-8")
    kb = parse_file(f)
    assert len(kb.clauses) == 2


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


ROUND_TRIP_FIXTURES = [
    "human(socrates).",
    "parent(alice, bob).",
    "raining.",
    "mortal(X) :- human(X).",
    "ancestor(X, Y) :- parent(X, Y).",
    "ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).",
    "even(0).",
    "even(s(s(N))) :- even(N).",
    "same(X, Y) :- X = Y.",
    "in_list(X, _rest) :- member(X, _rest).",
]


@pytest.mark.parametrize("source", ROUND_TRIP_FIXTURES)
def test_round_trip(source: str) -> None:
    """Parse → serialize → re-parse must yield the same head and body."""
    c1 = parse_clause(source)
    serialized = _clause_str(c1)
    c2 = parse_clause(serialized)
    assert c1.head == c2.head
    assert c1.body == c2.body


# ---------------------------------------------------------------------------
# Peano demo-specific parsing (used by solve/ demos)
# ---------------------------------------------------------------------------


def test_parse_peano_even_kb() -> None:
    src = "even(0).\neven(s(s(N))) :- even(N).\n"
    kb = parse_kb(src)
    assert len(kb.clauses) == 2
    # Base case
    assert kb.clauses[0].head == Atom("even", (Const(0),))
    assert kb.clauses[0].body == ()
    # Inductive step: head = even(s(s(N))), body = [even(N)]
    step = kb.clauses[1]
    expected_head = Atom("even", (Func("s", (Func("s", (Var("N"),)),)),))
    assert step.head == expected_head
    assert step.body == (Atom("even", (Var("N"),)),)
