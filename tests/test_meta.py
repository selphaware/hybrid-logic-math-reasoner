"""Tests for Meta term type and formula.py extensions (M1 §5.1)."""

from __future__ import annotations

from hlmr.ir.formula import (
    Atom,
    Const,
    Term,
    Var,
    free_vars,
    free_vars_term,
    subst,
    subst_term,
)
from hlmr.ir.justification import Premise
from hlmr.ir.meta import Meta
from hlmr.ir.proof import Proof, ProofLine
from hlmr.ir.serialise import from_json, to_json

# ---------------------------------------------------------------------------
# Meta dataclass basics
# ---------------------------------------------------------------------------


def test_meta_frozen_dataclass() -> None:
    m = Meta("?X")
    assert m.name == "?X"


def test_meta_equality_by_name() -> None:
    assert Meta("?X") == Meta("?X")
    assert Meta("?X") != Meta("?Y")


def test_meta_hashable() -> None:
    s = {Meta("?X"), Meta("?X"), Meta("?Y")}
    assert len(s) == 2


def test_meta_is_term() -> None:
    assert isinstance(Meta("?X"), Term)


def test_meta_immutable() -> None:
    import dataclasses
    assert dataclasses.is_dataclass(Meta)
    m = Meta("?X")
    try:
        m.name = "?Y"  # type: ignore[misc]
        assert False, "expected FrozenInstanceError"
    except dataclasses.FrozenInstanceError:
        pass


# ---------------------------------------------------------------------------
# free_vars_term
# ---------------------------------------------------------------------------


def test_free_vars_term_meta_returns_empty() -> None:
    assert free_vars_term(Meta("?X")) == frozenset()


def test_free_vars_term_meta_not_confused_with_var() -> None:
    # Var contributes its name; Meta contributes nothing.
    assert free_vars_term(Var("X")) == frozenset({"X"})
    assert free_vars_term(Meta("?X")) == frozenset()


# ---------------------------------------------------------------------------
# subst_term
# ---------------------------------------------------------------------------


def test_subst_term_meta_unchanged() -> None:
    # Substituting a logical variable into a Meta is a no-op.
    assert subst_term(Meta("?X"), "y", Const("c")) == Meta("?X")


def test_subst_term_meta_unchanged_when_var_name_matches_meta_name() -> None:
    # Meta names start with '?' and are never logical variable targets, even
    # if the string happens to match the var argument.
    assert subst_term(Meta("?X"), "?X", Const("c")) == Meta("?X")


def test_subst_term_replacement_can_be_meta() -> None:
    # When the target term IS a Var and var matches, replacement (Meta) is returned.
    result = subst_term(Var("y"), "y", Meta("?X"))
    assert result == Meta("?X")


# ---------------------------------------------------------------------------
# Formulas containing Meta (via Atom args)
# ---------------------------------------------------------------------------


def test_subst_atom_meta_untouched_var_substituted() -> None:
    # Atom("p", (Meta("?X"), Var("y"))) with subst("y", Const("c"))
    atom = Atom("p", (Meta("?X"), Var("y")))
    result = subst(atom, "y", Const("c"))
    assert result == Atom("p", (Meta("?X"), Const("c")))


def test_free_vars_atom_with_meta_only() -> None:
    # Meta contributes nothing; the Atom has no free logical variables.
    atom = Atom("p", (Meta("?X"),))
    assert free_vars(atom) == frozenset()


def test_free_vars_atom_mixed_meta_and_var() -> None:
    atom = Atom("p", (Meta("?X"), Var("y"), Var("z")))
    assert free_vars(atom) == frozenset({"y", "z"})


def test_subst_does_not_substitute_into_meta_name() -> None:
    # Substituting the logical variable "X" should not affect Meta("?X").
    atom = Atom("p", (Meta("?X"), Var("X")))
    result = subst(atom, "X", Const(1))
    assert result == Atom("p", (Meta("?X"), Const(1)))


# ---------------------------------------------------------------------------
# JSON round-trip (serialise.py extended to handle Meta)
# Schema version unchanged — adding Meta is backward-compatible.
# ---------------------------------------------------------------------------


def test_meta_term_to_dict_and_back() -> None:
    # A proof whose formula contains a Meta arg round-trips through JSON.
    atom_with_meta = Atom("p", (Meta("?X"),))
    proof = Proof(lines=(ProofLine(1, atom_with_meta, Premise(), 0),))
    restored = from_json(to_json(proof))
    assert restored == proof


def test_meta_round_trip_preserves_name() -> None:
    atom = Atom("mortal", (Meta("?Who"),))
    proof = Proof(lines=(ProofLine(1, atom, Premise(), 0),))
    restored_atom = from_json(to_json(proof)).lines[0].formula
    assert restored_atom == atom
    assert isinstance(restored_atom, Atom)
    assert restored_atom.args[0] == Meta("?Who")


def test_meta_schema_version_unchanged() -> None:
    from hlmr.ir.serialise import SCHEMA_VERSION
    assert SCHEMA_VERSION == 1
