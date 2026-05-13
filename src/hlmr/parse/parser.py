from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from lark import Lark, Transformer
from lark.exceptions import LarkError, UnexpectedCharacters, UnexpectedEOF, UnexpectedToken

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.ir.kb import Clause, KnowledgeBase

_GRAMMAR_TEXT = (Path(__file__).parent / "grammar.lark").read_text(encoding="utf-8")


class ParseError(Exception):
    """Raised when source text fails to parse.

    Message includes line and column from Lark where available.
    This is a user-facing error, not a Python stack trace.
    """


# ---------------------------------------------------------------------------
# Lark transformer: parse tree → IR objects directly
# ---------------------------------------------------------------------------


class _IRTransformer(Transformer):
    # --- Terms ---

    def var_term(self, items: list) -> Var:
        return Var(str(items[0]))

    def meta_term(self, items: list) -> Meta:
        return Meta(str(items[0]))

    def const_term(self, items: list) -> Const:
        return Const(str(items[0]))

    def int_term(self, items: list) -> Const:
        return Const(int(str(items[0])))

    def rational_term(self, items: list) -> Const:
        """RATIONAL token of form `n/m` (no whitespace) → Const(Fraction(n, m))."""
        n_str, m_str = str(items[0]).split("/", 1)
        return Const(Fraction(int(n_str), int(m_str)))

    def func_term(self, items: list) -> Func:
        name = str(items[0])
        args: list[Term] = items[1]
        return Func(name, tuple(args))

    def arglist(self, items: list) -> list[Term]:
        return list(items)

    # --- M2 operator-form arithmetic terms ---

    def add_term(self, items: list) -> Func:
        return Func("+", (items[0], items[1]))

    def sub_term(self, items: list) -> Func:
        return Func("-", (items[0], items[1]))

    def mul_term(self, items: list) -> Func:
        return Func("*", (items[0], items[1]))

    def div_term(self, items: list) -> Func:
        return Func("/", (items[0], items[1]))

    def pow_term(self, items: list) -> Func:
        return Func("^", (items[0], items[1]))

    # --- Atoms and equality ---

    def atom_no_args(self, items: list) -> Atom:
        return Atom(str(items[0]), ())

    def atom_args(self, items: list) -> Atom:
        name = str(items[0])
        args: list[Term] = items[1]
        atom = Atom(name, tuple(args))
        # Polynomial-variable rewrite: in `root_of(target, poly)`, the
        # second argument is conventionally a polynomial whose bare lowercase
        # identifiers are variables (e.g. `x`, `y`), not Prolog constants.
        # The classifier and SymPy bridge both accept Var or Meta as the
        # polynomial's free variable; the M1 grammar parses lowercase names
        # as Const(str). To make `root_of(?X, x^2 - 5*x + 6)` produce the
        # same IR as the programmatic CLI demo, rewrite Const(str) → Var(str)
        # inside the second argument of root_of/2 only.
        if name == "root_of" and len(atom.args) == 2:
            poly = _rewrite_lname_consts_to_vars(atom.args[1])
            atom = Atom(name, (atom.args[0], poly))
        return atom

    def comparison_atom(self, items: list) -> Atom:
        """expr COMP_OP expr → Atom(op, (lhs, rhs)). COMP_OP ∈ {<, <=, >, >=, !=}."""
        lhs = items[0]
        op = str(items[1])
        rhs = items[2]
        return Atom(op, (lhs, rhs))

    def equals_literal(self, items: list) -> Equals:
        """expr "=" expr → Equals IR node."""
        return Equals(items[0], items[1])

    # --- Body (returns list; clause() converts to tuple) ---

    def body(self, items: list) -> list[Atom | Equals]:
        return list(items)

    # --- Goals (multi-goal query body) ---

    def goals(self, items: list) -> tuple[Atom | Equals, ...]:
        """Multi-goal body: returns a tuple of literals."""
        return tuple(items)

    # --- Clause (returns pair; KnowledgeBase.Clause built in public API) ---

    def clause(
        self, items: list
    ) -> tuple[Atom | Equals, tuple[Atom | Equals, ...]]:
        head: Atom | Equals = items[0]
        body: tuple[Atom | Equals, ...] = tuple(items[1]) if len(items) > 1 else ()
        return (head, body)

    # --- Start rules ---

    def single_clause(
        self, items: list
    ) -> tuple[Atom | Equals, tuple[Atom | Equals, ...]]:
        return items[0]

    def single_query(self, items: list) -> tuple[Atom | Equals, ...]:
        """Returns a tuple of one or more goal literals."""
        return items[0]

    def file(
        self, items: list
    ) -> list[tuple[Atom | Equals, tuple[Atom | Equals, ...]]]:
        return list(items)


_transformer = _IRTransformer()

