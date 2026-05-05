"""Adversarial tests for the unifier and substitution machinery.

Three groups:
  1. Deep occurs check: unify(?X, f(f(...?X...))) at various depths returns None.
  2. Capture-avoidance with adversarial Meta/Var names: distinct names stay distinct.
  3. Substitution composition associativity on closed terms.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.ir.formula import Const, Func, Meta, Var
from hlmr.unify.substitution import Substitution, apply_to_term, compose
from hlmr.unify.unifier import unify


def _wrap_in_func(t: object, depth: int) -> object:
    """Wrap term t in depth layers of f(...)."""
    for _ in range(depth):
        t = Func("f", (t,))
    return t


class TestOccursCheck:
    """unify(?X, t) returns None whenever ?X appears structurally inside t."""

    @pytest.mark.parametrize("depth", [1, 5, 50, 100])
    def test_occurs_check_depth(self, depth: int) -> None:
        # Note: _occurs is recursive; depth>~500 hits Python's call-stack limit.
        # 100 is deep enough to verify the algorithm without system constraints.
        x = Meta("?X")
        nested = _wrap_in_func(x, depth)
        result = unify(x, nested, {})
        assert result is None, f"occurs check should fail at depth {depth}"

    def test_occurs_check_in_func_arg(self) -> None:
        x = Meta("?X")
        t = Func("g", (Const("a"), Func("f", (x,))))
        assert unify(x, t, {}) is None

    def test_no_occurs_check_needed_for_ground(self) -> None:
        x = Meta("?X")
        t = Func("f", (Const("a"),))
        result = unify(x, t, {})
        assert result is not None
        assert result["?X"] == t


class TestCaptureAvoidance:
    """Variables named X, X_1, X_renamed, ?X remain distinct under unification."""

    def test_var_and_meta_are_distinct(self) -> None:
        # Var("X") and Meta("?X") are different IR nodes
        assert Var("X") != Meta("?X")

    def test_meta_names_with_suffixes_distinct(self) -> None:
        assert Meta("?X") != Meta("?X_1")
        assert Meta("?X_1") != Meta("?X_2")

    def test_unify_two_metas_distinct(self) -> None:
        # Unifying ?X with ?Y gives a subst where only one maps to the other
        s = unify(Meta("?X"), Meta("?Y"), {})
        assert s is not None
        # One of them maps to the other; they are not collapsed
        assert "?X" in s or "?Y" in s
        if "?X" in s:
            assert s["?X"] == Meta("?Y") or s.get("?Y") == Meta("?X")

    def test_similar_names_stay_distinct_after_apply(self) -> None:
        # ?X_1 and ?X_2 must remain separate through compose
        s1: Substitution = {"?X_1": Const("a")}
        s2: Substitution = {"?X_2": Const("b")}
        composed = compose(s1, s2)
        assert apply_to_term(composed, Meta("?X_1")) == Const("a")
        assert apply_to_term(composed, Meta("?X_2")) == Const("b")

    def test_adversarial_names_ground(self) -> None:
        names = ["?X", "?X_1", "?X_renamed", "?Xtra"]
        consts = [Const(f"c{i}") for i in range(len(names))]
        s: Substitution = dict(zip(names, consts))
        for name, expected in zip(names, consts):
            assert apply_to_term(s, Meta(name)) == expected


# ---------------------------------------------------------------------------
# Hypothesis generators for closed terms (no Metas)
# ---------------------------------------------------------------------------

_CONST_NAMES = ["a", "b", "c", "0", "1"]
_FUNC_NAMES = ["f", "g"]
_META_NAMES = ["?X", "?Y", "?Z"]


def _small_term_st(max_depth: int = 2):
    return st.recursive(
        st.one_of(
            st.sampled_from([Const(v) for v in _CONST_NAMES]),
            st.sampled_from([Meta(n) for n in _META_NAMES]),
        ),
        lambda children: st.one_of(
            st.builds(lambda n, args: Func(n, tuple(args)),
                      st.sampled_from(_FUNC_NAMES),
                      st.lists(children, min_size=1, max_size=2)),
        ),
        max_leaves=max_depth * 4,
    )


def _small_ground_term_st(max_depth: int = 2):
    return st.recursive(
        st.sampled_from([Const(v) for v in _CONST_NAMES]),
        lambda children: st.builds(
            lambda n, args: Func(n, tuple(args)),
            st.sampled_from(_FUNC_NAMES),
            st.lists(children, min_size=1, max_size=2),
        ),
        max_leaves=max_depth * 4,
    )


def _small_subst_st():
    return st.fixed_dictionaries(
        {n: _small_ground_term_st() for n in _META_NAMES[:2]}
    )


class TestSubstitutionCompositionAssociativity:
    """apply(compose(s1, compose(s2, s3)), t) == apply(compose(compose(s1, s2), s3), t)."""

    @given(
        s1=_small_subst_st(),
        s2=_small_subst_st(),
        s3=_small_subst_st(),
        t=_small_term_st(),
    )
    @settings(max_examples=300)
    def test_compose_associative(
        self,
        s1: Substitution,
        s2: Substitution,
        s3: Substitution,
        t,
    ) -> None:
        lhs = apply_to_term(compose(s1, compose(s2, s3)), t)
        rhs = apply_to_term(compose(compose(s1, s2), s3), t)
        assert lhs == rhs

    @given(s=_small_subst_st(), t=_small_term_st())
    @settings(max_examples=200)
    def test_apply_compose_is_sequential(self, s: Substitution, t) -> None:
        # apply(compose(s, {}), t) == apply(s, t)
        assert apply_to_term(compose(s, {}), t) == apply_to_term(s, t)
        # apply(compose({}, s), t) == apply(s, t)  (one pass only)
        assert apply_to_term(compose({}, s), t) == apply_to_term(s, t)
