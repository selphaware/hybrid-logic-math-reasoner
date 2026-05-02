from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


class Term:
    pass


@dataclass(frozen=True)
class Var(Term):
    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Const(Term):
    value: object

    def __repr__(self) -> str:
        return repr(self.value)


@dataclass(frozen=True)
class Func(Term):
    name: str
    args: tuple[Term, ...]

    def __repr__(self) -> str:
        if not self.args:
            return self.name
        args_repr = ", ".join(repr(a) for a in self.args)
        return f"{self.name}({args_repr})"


@dataclass(frozen=True)
class Meta(Term):
    """An unknown to be resolved by unification during SLD search.

    Metavariables exist only during search; the kernel never sees them in a
    valid proof. The renderer must apply the final substitution before
    kernel checking to produce a ground proof.

    By convention, names start with '?', e.g. '?X', '?Y'.
    """

    name: str


# ---------------------------------------------------------------------------
# Formulas
# ---------------------------------------------------------------------------


class Formula:
    pass


@dataclass(frozen=True)
class Atom(Formula):
    pred: str
    args: tuple[Term, ...] = ()

    def __repr__(self) -> str:
        if not self.args:
            return self.pred
        args_repr = ", ".join(repr(a) for a in self.args)
        return f"{self.pred}({args_repr})"


@dataclass(frozen=True)
class Equals(Formula):
    lhs: Term
    rhs: Term

    def __repr__(self) -> str:
        return f"({self.lhs!r} = {self.rhs!r})"


@dataclass(frozen=True)
class Not(Formula):
    body: Formula

    def __repr__(self) -> str:
        return f"~{self.body!r}"


@dataclass(frozen=True)
class And(Formula):
    left: Formula
    right: Formula

    def __repr__(self) -> str:
        return f"({self.left!r} & {self.right!r})"


@dataclass(frozen=True)
class Or(Formula):
    left: Formula
    right: Formula

    def __repr__(self) -> str:
        return f"({self.left!r} | {self.right!r})"


@dataclass(frozen=True)
class Implies(Formula):
    left: Formula
    right: Formula

    def __repr__(self) -> str:
        return f"({self.left!r} -> {self.right!r})"


@dataclass(frozen=True)
class Iff(Formula):
    left: Formula
    right: Formula

    def __repr__(self) -> str:
        return f"({self.left!r} <-> {self.right!r})"


@dataclass(frozen=True)
class Bot(Formula):
    def __repr__(self) -> str:
        return "_|_"


@dataclass(frozen=True)
class ForAll(Formula):
    var: str
    body: Formula

    def __repr__(self) -> str:
        return f"(forall {self.var}. {self.body!r})"


@dataclass(frozen=True)
class Exists(Formula):
    var: str
    body: Formula

    def __repr__(self) -> str:
        return f"(exists {self.var}. {self.body!r})"


# ---------------------------------------------------------------------------
# Free variables
# ---------------------------------------------------------------------------


def free_vars_term(t: Term) -> frozenset[str]:
    match t:
        case Var(name=n):
            return frozenset({n})
        case Const():
            return frozenset()
        case Func(args=args):
            result: frozenset[str] = frozenset()
            for a in args:
                result = result | free_vars_term(a)
            return result
        case Meta():
            return frozenset()
        case _:  # unreachable; Term hierarchy is closed
            raise TypeError(f"Unknown term type: {type(t)}")  # pragma: no cover


def free_vars(f: Formula) -> frozenset[str]:
    match f:
        case Atom(args=args):
            result: frozenset[str] = frozenset()
            for a in args:
                result = result | free_vars_term(a)
            return result
        case Equals(lhs=lhs, rhs=rhs):
            return free_vars_term(lhs) | free_vars_term(rhs)
        case Not(body=body):
            return free_vars(body)
        case And(left=left, right=right) | Or(left=left, right=right) | Implies(
            left=left, right=right
        ) | Iff(left=left, right=right):
            return free_vars(left) | free_vars(right)
        case Bot():
            return frozenset()
        case ForAll(var=var, body=body) | Exists(var=var, body=body):
            return free_vars(body) - {var}
        case _:  # unreachable; Formula hierarchy is closed
            raise TypeError(f"Unknown formula type: {type(f)}")  # pragma: no cover


# ---------------------------------------------------------------------------
# Capture-avoiding substitution
# ---------------------------------------------------------------------------

_fresh_counter: int = 0


def _fresh(base: str, avoid: frozenset[str]) -> str:
    global _fresh_counter
    candidate = f"{base}_{_fresh_counter}"
    _fresh_counter += 1
    while candidate in avoid:
        candidate = f"{base}_{_fresh_counter}"
        _fresh_counter += 1
    return candidate


def subst_term(t: Term, var: str, replacement: Term) -> Term:
    match t:
        case Var(name=n):
            return replacement if n == var else t
        case Const():
            return t
        case Func(name=name, args=args):
            new_args = tuple(subst_term(a, var, replacement) for a in args)
            if new_args == args:
                return t
            return Func(name, new_args)
        case Meta():
            return t  # logical-variable substitution is a no-op on Meta
        case _:  # unreachable; Term hierarchy is closed
            raise TypeError(f"Unknown term type: {type(t)}")  # pragma: no cover


def subst(f: Formula, var: str, replacement: Term) -> Formula:
    match f:
        case Atom(pred=pred, args=args):
            new_args = tuple(subst_term(a, var, replacement) for a in args)
            if new_args == args:
                return f
            return Atom(pred, new_args)
        case Equals(lhs=lhs, rhs=rhs):
            new_lhs = subst_term(lhs, var, replacement)
            new_rhs = subst_term(rhs, var, replacement)
            if new_lhs is lhs and new_rhs is rhs:
                return f
            return Equals(new_lhs, new_rhs)
        case Not(body=body):
            new_body = subst(body, var, replacement)
            return f if new_body is body else Not(new_body)
        case And(left=left, right=right):
            new_l, new_r = subst(left, var, replacement), subst(right, var, replacement)
            return f if (new_l is left and new_r is right) else And(new_l, new_r)
        case Or(left=left, right=right):
            new_l, new_r = subst(left, var, replacement), subst(right, var, replacement)
            return f if (new_l is left and new_r is right) else Or(new_l, new_r)
        case Implies(left=left, right=right):
            new_l, new_r = subst(left, var, replacement), subst(right, var, replacement)
            return f if (new_l is left and new_r is right) else Implies(new_l, new_r)
        case Iff(left=left, right=right):
            new_l, new_r = subst(left, var, replacement), subst(right, var, replacement)
            return f if (new_l is left and new_r is right) else Iff(new_l, new_r)
        case Bot():
            return f
        case ForAll(var=bvar, body=body) | Exists(var=bvar, body=body):
            # Bound variable shields: subst(forall x. P, "x", t) == forall x. P
            if bvar == var:
                return f
            # If var is not free in body, no substitution will occur — skip rename
            if var not in free_vars(body):
                return f
            repl_fvars = free_vars_term(replacement)
            if bvar in repl_fvars:
                # Renaming required to avoid capture
                all_vars = free_vars(f) | repl_fvars | {bvar, var}
                fresh = _fresh(bvar, all_vars)
                body = subst(body, bvar, Var(fresh))
                bvar = fresh
            new_body = subst(body, var, replacement)
            if isinstance(f, ForAll):
                return ForAll(bvar, new_body)
            else:
                return Exists(bvar, new_body)
        case _:  # unreachable; Formula hierarchy is closed
            raise TypeError(f"Unknown formula type: {type(f)}")  # pragma: no cover