# Three parsers share the same grammar text and transformer; they differ only
# in their start rule.
_file_parser = Lark(
    _GRAMMAR_TEXT, parser="earley", start="file", ambiguity="resolve"
)
_clause_parser = Lark(
    _GRAMMAR_TEXT, parser="earley", start="single_clause", ambiguity="resolve"
)
_query_parser = Lark(
    _GRAMMAR_TEXT, parser="earley", start="single_query", ambiguity="resolve"
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _lark_error_msg(e: LarkError) -> str:
    """Build a user-friendly error message from a Lark exception."""
    line: int | None = None
    col: int | None = None
    if isinstance(e, UnexpectedToken):  # pragma: no cover  # Earley emits Unexpected{Characters,EOF}
        line, col = e.line, e.column
    elif isinstance(e, (UnexpectedCharacters, UnexpectedEOF)):
        line, col = e.line, e.column
    if line is not None and line >= 0:
        return f"parse error at line {line}, column {col}: {e}"
    return f"parse error: {e}"


def _head_pred(head: Atom | Equals) -> str:
    """Return the predicate key used for auto-generating clause names."""
    match head:
        case Atom(pred=p):
            return p
        case Equals():
            return "eq"


def _term_has_meta(t: Term) -> bool:
    match t:
        case Meta():
            return True
        case Func(args=args):
            return any(_term_has_meta(a) for a in args)
    return False


def _literal_has_meta(f: Atom | Equals) -> bool:
    match f:
        case Atom(args=args):
            return any(_term_has_meta(a) for a in args)
        case Equals(lhs=lhs, rhs=rhs):
            return _term_has_meta(lhs) or _term_has_meta(rhs)


def _rewrite_lname_consts_to_vars(t: Term) -> Term:
    """Recursively rewrite Const(str) → Var(str) inside a term.

    Used to convert the second argument of `root_of(target, poly)` so that
    bare lowercase identifiers in polynomial position (like `x` in
    `x^2 - 5*x + 6`) become Vars rather than Prolog constants. Numeric
    Consts (int, Fraction) are unchanged. Func args are recursed into.
    """
    match t:
        case Const(value=v) if isinstance(v, str):
            return Var(v)
        case Func(name=name, args=args):
            new_args = tuple(_rewrite_lname_consts_to_vars(a) for a in args)
            return Func(name, new_args) if new_args != args else t
        case _:
            return t


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_clause(source: str) -> Clause:
    """Parse a single clause definition.

    Raises ParseError if:
    - source is not a valid clause (syntax error, missing dot, etc.)
    - source contains metavariables (?X), which are only valid in queries
    """
    try:
        head, body = _transformer.transform(_clause_parser.parse(source))
    except LarkError as e:
        raise ParseError(_lark_error_msg(e)) from e
    if _literal_has_meta(head) or any(_literal_has_meta(b) for b in body):
        raise ParseError(
            "metavariables (?X) are not allowed in clause definitions"
        )
    return Clause(f"{_head_pred(head)}_1", head, body)


def parse_query(source: str) -> tuple[Atom | Equals, ...]:
    """Parse a single `?-` query, returning a tuple of one or more goals.

    M2 extension: queries may contain comma-separated goals like
    `?- prime(?P), ?P > 2.`. The result is a tuple of literals; single-goal
    queries return a one-element tuple for uniform handling. Metavariables
    are allowed in queries.
    Raises ParseError on invalid input.
    """
    try:
        return _transformer.transform(_query_parser.parse(source))
    except LarkError as e:
        raise ParseError(_lark_error_msg(e)) from e


def parse_kb(source: str) -> KnowledgeBase:
    """Parse a multi-clause source string into a KnowledgeBase.

    Comments (% ...) and whitespace are stripped by the lexer.
    Clause names are auto-generated as '<pred>_<n>' scoped per predicate:
    the first 'human' clause is 'human_1', the second is 'human_2', etc.

    An empty source produces an empty KnowledgeBase.
    Raises ParseError on any syntax error.
    """
    try:
        pairs = _transformer.transform(_file_parser.parse(source))
    except LarkError as e:
        raise ParseError(_lark_error_msg(e)) from e
    for head, body in pairs:
        if _literal_has_meta(head) or any(_literal_has_meta(b) for b in body):
            raise ParseError(
                "metavariables (?X) are not allowed in clause definitions"
            )
    pred_counts: dict[str, int] = {}
    clauses: list[Clause] = []
    for head, body in pairs:
        pred = _head_pred(head)
        pred_counts[pred] = pred_counts.get(pred, 0) + 1
        clauses.append(Clause(f"{pred}_{pred_counts[pred]}", head, body))
    return KnowledgeBase(tuple(clauses))


def parse_file(path: str | Path) -> KnowledgeBase:
    """Read a file and parse its contents as a KnowledgeBase.

    Raises OSError if the file cannot be read.
    Raises ParseError on syntax errors.
    """
    source = Path(path).read_text(encoding="utf-8")
    return parse_kb(source)
