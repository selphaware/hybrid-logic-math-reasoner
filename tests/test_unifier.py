"""Tests for hlmr.unify.unifier (M1 §7.2-7.3).

apply_to_term from substitution.py is intentionally one-pass.  When the
unifier builds a chain (?X → Meta(?Y), ?Y → Const(a)), a single
apply_to_term call only resolves one level.  The Hypothesis property
test therefore uses a local _saturate helper that iterates apply_to_term
until stable, giving the semantics "apply the fully-resolved
substitution".  All non-Hypothesis unit tests are written to avoid chains
by design so they can use apply_to_term directly.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Term, Var
from hlmr.unify.substitution import Substitution, apply_to_term
from hlmr.unify.unifier import _bind, _occurs, _walk, unify, unify_atoms


# ---------------------------------------------------------------------------
# Local helper — fully resolve a substitution (Hypothesis tests only)
# ---------------------------------------------------------------------------


def _saturate(s: Substitution, max_iter: int = 30) -> Substitution:
    """Apply s to all its own values until stable.

    Convergence is guaranteed by the occurs check (no cycles), so
    max_iter is a safety bound only.
    """
    for _ in range(max_iter):
        s_new = {k: apply_to_term(s, v) for k, v in s.items()}
        if s_new == s:
            return s
        s = s_new
    return s  # pragma: no cover


# ---------------------------------------------------------------------------
# _walk
# ---------------------------------------------------------------------------


def test_walk_unbound_meta_returns_same_object() -> None:
    m = Meta("?X")
    assert _walk(m, {}) is m


def test_walk_bound_meta_one_step() -> None:
    assert _walk(Meta("?X"), {"?X": Const("a")}) == Const("a")


def test_walk_meta_chain() -> None:
    # ?X → Meta(?Y), ?Y → Const("a")
    s: Substitution = {"?X": Meta("?Y"), "?Y": Const("a")}
    assert _walk(Meta("?X"), s) == Const("a")


def test_walk_var_unchanged() -> None:
    v = Var("x")
    assert _walk(v, {"?X": Const("a")}) is v


def test_walk_const_unchanged() -> None:
    c = Const(42)
    assert _walk(c, {"?X": Const("a")}) is c


def test_walk_func_unchanged() -> None:
    f = Func("g", (Meta("?X"),))
    # _walk only chases top-level Meta; does not descend into Func args
    assert _walk(f, {"?X": Const("a")}) is f


# ---------------------------------------------------------------------------
# _occurs
# ---------------------------------------------------------------------------


def test_occurs_meta_in_func_arg() -> None:
    assert _occurs("?X", Func("f", (Meta("?X"),)), {}) is True


def test_occurs_meta_in_nested_func() -> None:
    assert _occurs("?X", Func("f", (Func("g", (Meta("?X"),)),)), {}) is True


def test_occurs_meta_not_present() -> None:
    assert _occurs("?X", Func("f", (Meta("?Y"),)), {}) is False


def test_occurs_const_false() -> None:
    assert _occurs("?X", Const("a"), {}) is False


def test_occurs_var_false() -> None:
    assert _occurs("?X", Var("x"), {}) is False


def test_occurs_via_binding_in_s() -> None:
    # ?Y is bound to Func(f, (Meta(?X),)); occurs checks via _walk
    s: Substitution = {"?Y": Func("f", (Meta("?X"),))}
    assert _occurs("?X", Meta("?Y"), s) is True


def test_occurs_meta_unbound_different_name() -> None:
    assert _occurs("?X", Meta("?Z"), {}) is False


# ---------------------------------------------------------------------------
# _bind
# ---------------------------------------------------------------------------


def test_bind_no_cycle() -> None:
    result = _bind("?X", Const("a"), {})
    assert result == {"?X": Const("a")}


def test_bind_cycle_returns_none() -> None:
    # Binding ?X → Func(f, Meta(?X)) would create a cycle
    assert _bind("?X", Func("f", (Meta("?X"),)), {}) is None


# ---------------------------------------------------------------------------
# unify — ground terms (Const, Var)
# ---------------------------------------------------------------------------


def test_unify_equal_consts() -> None:
    assert unify(Const("a"), Const("a")) == {}


def test_unify_unequal_consts() -> None:
    assert unify(Const("a"), Const("b")) is None


def test_unify_equal_vars() -> None:
    assert unify(Var("x"), Var("x")) == {}


def test_unify_unequal_vars() -> None:
    assert unify(Var("x"), Var("y")) is None


def test_unify_var_vs_const() -> None:
    assert unify(Var("x"), Const("a")) is None


def test_unify_const_vs_var() -> None:
    assert unify(Const("a"), Var("x")) is None


# ---------------------------------------------------------------------------
# unify — Meta binding
# ---------------------------------------------------------------------------


def test_unify_meta_with_const() -> None:
    assert unify(Meta("?X"), Const("a")) == {"?X": Const("a")}


def test_unify_const_with_meta() -> None:
    # Symmetric: Const on the left
    assert unify(Const("a"), Meta("?X")) == {"?X": Const("a")}


def test_unify_meta_with_var() -> None:
    # Meta is the substitution target; Var is a valid binding value.
    assert unify(Meta("?X"), Var("y")) == {"?X": Var("y")}


def test_unify_var_with_meta() -> None:
    # Symmetric
    assert unify(Var("y"), Meta("?X")) == {"?X": Var("y")}


def test_unify_meta_with_itself() -> None:
    # ?X unified with ?X → substitution unchanged
    assert unify(Meta("?X"), Meta("?X")) == {}


def test_unify_two_distinct_metas() -> None:
    # Both unbound → bind the first to the second
    result = unify(Meta("?X"), Meta("?Y"))
    assert result == {"?X": Meta("?Y")}


def test_unify_meta_with_func() -> None:
    t = Func("f", (Const("a"),))
    assert unify(Meta("?X"), t) == {"?X": t}


# ---------------------------------------------------------------------------
# unify — occurs check (soundness, mandatory)
# ---------------------------------------------------------------------------


def test_unify_occurs_check_meta_in_func() -> None:
    # ?X unified with f(?X) must fail — occurs check
    assert unify(Meta("?X"), Func("f", (Meta("?X"),))) is None


def test_unify_occurs_check_meta_in_nested_func() -> None:
    assert unify(Meta("?X"), Func("f", (Func("g", (Meta("?X"),)),))) is None


def test_unify_occurs_check_via_existing_binding() -> None:
    # s already maps ?Y → Func(f, ?X); unifying ?X with ?Y should fail
    s: Substitution = {"?Y": Func("f", (Meta("?X"),))}
    assert unify(Meta("?X"), Meta("?Y"), s) is None


# ---------------------------------------------------------------------------
# unify — Func cases
# ---------------------------------------------------------------------------


def test_unify_func_name_mismatch() -> None:
    assert unify(Func("f", (Const("a"),)), Func("g", (Const("a"),))) is None


def test_unify_func_arity_mismatch() -> None:
    assert unify(Func("f", (Const("a"), Const("b"))), Func("f", (Const("a"),))) is None


def test_unify_func_args_unify() -> None:
    # f(?X, a) with f(b, ?Y) → {?X: b, ?Y: a}
    t1 = Func("f", (Meta("?X"), Const("a")))
    t2 = Func("f", (Const("b"), Meta("?Y")))
    result = unify(t1, t2)
    assert result == {"?X": Const("b"), "?Y": Const("a")}


def test_unify_func_same_meta_twice_different_consts() -> None:
    # f(?X, ?X) with f(a, b) — ?X must be both a and b → None
    t1 = Func("f", (Meta("?X"), Meta("?X")))
    t2 = Func("f", (Const("a"), Const("b")))
    assert unify(t1, t2) is None


def test_unify_func_same_meta_twice_same_const() -> None:
    # f(?X, ?X) with f(a, a) → {?X: a}
    t1 = Func("f", (Meta("?X"), Meta("?X")))
    t2 = Func("f", (Const("a"), Const("a")))
    assert unify(t1, t2) == {"?X": Const("a")}


def test_unify_func_nested_args() -> None:
    # f(g(?X)) with f(g(a)) → {?X: a}
    t1 = Func("f", (Func("g", (Meta("?X"),)),))
    t2 = Func("f", (Func("g", (Const("a"),)),))
    assert unify(t1, t2) == {"?X": Const("a")}


def test_unify_nullary_funcs_equal() -> None:
    assert unify(Func("c", ()), Func("c", ())) == {}


def test_unify_nullary_funcs_different() -> None:
    assert unify(Func("c", ()), Func("d", ())) is None


# ---------------------------------------------------------------------------
# unify — threading s (multi-step accumulation)
# ---------------------------------------------------------------------------


def test_unify_extends_existing_s() -> None:
    s: Substitution = {"?Y": Const("b")}
    result = unify(Meta("?X"), Const("a"), s)
    assert result == {"?Y": Const("b"), "?X": Const("a")}


def test_unify_threads_s_through_func_args() -> None:
    # Bind ?X → f(?Y) in step 1; then unify ?X with f(a) — should
    # resolve ?X to f(?Y), then unify f(?Y) with f(a) → ?Y → a.
    s1 = unify(Meta("?X"), Func("f", (Meta("?Y"),)))
    assert s1 == {"?X": Func("f", (Meta("?Y"),))}

    s2 = unify(Meta("?X"), Func("f", (Const("a"),)), s1)
    assert s2 is not None
    assert s2.get("?Y") == Const("a")


def test_unify_already_bound_meta_consistent() -> None:
    # s = {?X: Const(a)}; unifying ?X with Const(a) again is consistent
    s: Substitution = {"?X": Const("a")}
    assert unify(Meta("?X"), Const("a"), s) == {"?X": Const("a")}


def test_unify_already_bound_meta_conflict() -> None:
    # s = {?X: Const(a)}; unifying ?X with Const(b) conflicts → None
    s: Substitution = {"?X": Const("a")}
    assert unify(Meta("?X"), Const("b"), s) is None


# ---------------------------------------------------------------------------
# unify — mixed types → None
# ---------------------------------------------------------------------------


def test_unify_func_vs_const() -> None:
    assert unify(Func("f", ()), Const("f")) is None


def test_unify_const_vs_func() -> None:
    assert unify(Const("f"), Func("f", ())) is None


def test_unify_var_vs_func() -> None:
    assert unify(Var("x"), Func("f", ())) is None


# ---------------------------------------------------------------------------
# unify_atoms
# ---------------------------------------------------------------------------


def test_unify_atoms_same_nullary_atom() -> None:
    assert unify_atoms(Atom("p"), Atom("p")) == {}


def test_unify_atoms_different_pred() -> None:
    assert unify_atoms(Atom("p", (Var("x"),)), Atom("q", (Var("x"),))) is None


def test_unify_atoms_same_pred_args_unify() -> None:
    result = unify_atoms(
        Atom("parent", (Meta("?X"), Var("y"))),
        Atom("parent", (Const("alice"), Var("y"))),
    )
    assert result == {"?X": Const("alice")}


def test_unify_atoms_arity_mismatch() -> None:
    a1 = Atom("p", (Const("a"), Const("b")))
    a2 = Atom("p", (Const("a"),))
    assert unify_atoms(a1, a2) is None


def test_unify_atoms_equals_with_equals() -> None:
    result = unify_atoms(
        Equals(Meta("?X"), Var("y")),
        Equals(Const("a"), Var("y")),
    )
    assert result == {"?X": Const("a")}


def test_unify_atoms_equals_lhs_and_rhs() -> None:
    result = unify_atoms(
        Equals(Meta("?X"), Meta("?Y")),
        Equals(Const("a"), Const("b")),
    )
    assert result == {"?X": Const("a"), "?Y": Const("b")}


def test_unify_atoms_atom_vs_equals() -> None:
    assert unify_atoms(Atom("p", (Var("x"),)), Equals(Var("x"), Const("a"))) is None


def test_unify_atoms_equals_vs_atom() -> None:
    assert unify_atoms(Equals(Var("x"), Var("y")), Atom("eq", (Var("x"), Var("y")))) is None


def test_unify_atoms_threads_s() -> None:
    s: Substitution = {"?Y": Const("b")}
    result = unify_atoms(
        Atom("p", (Meta("?X"),)),
        Atom("p", (Const("a"),)),
        s,
    )
    assert result == {"?Y": Const("b"), "?X": Const("a")}


# ---------------------------------------------------------------------------
# Hypothesis property: soundness of unification
# ---------------------------------------------------------------------------

_var_names = st.sampled_from(["x", "y", "z"])
_const_vals: st.SearchStrategy[int | str] = st.sampled_from([0, 1, "a", "b"])
_meta_names = st.sampled_from(["?X", "?Y", "?Z"])


@st.composite
def _small_terms(draw: st.DrawFn, depth: int = 2) -> Term:
    """Random Term with a limited alphabet to maximise interesting interactions."""
    leaf = st.one_of(
        _var_names.map(Var),
        _const_vals.map(Const),
        _meta_names.map(Meta),
    )
    if depth == 0:
        return draw(leaf)
    return draw(st.one_of(
        leaf,
        st.builds(
            Func,
            name=st.sampled_from(["f", "g"]),
            args=st.one_of(
                st.just(()),
                st.tuples(_small_terms(depth=depth - 1)),
                st.tuples(_small_terms(depth=depth - 1), _small_terms(depth=depth - 1)),
            ),
        ),
    ))


@given(t1=_small_terms(), t2=_small_terms())
@settings(max_examples=500)
def test_hypothesis_unify_soundness(t1: Term, t2: Term) -> None:
    """If unify(t1, t2) succeeds, the result makes t1 and t2 equal after
    full substitution application.  _saturate gives a fully-resolved
    substitution so that one-pass chains are handled correctly."""
    result = unify(t1, t2)
    if result is not None:
        sat = _saturate(result)
        assert apply_to_term(sat, t1) == apply_to_term(sat, t2)
