"""M2 renderer extension tests per RENDER_M2_DESIGN.md §10.

Covers:
  A. DispatcherResolvedStep → arithEval / eqRefl line shapes
  B. Mixed ClauseResolvedStep + DispatcherResolvedStep (prime demo)
  C. Multi-goal andI-chain invariants
  D. eqRefl vs arithEval policy (§4.4)
  E. Soundness backstops (malicious-renderer kernel rejection)
  F. Hypothesis property test: rendered proofs kernel-verified
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from hlmr.dispatch import RouteTarget
from hlmr.ir.formula import And, Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.justification import RuleApp
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof, ProofLine
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import (
    CheckFailure,
    EvaluationFalse,
    MalformedArithmetic,
    UnresolvedMeta,
    Verified,
)
from hlmr.solve import manual_solve
from hlmr.solve.render import RenderError, _choose_equality_rule, _saturate, render
from hlmr.solve.sld import ClauseResolvedStep, DispatcherResolvedStep, SLDState
from hlmr.solvers import SymPyFiniteRoots, Z3Sat, Z3Unsat


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _make_dispatcher_step(
    ground_atom: Atom | Equals,
    goal_resolved: Atom | Equals | None = None,
    binding: dict | None = None,
) -> DispatcherResolvedStep:
    return DispatcherResolvedStep(
        goal_resolved=goal_resolved or ground_atom,
        ground_atom=ground_atom,
        route=RouteTarget.Z3,
        binding_added=binding or {},
        solver_summary="test",
    )


def _state_from_steps(*steps, subst=None) -> SLDState:
    return SLDState(goals=(), subst=subst or {}, history=tuple(steps))


def _rendered_rule_names(proof: Proof) -> list[str]:
    names = []
    from hlmr.ir.justification import Premise
    for line in proof.lines:
        j = line.justification
        if isinstance(j, Premise):
            names.append("Premise")
        elif isinstance(j, RuleApp):
            names.append(j.rule)
    return names


_M2_ALPHABET = {"Premise", "forallE", "andI", "impE", "arithEval", "eqRefl"}


# ---------------------------------------------------------------------------
# A. DispatcherResolvedStep emission — basic shapes
# ---------------------------------------------------------------------------


class TestDispatcherStepEmission:
    def _render_single(
        self, ground_atom: Atom | Equals
    ) -> tuple[Proof, str]:
        step = _make_dispatcher_step(ground_atom)
        state = _state_from_steps(step)
        proof = render(state, KnowledgeBase(clauses=()), ground_atom)
        rule = proof.lines[0].justification.rule  # type: ignore[union-attr]
        return proof, rule

    def test_gt_atom_arith_eval(self):
        """Atom(">", (5, 2)) → arithEval line."""
        atom = Atom(">", (Const(5), Const(2)))
        proof, rule = self._render_single(atom)
        assert rule == "arithEval"
        assert isinstance(check_proof(proof), Verified)

    def test_lt_atom_arith_eval(self):
        """Atom("<", (2, 5)) → arithEval line."""
        atom = Atom("<", (Const(2), Const(5)))
        proof, rule = self._render_single(atom)
        assert rule == "arithEval"
        assert isinstance(check_proof(proof), Verified)

    def test_plus_ternary_arith_eval(self):
        """Atom("plus", (2, 3, 5)) → arithEval line."""
        atom = Atom("plus", (Const(2), Const(3), Const(5)))
        proof, rule = self._render_single(atom)
        assert rule == "arithEval"
        assert isinstance(check_proof(proof), Verified)

    def test_equals_non_reflexive_arith_eval(self):
        """Equals(2+3, 5) → arithEval (sides syntactically differ)."""
        atom = Equals(Func("+", (Const(2), Const(3))), Const(5))
        proof, rule = self._render_single(atom)
        assert rule == "arithEval"
        assert isinstance(check_proof(proof), Verified)

    def test_equals_reflexive_eq_refl(self):
        """Equals(7, 7) → eqRefl (syntactically identical sides)."""
        atom = Equals(Const(7), Const(7))
        proof, rule = self._render_single(atom)
        assert rule == "eqRefl"
        assert isinstance(check_proof(proof), Verified)

    def test_equals_fraction_reflexive_eq_refl(self):
        """Equals(Fraction(1,2), Fraction(1,2)) → eqRefl."""
        half = Const(Fraction(1, 2))
        atom = Equals(half, half)
        proof, rule = self._render_single(atom)
        assert rule == "eqRefl"
        assert isinstance(check_proof(proof), Verified)

    def test_depth_zero_invariant(self):
        """Every emitted line has box_depth == 0 (RENDER §10)."""
        atom = Atom(">", (Const(3), Const(1)))
        step = _make_dispatcher_step(atom)
        state = _state_from_steps(step)
        proof = render(state, KnowledgeBase(clauses=()), atom)
        assert all(line.box_depth == 0 for line in proof.lines)

    def test_no_line_refs_on_arith_eval(self):
        """arithEval lines carry no line or box refs (zero-premise rule)."""
        atom = Atom("!=", (Const(3), Const(4)))
        proof, rule = self._render_single(atom)
        j = proof.lines[0].justification
        assert isinstance(j, RuleApp)
        assert j.line_refs == ()
        assert j.box_refs == ()
        assert j.extra == {}


# ---------------------------------------------------------------------------
# B. Mixed-shape rendering — ClauseResolvedStep + DispatcherResolvedStep
# ---------------------------------------------------------------------------


class TestMixedRendering:
    """Tests mirroring the §2 prime demo and quadratic demo."""

    def _prime_demo_state(self, prime_val: int = 5) -> tuple[SLDState, Clause]:
        """Build the SLDState for a prime demo pick."""
        prime_clause = Clause(
            f"prime_{prime_val}",
            Atom("prime", (Const(prime_val),)),
            (),
        )
        kb_step = ClauseResolvedStep(
            goal_resolved=Atom("prime", (Meta("?P"),)),
            clause_used=prime_clause,
            clause_renamed=prime_clause,
            unifier={"?P": Const(prime_val)},
        )
        gt_step = _make_dispatcher_step(
            Atom(">", (Const(prime_val), Const(2))),
            goal_resolved=Atom(">", (Meta("?P"), Const(2))),
        )
        lt_step = _make_dispatcher_step(
            Atom("<", (Const(prime_val), Const(6))),
            goal_resolved=Atom("<", (Meta("?P"), Const(6))),
        )
        ne_step = _make_dispatcher_step(
            Atom("!=", (Const(prime_val), Const(4))),
            goal_resolved=Atom("!=", (Meta("?P"), Const(4))),
        )
        state = SLDState(
            goals=(),
            subst={"?P": Const(prime_val)},
            history=(kb_step, gt_step, lt_step, ne_step),
        )
        return state, prime_clause

    def test_prime_demo_kernel_verified(self):
        """Prime demo renders to a kernel-verified proof."""
        state, prime_clause = self._prime_demo_state(prime_val=5)
        kb = KnowledgeBase(clauses=(prime_clause,))
        query = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        proof = render(state, kb, query)
        assert isinstance(check_proof(proof), Verified)

    def test_prime_demo_line_count(self):
        """Prime demo: 7 lines (1 premise + 3 arithEval + 3 andI)."""
        state, prime_clause = self._prime_demo_state(prime_val=5)
        kb = KnowledgeBase(clauses=(prime_clause,))
        query = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        proof = render(state, kb, query)
        assert len(proof.lines) == 7

    def test_prime_demo_rule_names(self):
        """Prime demo rule sequence: Premise, arithEval×3, andI×3."""
        state, prime_clause = self._prime_demo_state(prime_val=5)
        kb = KnowledgeBase(clauses=(prime_clause,))
        query = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        proof = render(state, kb, query)
        names = _rendered_rule_names(proof)
        assert names == ["Premise", "arithEval", "arithEval", "arithEval", "andI", "andI", "andI"]

    def test_prime_demo_alphabet(self):
        """All rules in prime demo proof are in the M2 alphabet."""
        state, prime_clause = self._prime_demo_state(prime_val=5)
        kb = KnowledgeBase(clauses=(prime_clause,))
        query = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        proof = render(state, kb, query)
        for name in _rendered_rule_names(proof):
            assert name in _M2_ALPHABET

    def test_quadratic_single_root_kernel_verified(self):
        """Quadratic ?X=2 proof: one arithEval line, kernel-verified."""
        poly = Func(
            "+",
            (Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
             Const(6)),
        )
        # Verify atom: substitute x=2 into poly and equate to zero.
        # poly(2) = (2^2 - 5*2) + 6 = (4 - 10) + 6 = 0
        poly_at_2 = Func(
            "+",
            (Func("-", (Func("^", (Const(2), Const(2))), Func("*", (Const(5), Const(2))))),
             Const(6)),
        )
        ground = Equals(poly_at_2, Const(0))
        step = _make_dispatcher_step(
            ground,
            goal_resolved=Atom("root_of", (Meta("?X"), poly)),
            binding={"?X": Const(2)},
        )
        state = SLDState(goals=(), subst={"?X": Const(2)}, history=(step,))
        proof = render(state, KnowledgeBase(clauses=()), ground)
        assert len(proof.lines) == 1
        assert proof.lines[0].justification.rule == "arithEval"  # type: ignore[union-attr]
        assert isinstance(check_proof(proof), Verified)


# ---------------------------------------------------------------------------
# C. Multi-goal andI-chain invariants
# ---------------------------------------------------------------------------


class TestMultiGoalAndIChain:
    def test_two_goals_chain(self):
        """Two dispatcher goals → final line is andI of both."""
        a1 = Atom(">", (Const(3), Const(1)))
        a2 = Atom("<", (Const(1), Const(5)))
        state = _state_from_steps(
            _make_dispatcher_step(a1),
            _make_dispatcher_step(a2),
        )
        proof = render(state, KnowledgeBase(clauses=()), (a1, a2))
        assert isinstance(check_proof(proof), Verified)
        # Last line is andI
        last = proof.lines[-1]
        assert last.justification.rule == "andI"  # type: ignore[union-attr]
        assert isinstance(last.formula, And)

    def test_three_goals_left_associated_chain(self):
        """Three goals → left-associated andI chain ((g1 & g2) & g3)."""
        a1 = Atom(">", (Const(5), Const(1)))
        a2 = Atom("<", (Const(1), Const(10)))
        a3 = Atom("!=", (Const(5), Const(3)))
        state = _state_from_steps(
            _make_dispatcher_step(a1),
            _make_dispatcher_step(a2),
            _make_dispatcher_step(a3),
        )
        proof = render(state, KnowledgeBase(clauses=()), (a1, a2, a3))
        assert isinstance(check_proof(proof), Verified)
        # Final formula: ((a1 & a2) & a3)
        last_formula = proof.lines[-1].formula
        assert isinstance(last_formula, And)
        assert isinstance(last_formula.left, And)

    def test_single_goal_no_and_chain(self):
        """Single goal → no andI at the end (M1 shape preserved)."""
        a = Atom(">", (Const(5), Const(2)))
        state = _state_from_steps(_make_dispatcher_step(a))
        proof = render(state, KnowledgeBase(clauses=()), a)
        assert isinstance(check_proof(proof), Verified)
        # Only one line; no andI
        assert len(proof.lines) == 1
        names = _rendered_rule_names(proof)
        assert "andI" not in names

    def test_two_goals_depth_zero(self):
        """All lines in multi-goal proof have box_depth == 0."""
        a1 = Atom(">", (Const(3), Const(0)))
        a2 = Atom("<", (Const(0), Const(100)))
        state = _state_from_steps(
            _make_dispatcher_step(a1),
            _make_dispatcher_step(a2),
        )
        proof = render(state, KnowledgeBase(clauses=()), (a1, a2))
        assert all(line.box_depth == 0 for line in proof.lines)


# ---------------------------------------------------------------------------
# D. eqRefl vs arithEval policy (RENDER §4.4)
# ---------------------------------------------------------------------------


class TestEqualityRuleChoice:
    def test_reflexive_const_int(self):
        assert _choose_equality_rule(Equals(Const(7), Const(7))) == "eqRefl"

    def test_reflexive_const_fraction(self):
        h = Const(Fraction(1, 2))
        assert _choose_equality_rule(Equals(h, h)) == "eqRefl"

    def test_non_reflexive_different_values(self):
        assert _choose_equality_rule(Equals(Const(7), Const(8))) == "arithEval"

    def test_non_reflexive_func_vs_const(self):
        """Equals(2+3, 5) → arithEval (syntactically distinct sides)."""
        lhs = Func("+", (Const(2), Const(3)))
        rhs = Const(5)
        assert _choose_equality_rule(Equals(lhs, rhs)) == "arithEval"

    def test_atom_always_arith_eval(self):
        """Atoms (comparison predicates) never route to eqRefl."""
        for pred in (">", "<", "<=", ">=", "!="):
            assert _choose_equality_rule(Atom(pred, (Const(3), Const(3)))) == "arithEval"

    def test_reflexive_func_routes_eq_refl(self):
        """Equals(Func('+', (2, 3)), Func('+', (2, 3))) → eqRefl (same Func obj)."""
        t = Func("+", (Const(2), Const(3)))
        assert _choose_equality_rule(Equals(t, t)) == "eqRefl"


# ---------------------------------------------------------------------------
# E. Soundness backstops — malicious renderer scenarios
# ---------------------------------------------------------------------------


class TestSoundnessBackstops:
    def _make_proof_with_arith_eval(
        self, formula: Atom | Equals
    ) -> Proof:
        """Hand-craft a one-line proof with an arithEval justification."""
        line = ProofLine(
            number=1,
            formula=formula,
            justification=RuleApp("arithEval", (), (), {}),
            box_depth=0,
        )
        return Proof(lines=(line,), goal=formula)

    def test_false_comparison_kernel_rejects(self):
        """arithEval on 2 > 5 (false) → EvaluationFalse."""
        proof = self._make_proof_with_arith_eval(Atom(">", (Const(2), Const(5))))
        result = check_proof(proof)
        assert isinstance(result, CheckFailure)
        assert isinstance(result.reason, EvaluationFalse)

    def test_unresolved_meta_kernel_rejects(self):
        """arithEval on Atom(">", (Meta("?X"), 2)) → UnresolvedMeta (pre-check)."""
        proof = self._make_proof_with_arith_eval(Atom(">", (Meta("?X"), Const(2))))
        result = check_proof(proof)
        assert isinstance(result, CheckFailure)
        assert isinstance(result.reason, UnresolvedMeta)

    def test_contested_zero_pow_zero_kernel_rejects(self):
        """arithEval on Equals(0^0, 1) → MalformedArithmetic (contested)."""
        zero_pow_zero = Func("^", (Const(0), Const(0)))
        proof = self._make_proof_with_arith_eval(Equals(zero_pow_zero, Const(1)))
        result = check_proof(proof)
        assert isinstance(result, CheckFailure)
        assert isinstance(result.reason, MalformedArithmetic)

    def test_render_then_kernel_verify_accepted(self):
        """Rendering a true atom and kernel-verifying produces Verified."""
        atom = Atom(">", (Const(5), Const(2)))
        step = _make_dispatcher_step(atom)
        state = _state_from_steps(step)
        proof = render(state, KnowledgeBase(clauses=()), atom)
        assert isinstance(check_proof(proof), Verified)


# ---------------------------------------------------------------------------
# F. Hypothesis property test
# ---------------------------------------------------------------------------


# Strategies for generating small ground arithmetic atoms.
_int_consts = st.integers(min_value=-20, max_value=20).map(Const)
_frac_consts = st.fractions(
    min_value=Fraction(-10), max_value=Fraction(10), max_denominator=8
).map(Const)
_numeric_consts = st.one_of(_int_consts, _frac_consts)


@st.composite
def _arith_term(draw, depth=0):
    """Generate a small arithmetic term (Const or simple Func)."""
    if depth >= 2:
        return draw(_numeric_consts)
    return draw(
        st.one_of(
            _numeric_consts,
            st.builds(
                lambda a, b: Func("+", (a, b)),
                _arith_term(depth + 1),
                _arith_term(depth + 1),
            ),
            st.builds(
                lambda a, b: Func("-", (a, b)),
                _arith_term(depth + 1),
                _arith_term(depth + 1),
            ),
            st.builds(
                lambda a, b: Func("*", (a, b)),
                _arith_term(depth + 1),
                _arith_term(depth + 1),
            ),
        )
    )


@st.composite
def _ground_atom(draw):
    """Generate a ground arithmetic atom."""
    pred = draw(st.sampled_from([">", "<", ">=", "<=", "!="]))
    a = draw(_arith_term())
    b = draw(_arith_term())
    return Atom(pred, (a, b))


@settings(max_examples=80)
@given(atom=_ground_atom())
def test_property_rendered_proof_kernel_verified_or_false(atom: Atom):
    """For any ground arithmetic atom, the rendered proof either passes
    kernel verification (atom is true) or kernel rejects with EvaluationFalse
    (atom is false). No other outcomes.

    This tests that the renderer produces syntactically valid proofs
    unconditionally, and the kernel arbitrates truth.
    """
    step = _make_dispatcher_step(atom)
    state = _state_from_steps(step)
    proof = render(state, KnowledgeBase(clauses=()), atom)
    result = check_proof(proof)
    if isinstance(result, Verified):
        pass  # atom is true; proof accepted
    elif isinstance(result, CheckFailure):
        assert isinstance(result.reason, EvaluationFalse), (
            f"Expected EvaluationFalse for false atom {atom!r}, "
            f"got {type(result.reason).__name__}"
        )
    else:
        raise AssertionError(f"Unexpected check_proof result: {result!r}")
