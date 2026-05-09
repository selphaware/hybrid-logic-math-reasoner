"""End-to-end M2 demo tests per prd_milestone_2.md §14 and RENDER §10.5.

Each demo runs through manual_solve with real Z3 and SymPy bridges and
verifies the rendered proof passes check_proof. These are the M2 acceptance
tests; after this session, §15 definition of done has all proof-rendering
bullets green.
"""

from __future__ import annotations

import pytest
from fractions import Fraction

try:
    from hlmr.solvers.z3_bridge import Z3Bridge
    from hlmr.solvers.sympy_bridge import SymPyBridge
except ImportError as _e:
    pytest.skip(f"solver library not installed: {_e}", allow_module_level=True)

from hlmr.dispatch import OutsideFragmentReason
from hlmr.dispatch.route import Dispatcher
from hlmr.ir.formula import And, Atom, Const, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.solve import manual_solve


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_dispatcher(kb: KnowledgeBase) -> Dispatcher:
    return Dispatcher(
        z3_bridge=Z3Bridge(),
        sympy_bridge=SymPyBridge(),
        kb=kb,
    )


def _first_picker(cs, state):
    return 0 if cs else None


def _pick_prime_5(cs, state):
    """Picker that selects the clause unifying ?P with 5."""
    for i, c in enumerate(cs):
        match c.head:
            case Atom(pred="prime", args=(Const(value=5),)):
                return i
    return None


def _rendered_rule_names(proof: Proof) -> list[str]:
    from hlmr.ir.justification import Premise, RuleApp
    names = []
    for line in proof.lines:
        j = line.justification
        if isinstance(j, Premise):
            names.append("Premise")
        elif isinstance(j, RuleApp):
            names.append(j.rule)
    return names


_M2_ALPHABET = {"Premise", "forallE", "andI", "impE", "arithEval", "eqRefl"}

_PRIME_KB = KnowledgeBase(
    clauses=tuple(
        Clause(f"prime_{p}", Atom("prime", (Const(p),)), ())
        for p in [2, 3, 5, 7]
    )
)

_EMPTY_KB = KnowledgeBase(clauses=())


# ---------------------------------------------------------------------------
# A. Demo 1 — the §2 prime example
# ---------------------------------------------------------------------------


class TestPrimeDemo:
    def test_prime_demo_produces_verified_proof(self):
        """prime(?P), ?P>2, ?P<6, ?P!=4 with pick prime(5) → verified proof."""
        d = _make_dispatcher(_PRIME_KB)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(_PRIME_KB, goals, _pick_prime_5, dispatcher=d)
        assert result is not None
        sat, proof = result
        assert proof is not None
        assert isinstance(check_proof(proof), Verified)

    def test_prime_demo_substitution(self):
        """{?P: 5} after picking prime(5)."""
        d = _make_dispatcher(_PRIME_KB)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(_PRIME_KB, goals, _pick_prime_5, dispatcher=d)
        sat, _ = result
        assert sat.get("?P") == Const(5)

    def test_prime_demo_proof_goal_is_conjunction(self):
        """Proof goal is the andI-chained conjunction of all four atoms."""
        d = _make_dispatcher(_PRIME_KB)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(_PRIME_KB, goals, _pick_prime_5, dispatcher=d)
        _, proof = result
        # Goal is ((prime(5) & 5>2) & 5<6) & 5!=4 — left-associated And
        assert isinstance(proof.goal, And)
        assert isinstance(proof.goal.left, And)
        assert isinstance(proof.goal.left.left, And)

    def test_prime_demo_rule_alphabet(self):
        """All rules in the prime demo proof are in the M2 alphabet."""
        d = _make_dispatcher(_PRIME_KB)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(_PRIME_KB, goals, _pick_prime_5, dispatcher=d)
        _, proof = result
        for name in _rendered_rule_names(proof):
            assert name in _M2_ALPHABET

    def test_prime_demo_depth_zero(self):
        """Every proof line has box_depth == 0 (RENDER §10)."""
        d = _make_dispatcher(_PRIME_KB)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(_PRIME_KB, goals, _pick_prime_5, dispatcher=d)
        _, proof = result
        assert all(line.box_depth == 0 for line in proof.lines)


# ---------------------------------------------------------------------------
# B. Demo 2 — the quadratic
# ---------------------------------------------------------------------------


def _quadratic_poly():
    """IR for x^2 - 5x + 6."""
    return Func(
        "+",
        (
            Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
            Const(6),
        ),
    )


