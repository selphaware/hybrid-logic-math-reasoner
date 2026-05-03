from __future__ import annotations

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.unify.substitution import Substitution


def _walk(t: Term, s: Substitution) -> Term:
    """Chase Meta bindings in s until we reach an unbound Meta or non-Meta."""
    while isinstance(t, Meta) and t.name in s:
        t = s[t.name]
    return t


def _occurs(name: str, t: Term, s: Substitution) -> bool:
    """True if Meta(name) appears anywhere in the fully-walked tree of t."""
    t = _walk(t, s)
    match t:
        case Meta(name=n):
            return n == name
        case Var() | Const():
            return False
        case Func(args=args):
            return any(_occurs(name, a, s) for a in args)
        case _:
            return False  # pragma: no cover


def _bind(name: str, t: Term, s: Substitution) -> Substitution | None:
    """Extend s with name → t, or None if the binding would create a cycle."""
    if _occurs(name, t, s):
        return None
    return {**s, name: t}


def unify(
    t1: Term, t2: Term, s: Substitution | None = None
) -> Substitution | None:
    """Robinson first-order unification with occurs check.

    Returns an extended substitution on success, or None if t1 and t2
    cannot be unified under s.  The optional s argument lets callers
    thread an existing substitution through multiple unification steps
    (e.g. unifying each argument pair of two atoms in sequence).

    Var is not a substitution target: two distinct Vars never unify.
    Meta is the only binding target; Var can appear as a binding value.
    """
    if s is None:
        s = {}

    t1 = _walk(t1, s)
    t2 = _walk(t2, s)

    if t1 == t2:
        return s

    if isinstance(t1, Meta):
        return _bind(t1.name, t2, s)
    if isinstance(t2, Meta):
        return _bind(t2.name, t1, s)

    if isinstance(t1, Func) and isinstance(t2, Func):
        if t1.name != t2.name or len(t1.args) != len(t2.args):
            return None
        for a1, a2 in zip(t1.args, t2.args):
            s = unify(a1, a2, s)
            if s is None:
                return None
        return s

    return None


def unify_atoms(
    a1: Atom | Equals,
    a2: Atom | Equals,
    s: Substitution | None = None,
) -> Substitution | None:
    """Unify two atomic formulas.

    Atoms unify when they share the same predicate symbol and arity and
    their arguments pairwise unify (threading s through).  Equals counts
    as its own predicate distinct from any Atom predicate.  Atom vs
    Equals always returns None.
    """
    if s is None:
        s = {}
    match (a1, a2):
        case (Atom(pred=p1, args=args1), Atom(pred=p2, args=args2)):
            if p1 != p2 or len(args1) != len(args2):
                return None
            for t1, t2 in zip(args1, args2):
                s = unify(t1, t2, s)
                if s is None:
                    return None
            return s
        case (Equals(lhs=l1, rhs=r1), Equals(lhs=l2, rhs=r2)):
            s = unify(l1, l2, s)
            if s is None:
                return None
            return unify(r1, r2, s)
        case _:
            return None
