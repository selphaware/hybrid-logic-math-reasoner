from __future__ import annotations

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Formula,
    Func,
    Iff,
    Implies,
    Meta,
    Not,
    Or,
    Term,
    Var,
)

# Keys are Meta names by convention (e.g. "?X", "?Y").
# Values are arbitrary Terms, which may themselves contain Metas.
# apply_to_term performs ONE pass — it does not chase chains of Metas.
Substitution = dict[str, Term]


def apply_to_term(s: Substitution, t: Term) -> Term:
    """Replace Meta(name) with s[name] wherever it appears in t (one pass).

    Recurses into Func args. Does NOT follow chains: if
    s = {"?X": Meta("?Y"), "?Y": Const("a")}, then
    apply_to_term(s, Meta("?X")) returns Meta("?Y"), not Const("a").
    Recursive resolution is the unifier's responsibility.

    Var and Const are returned unchanged; they are not substitution targets.
    """
    if not s:
        return t
    match t:
        case Meta(name=name):
            return s.get(name, t)
        case Var() | Const():
            return t
        case Func(name=name, args=args):
            new_args = tuple(apply_to_term(s, a) for a in args)
            if new_args == args:
                return t
            return Func(name, new_args)
        case _:  # unreachable; Term hierarchy is closed
            raise TypeError(f"Unknown term type: {type(t)}")  # pragma: no cover


def apply_to_formula(s: Substitution, f: Formula) -> Formula:
    """Apply substitution s to every Term inside formula f.

    Recurses through the full formula structure. Bound variable names in
    ForAll/Exists (str fields) are not affected — Meta is the only target.
    """
    if not s:
        return f
    match f:
        case Atom(pred=pred, args=args):
            new_args = tuple(apply_to_term(s, a) for a in args)
            if new_args == args:
                return f
            return Atom(pred, new_args)
        case Equals(lhs=lhs, rhs=rhs):
            new_lhs = apply_to_term(s, lhs)
            new_rhs = apply_to_term(s, rhs)
            if new_lhs is lhs and new_rhs is rhs:
                return f
            return Equals(new_lhs, new_rhs)
        case Not(body=body):
            new_body = apply_to_formula(s, body)
            return f if new_body is body else Not(new_body)
        case And(left=left, right=right):
            new_l = apply_to_formula(s, left)
            new_r = apply_to_formula(s, right)
            return f if (new_l is left and new_r is right) else And(new_l, new_r)
        case Or(left=left, right=right):
            new_l = apply_to_formula(s, left)
            new_r = apply_to_formula(s, right)
            return f if (new_l is left and new_r is right) else Or(new_l, new_r)
        case Implies(left=left, right=right):
            new_l = apply_to_formula(s, left)
            new_r = apply_to_formula(s, right)
            return f if (new_l is left and new_r is right) else Implies(new_l, new_r)
        case Iff(left=left, right=right):
            new_l = apply_to_formula(s, left)
            new_r = apply_to_formula(s, right)
            return f if (new_l is left and new_r is right) else Iff(new_l, new_r)
        case Bot():
            return f
        case ForAll(var=var, body=body):
            new_body = apply_to_formula(s, body)
            return f if new_body is body else ForAll(var, new_body)
        case Exists(var=var, body=body):
            new_body = apply_to_formula(s, body)
            return f if new_body is body else Exists(var, new_body)
        case _:  # unreachable; Formula hierarchy is closed
            raise TypeError(f"Unknown formula type: {type(f)}")  # pragma: no cover


def compose(s1: Substitution, s2: Substitution) -> Substitution:
    """Compose two substitutions; s2 is applied first.

    The result satisfies:
        apply_to_term(compose(s1, s2), t) == apply_to_term(s1, apply_to_term(s2, t))

    Worked example::

        s1 = {"?X": Const("a")}
        s2 = {"?Y": Meta("?X")}
        compose(s1, s2) = {"?Y": Const("a"), "?X": Const("a")}

    Because apply(s2, Meta("?Y")) = Meta("?X"), then apply(s1, Meta("?X")) = Const("a").
    s1's own entry for "?X" is preserved because it is not shadowed by s2.
    """
    result: Substitution = {k: apply_to_term(s1, v) for k, v in s2.items()}
    for k, v in s1.items():
        if k not in result:
            result[k] = v
    return result