class TestQuadraticDemo:
    def test_quadratic_first_root_verified(self):
        """Pick first root → kernel-verified proof."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), _quadratic_poly()))
        result = manual_solve(
            _EMPTY_KB, goal, _first_picker,
            dispatcher=d, solver_picker=lambda sols: 0,
        )
        assert result is not None
        sat, proof = result
        assert proof is not None
        assert isinstance(check_proof(proof), Verified)

    def test_quadratic_second_root_verified(self):
        """Pick second root → kernel-verified proof."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), _quadratic_poly()))
        result = manual_solve(
            _EMPTY_KB, goal, _first_picker,
            dispatcher=d, solver_picker=lambda sols: 1,
        )
        assert result is not None
        sat, proof = result
        assert proof is not None
        assert isinstance(check_proof(proof), Verified)

    def test_quadratic_roots_are_2_and_3(self):
        """The two roots are 2 and 3 (order may vary)."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), _quadratic_poly()))

        root_values = []
        for idx in (0, 1):
            d2 = _make_dispatcher(_EMPTY_KB)
            result = manual_solve(
                _EMPTY_KB, goal, _first_picker,
                dispatcher=d2, solver_picker=lambda sols, i=idx: i,
            )
            assert result is not None
            sat, _ = result
            v = sat.get("?X")
            assert v is not None
            root_values.append(v.value)

        assert sorted(root_values) == [2, 3]

    def test_quadratic_single_arith_eval_line(self):
        """Quadratic proof is exactly one arithEval line (single goal, leaf step)."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), _quadratic_poly()))
        result = manual_solve(
            _EMPTY_KB, goal, _first_picker,
            dispatcher=d, solver_picker=lambda sols: 0,
        )
        _, proof = result
        assert len(proof.lines) == 1
        assert _rendered_rule_names(proof) == ["arithEval"]


# ---------------------------------------------------------------------------
# C. Demo 3 — linear system
# ---------------------------------------------------------------------------


class TestLinearSystemDemo:
    def test_linear_system_verified_proof(self):
        """?X=2, ?X+?Y=10 → {?X:2, ?Y:8}, kernel-verified proof with andI chain."""
        d = _make_dispatcher(_EMPTY_KB)
        from hlmr.ir.formula import Equals
        goals = (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )
        result = manual_solve(_EMPTY_KB, goals, _first_picker, dispatcher=d)
        assert result is not None
        sat, proof = result
        assert proof is not None
        assert isinstance(check_proof(proof), Verified)
        assert sat.get("?X") == Const(2)
        assert sat.get("?Y") == Const(8)

    def test_linear_system_uses_eq_refl_for_binding(self):
        """The ?X=2 step emits eqRefl (Equals(2,2) is reflexive)."""
        d = _make_dispatcher(_EMPTY_KB)
        from hlmr.ir.formula import Equals
        goals = (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )
        result = manual_solve(_EMPTY_KB, goals, _first_picker, dispatcher=d)
        _, proof = result
        names = _rendered_rule_names(proof)
        # First non-andI line is eqRefl (binding Equals(2, 2))
        assert "eqRefl" in names

    def test_linear_system_proof_goal_is_conjunction(self):
        """Proof goal is the andI conjunction of the two instantiated equalities."""
        d = _make_dispatcher(_EMPTY_KB)
        from hlmr.ir.formula import Equals
        goals = (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )
        result = manual_solve(_EMPTY_KB, goals, _first_picker, dispatcher=d)
        _, proof = result
        assert isinstance(proof.goal, And)


# ---------------------------------------------------------------------------
# D. Demo 4 — OutsideFragment rejection
# ---------------------------------------------------------------------------


class TestOutsideFragmentDemo:
    def test_transcendental_returns_none(self):
        """root_of(?X, 2^x) → classifier rejects → manual_solve returns None."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
        result = manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
        assert result is None

    def test_transcendental_sets_last_outside_fragment(self):
        """dispatcher.last_outside_fragment is set with TRANSCENDENTAL reason."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
        manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
        assert d.last_outside_fragment is not None
        assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL

    def test_transcendental_no_proof_produced(self):
        """No proof object is produced for OutsideFragment rejection."""
        d = _make_dispatcher(_EMPTY_KB)
        goal = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
        result = manual_solve(_EMPTY_KB, goal, _first_picker, dispatcher=d)
        # None means no (sat, proof) tuple at all.
        assert result is None
