from __future__ import annotations

from dataclasses import dataclass

from hlmr.ir.formula import Atom, Equals


def _head_key(f: Atom | Equals) -> str:
    """Return the predicate key for a clause head or goal.

    Returns ``atom.pred`` for an Atom and ``"="`` for an Equals.
    Used as a cheap pre-filter in KnowledgeBase.matching(); full
    unification happens later in the solver.
    """
    match f:
        case Atom(pred=pred):
            return pred
        case Equals():
            return "="


@dataclass(frozen=True)
class Clause:
    """A definite Horn clause: head :- body_1, ..., body_n.

    A fact is a clause with an empty body. The head and each body
    literal are positive literals (Atom or Equals). Variables in the
    clause are universally quantified at the clause level; every use of
    a clause must rename its variables apart to prevent variable capture
    during unification.
    """

    name: str
    head: Atom | Equals
    body: tuple[Atom | Equals, ...] = ()


@dataclass(frozen=True)
class KnowledgeBase:
    """An ordered collection of Horn clauses.

    JSON serialisation of the KB is deferred to M2+. In M1 the KB is
    persisted as a ``.pl`` source file (the parser's job); there is no
    KB-as-JSON format.
    """

    clauses: tuple[Clause, ...]

    def matching(self, goal: Atom | Equals) -> tuple[Clause, ...]:
        """Return clauses whose head's predicate key matches the goal's.

        This is a cheap pre-filter that compares predicate symbols only
        (``atom.pred`` for Atom, ``"="`` for Equals). Full unification
        happens later. Clause order from the KB is preserved, which
        determines the order candidates are shown in the REPL.
        """
        key = _head_key(goal)
        return tuple(c for c in self.clauses if _head_key(c.head) == key)
