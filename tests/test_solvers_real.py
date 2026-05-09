"""Integration tests for real Z3Bridge and SymPyBridge.

These tests exercise the real solver implementations (not mocks).
They require z3 and sympy to be installed (runtime deps per
prd_milestone_2.md §8). A try/except at import time provides a
pytest.skip fallback, but should never fire in the standard env.
"""

from __future__ import annotations

import pytest
from fractions import Fraction

try:
    from hlmr.solvers.z3_bridge import Z3Bridge
    from hlmr.solvers.sympy_bridge import SymPyBridge
except ImportError as _e:
    pytest.skip(f"solver library not installed: {_e}", allow_module_level=True)

from hlmr.dispatch import (
    MultipleSolutions,
    NoSolution,
    OutsideFragment,
    OutsideFragmentReason,
    UniqueSolution,
    Underdetermined,
)
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.dispatch.route import Dispatcher, SolverKernelDisagreement
from hlmr.ir.formula import Atom, Const, Equals, Func, Meta, Var
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.solve import manual_solve
from hlmr.solvers import (
    SymPyConditionSet,
    SymPyError,
    SymPyFiniteRoots,
    SymPyNoRealRoots,
    Z3Result,
    Z3Sat,
    Z3Timeout,
    Z3Unsat,
    SymPyResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def z3b():
    return Z3Bridge(default_timeout_ms=5000)


@pytest.fixture
def spb():
    return SymPyBridge()


def _make_real_dispatcher(kb=None):
    """Dispatcher backed by real Z3Bridge and SymPyBridge."""
    if kb is None:
        kb = KnowledgeBase(clauses=())
    return Dispatcher(
        z3_bridge=Z3Bridge(),
        sympy_bridge=SymPyBridge(),
        kb=kb,
    )


# ---------------------------------------------------------------------------
# A. Z3 bridge translation correctness
# ---------------------------------------------------------------------------


class TestZ3BridgeTranslation:
    def test_sat_single_meta_range(self, z3b):
        """?P > 2 ∧ ?P < 6 ∧ ?P != 4 → Z3Sat; model has ?P ∈ {3, 5}."""
        result = z3b.check(
            (
                Atom(">", (Meta("?P"), Const(2))),
                Atom("<", (Meta("?P"), Const(6))),
                Atom("!=", (Meta("?P"), Const(4))),
            ),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert "?P" in result.model
        assert result.model["?P"] in (3, 5)

    def test_unsat_contradictory_range(self, z3b):
        """?P > 2 ∧ ?P < 2 → Z3Unsat."""
        result = z3b.check(
            (
                Atom(">", (Meta("?P"), Const(2))),
                Atom("<", (Meta("?P"), Const(2))),
            ),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Unsat)

    def test_sat_underdetermined_two_metas(self, z3b):
        """?P + ?Q = 10 → Z3Sat with some witness; dispatcher detects underdetermination."""
        result = z3b.check(
            (Equals(Func("+", (Meta("?P"), Meta("?Q"))), Const(10)),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert "?P" in result.model
        assert "?Q" in result.model
        # Values must sum to 10.
        p = result.model["?P"]
        q = result.model["?Q"]
        assert p + q == 10

    def test_sat_equals_single_meta(self, z3b):
        """?X = 5 → Z3Sat({?X: 5})."""
        result = z3b.check(
            (Equals(Meta("?X"), Const(5)),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert result.model.get("?X") == 5

    def test_sat_fraction_const(self, z3b):
        """?X > 1/2 ∧ ?X < 1 → Z3Sat with rational witness."""
        half = Const(Fraction(1, 2))
        result = z3b.check(
            (
                Atom(">", (Meta("?X"), half)),
                Atom("<", (Meta("?X"), Const(1))),
            ),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        val = result.model["?X"]
        assert Fraction(1, 2) < val < 1

    def test_sat_negation_inequality(self, z3b):
        """?X != 3 ∧ ?X > 0 ∧ ?X < 5 → Z3Sat, model not 3."""
        result = z3b.check(
            (
                Atom("!=", (Meta("?X"), Const(3))),
                Atom(">", (Meta("?X"), Const(0))),
                Atom("<", (Meta("?X"), Const(5))),
            ),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert result.model["?X"] != 3

    @pytest.mark.slow
    def test_timeout_very_short(self, z3b):
        """Extremely short timeout → Z3Timeout (may be flaky on fast CI)."""
        result = z3b.check(
            (Atom(">", (Meta("?X"), Const(0))),),
            timeout_ms=1,
        )
        # On fast hardware with trivial constraints Z3 may still return sat.
        # Accept both: the point is the bridge does not crash.
        assert isinstance(result, (Z3Sat, Z3Timeout))

    def test_model_values_are_int_or_fraction(self, z3b):
        """Model values must be int or Fraction, never float or str."""
        result = z3b.check(
            (
                Atom(">", (Meta("?P"), Const(0))),
                Atom("<", (Meta("?P"), Const(10))),
            ),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        for val in result.model.values():
            assert isinstance(val, (int, Fraction))


# ---------------------------------------------------------------------------
# B. SymPy bridge translation correctness
# ---------------------------------------------------------------------------


class TestSymPyBridgeTranslation:
    def test_quadratic_two_roots(self, spb):
        """x^2 - 5x + 6 → roots {2, 3}."""
        poly = Func(
            "+",
            (
                Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
                Const(6),
            ),
        )
        result = spb.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyFiniteRoots)
        assert sorted(result.roots) == [2, 3]

    def test_linear_one_root(self, spb):
        """x - 3 → root {3}."""
        result = spb.solveset(
            Atom("root_of", (Meta("?X"), Func("-", (Var("x"), Const(3)))))
        )
        assert isinstance(result, SymPyFiniteRoots)
        assert result.roots == (3,)

    def test_equals_squared_integer_roots(self, spb):
        """Equals(?X^2, 9) → roots {-3, 3}."""
        result = spb.solveset(
            Equals(Func("^", (Meta("?X"), Const(2))), Const(9))
        )
        assert isinstance(result, SymPyFiniteRoots)
        assert sorted(result.roots) == [-3, 3]

    def test_no_real_roots_quadratic(self, spb):
        """x^2 + 1 → no real roots."""
        result = spb.solveset(
            Atom(
                "root_of",
                (
                    Meta("?X"),
                    Func("+", (Func("^", (Var("x"), Const(2))), Const(1))),
                ),
            )
        )
        assert isinstance(result, SymPyNoRealRoots)

    def test_irrational_root_condition_set(self, spb):
        """Equals(?X^2, 2) → sqrt(2) irrational → SymPyConditionSet."""
        result = spb.solveset(
            Equals(Func("^", (Meta("?X"), Const(2))), Const(2))
        )
        assert isinstance(result, SymPyConditionSet)

    def test_cubic_irrational_condition_set(self, spb):
        """x^3 - 2 → cube root of 2 is irrational → SymPyConditionSet."""
        result = spb.solveset(
            Atom(
                "root_of",
                (
                    Meta("?X"),
                    Func("-", (Func("^", (Var("x"), Const(3))), Const(2))),
                ),
            )
        )
        assert isinstance(result, SymPyConditionSet)

    def test_rational_root_fraction(self, spb):
        """2x - 3 → root 3/2."""
        result = spb.solveset(
            Atom(
                "root_of",
                (
                    Meta("?X"),
                    Func("-", (Func("*", (Const(2), Var("x"))), Const(3))),
                ),
            )
        )
        assert isinstance(result, SymPyFiniteRoots)
        assert len(result.roots) == 1
        assert result.roots[0] == Fraction(3, 2)

    def test_transcendental_no_real_roots_safety_net(self, spb):
        """2^x (no constant offset): SymPy returns no real roots since 2^x > 0."""
        result = spb.solveset(
            Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
        )
        # 2^x > 0 always, so no real root; SymPy returns EmptySet.
        assert isinstance(result, SymPyNoRealRoots)


# ---------------------------------------------------------------------------
# C. Round-trip through Dispatcher with real bridges
# ---------------------------------------------------------------------------


def _first_picker(cs, state):
    return 0 if cs else None


def _pick_prime_5(cs, state):
    """Picker that selects the clause unifying ?P with 5."""
    for i, c in enumerate(cs):
        match c.head:
            case Atom(pred="prime", args=(Const(value=5),)):
                return i
    return None


class TestDispatcherRoundTrip:
    def test_prime_example_via_manual_solve(self):
        """§2 prime demo: KB prime facts + arithmetic constraints → ?P = 5.

        The picker selects prime(5); arithmetic goals are all ground after
        the KB step and short-circuit without a Z3 call.
        """
        primes = [2, 3, 5, 7]
        kb = KnowledgeBase(
            clauses=tuple(
                Clause(f"prime_{p}", Atom("prime", (Const(p),)), ())
                for p in primes
            )
        )
        d = _make_real_dispatcher(kb=kb)
        goals = (
            Atom("prime", (Meta("?P"),)),
            Atom(">", (Meta("?P"), Const(2))),
            Atom("<", (Meta("?P"), Const(6))),
            Atom("!=", (Meta("?P"), Const(4))),
        )
        result = manual_solve(kb, goals, _pick_prime_5, dispatcher=d)
        assert result is not None
        sat, proof = result
        assert proof is not None  # renderer now handles DispatcherResolvedSteps (5b)
        assert isinstance(check_proof(proof), Verified)
        assert sat.get("?P") == Const(5)

    def test_quadratic_multiple_solutions(self):
        """root_of(?X, x^2-5x+6) → MultipleSolutions with roots {2, 3}."""
        d = _make_real_dispatcher()
        poly = Func(
            "+",
            (
                Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
                Const(6),
            ),
        )
        goal = Atom("root_of", (Meta("?X"), poly))
        result = d.dispatch(goal, {})
        assert isinstance(result.outcome, MultipleSolutions)
        solution_values = sorted(
            b["?X"].value for b in result.outcome.solutions
        )
        assert solution_values == [2, 3]

    def test_linear_system_unique_solution(self):
        """?X = 2, then ?X + ?Y = 10 → {?X: 2, ?Y: 8}.

        Goals processed in order: bind ?X first, then ?Y from the sum.
        """
        d = _make_real_dispatcher()
        # Order matters: bind ?X first so the second goal has one free meta.
        goals = (
            Equals(Meta("?X"), Const(2)),
            Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10)),
        )
        result = manual_solve(KnowledgeBase(clauses=()), goals, _first_picker, dispatcher=d)
        assert result is not None
        sat, proof = result
        assert proof is not None  # renderer now handles DispatcherResolvedSteps (5b)
        assert isinstance(check_proof(proof), Verified)
        assert sat.get("?X") == Const(2)
        assert sat.get("?Y") == Const(8)

    def test_outside_fragment_transcendental(self):
        """root_of(?X, 2^x) → OutsideFragment(TRANSCENDENTAL) via classifier."""
        d = _make_real_dispatcher()
        goal = Atom("root_of", (Meta("?X"), Func("^", (Const(2), Var("x")))))
        result = manual_solve(KnowledgeBase(clauses=()), goal, _first_picker, dispatcher=d)
        assert result is None
        assert d.last_outside_fragment is not None
        assert d.last_outside_fragment.classification == OutsideFragmentReason.TRANSCENDENTAL

    def test_no_solution_unsat_z3(self):
        """?X > 5 ∧ ?X < 3 → NoSolution."""
        d = _make_real_dispatcher()
        goals = (
            Atom(">", (Meta("?X"), Const(5))),
            Atom("<", (Meta("?X"), Const(3))),
        )
        # First goal alone is satisfiable → Z3 returns sat for ?X > 5.
        # But then ?X is bound to e.g. 6, and ?X < 3 with ?X=6 is ground-false.
        # So the second ground goal returns NoSolution from short-circuit.
        result = manual_solve(KnowledgeBase(clauses=()), goals, _first_picker, dispatcher=d)
        assert result is None

    def test_multiple_solutions_solver_picker(self):
        """MultipleSolutions: solver_picker selects solution at index 0."""
        d = _make_real_dispatcher()
        poly = Func(
            "+",
            (
                Func("-", (Func("^", (Var("x"), Const(2))), Func("*", (Const(5), Var("x"))))),
                Const(6),
            ),
        )
        goal = Atom("root_of", (Meta("?X"), poly))
        picked = []
        def capturing_picker(solutions):
            picked.append(solutions)
            return 0
        result = manual_solve(
            KnowledgeBase(clauses=()), goal, _first_picker,
            dispatcher=d, solver_picker=capturing_picker,
        )
        assert result is not None
        assert len(picked) == 1
        assert len(picked[0]) == 2  # two solutions presented

    def test_z3_sequential_ground_verification(self):
        """?X > 2 then ?X < 100: Z3 binds ?X on first goal; second is ground-verified.

        Demonstrates the one-goal-at-a-time dispatch: Z3 picks some value > 2
        (typically 3), then the second constraint ?X < 100 is ground and verified
        by arithEval without another Z3 call.
        """
        d = _make_real_dispatcher()
        goals = (
            Atom(">", (Meta("?X"), Const(2))),
            Atom("<", (Meta("?X"), Const(100))),
        )
        result = manual_solve(
            KnowledgeBase(clauses=()), goals, _first_picker, dispatcher=d
        )
        assert result is not None
        sat, proof = result
        assert proof is not None  # renderer now handles multi-goal (5b)
        assert isinstance(check_proof(proof), Verified)
        x_val = sat.get("?X")
        assert x_val is not None
        v = x_val.value
        # Must satisfy both original constraints.
        assert v > 2 and v < 100

    def test_underdetermined_single_constraint_two_metas(self):
        """?X + ?Y = 10 alone → Underdetermined (two free metas, second model found)."""
        d = _make_real_dispatcher()
        goal = Equals(Func("+", (Meta("?X"), Meta("?Y"))), Const(10))
        result = manual_solve(
            KnowledgeBase(clauses=()), goal, _first_picker, dispatcher=d
        )
        # Underdetermined → (partial_binding, None) not None.
        assert result is not None
        sat, proof = result
        assert proof is None


# ---------------------------------------------------------------------------
# D. Soundness backstop with real solvers
# ---------------------------------------------------------------------------


class TestSoundnessBackstop:
    def test_lying_z3_bridge_raises_disagreement(self):
        """A Z3 bridge that returns a false witness triggers SolverKernelDisagreement.

        Dispatcher calls _verify_arith_ground; the kernel rejects the false
        witness with EvaluationFalse → Case 1 crash.
        """
        from dataclasses import dataclass, field as dc_field

        @dataclass
        class LyingZ3Bridge:
            """Always claims ?P = 1 regardless of the actual constraints."""
            calls: list = dc_field(default_factory=list)
            def check(self, constraints, timeout_ms):
                self.calls.append(constraints)
                return Z3Sat(model={"?P": 1})

        d = Dispatcher(
            z3_bridge=LyingZ3Bridge(),
            sympy_bridge=SymPyBridge(),
            kb=KnowledgeBase(clauses=()),
        )
        # Goal: ?P > 100 (1 > 100 is false).
        goal = Atom(">", (Meta("?P"), Const(100)))
        with pytest.raises(SolverKernelDisagreement):
            d.dispatch(goal, {})

    def test_correct_z3_witness_does_not_raise(self):
        """A real Z3-derived correct witness passes verify without crashing."""
        d = _make_real_dispatcher()
        goal = Atom(">", (Meta("?P"), Const(0)))
        result = d.dispatch(goal, {})
        assert isinstance(result.outcome, UniqueSolution)

    def test_lying_sympy_bridge_raises_disagreement(self):
        """SymPy bridge that returns an incorrect root triggers Case 1 crash."""
        from dataclasses import dataclass, field as dc_field

        @dataclass
        class LyingSymPyBridge:
            """Claims the root of x^2 - 4 is 99 (wrong)."""
            def solveset(self, goal):
                return SymPyFiniteRoots(roots=(99,))

        d = Dispatcher(
            z3_bridge=Z3Bridge(),
            sympy_bridge=LyingSymPyBridge(),
            kb=KnowledgeBase(clauses=()),
        )
        # root_of(?X, x^2 - 4) → bridge claims ?X = 99; verify: 99^2 - 4 = 0 is false.
        poly = Func("-", (Func("^", (Var("x"), Const(2))), Const(4)))
        goal = Atom("root_of", (Meta("?X"), poly))
        with pytest.raises(SolverKernelDisagreement):
            d.dispatch(goal, {})


# ---------------------------------------------------------------------------
# E. Z3Bridge translation error paths (coverage uplift for §14.3)
# ---------------------------------------------------------------------------


class TestZ3BridgeTranslationErrors:
    def test_string_const_raises(self):
        """Const('alice') is not arithmetic — Z3 bridge must reject it."""
        from hlmr.solvers.z3_bridge import Z3TranslationError
        b = Z3Bridge()
        with pytest.raises(Z3TranslationError):
            b.check((Atom(">", (Const("alice"), Const(0))),), timeout_ms=1000)

    def test_unrecognised_atom_raises(self):
        """An atom with an unrecognised predicate (e.g. 'foo') raises."""
        from hlmr.solvers.z3_bridge import Z3TranslationError
        b = Z3Bridge()
        with pytest.raises(Z3TranslationError):
            b.check((Atom("foo", (Const(1), Const(2))),), timeout_ms=1000)

    def test_transcendental_power_raises(self):
        """Func('^', (Var, Var)) — variable exponent — raises translation error."""
        from hlmr.solvers.z3_bridge import Z3TranslationError
        b = Z3Bridge()
        # Variable in exponent position — transcendental.
        with pytest.raises(Z3TranslationError):
            b.check(
                (Atom(">", (Func("^", (Const(2), Meta("?X"))), Const(0))),),
                timeout_ms=1000,
            )

    def test_ternary_minus_z3_sat(self):
        """Atom('minus', (a, b, c)) → Z3 constraint a - b == c."""
        b = Z3Bridge()
        result = b.check(
            (Atom("minus", (Meta("?A"), Const(3), Const(7))),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert result.model.get("?A") == 10

    def test_ternary_times_z3_sat(self):
        """Atom('times', (a, b, c)) → Z3 constraint a * b == c."""
        b = Z3Bridge()
        result = b.check(
            (Atom("times", (Meta("?A"), Const(3), Const(15))),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert result.model.get("?A") == 5

    def test_ternary_divides_z3_sat(self):
        """Atom('divides', (a, b, c)) → Z3 constraint a / b == c."""
        b = Z3Bridge()
        result = b.check(
            (Atom("divides", (Const(10), Const(2), Meta("?C"))),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)
        assert result.model.get("?C") == 5

    def test_lte_gte_predicates(self):
        """Atom('<=', ...) and Atom('>=', ...) translate correctly."""
        b = Z3Bridge()
        r1 = b.check((Atom("<=", (Const(3), Const(5))),), timeout_ms=5000)
        assert isinstance(r1, Z3Sat)
        r2 = b.check((Atom(">=", (Const(5), Const(3))),), timeout_ms=5000)
        assert isinstance(r2, Z3Sat)

    def test_unary_negation_term(self):
        """Func('-', (a,)) — unary negation — translates correctly."""
        b = Z3Bridge()
        neg_meta = Func("-", (Meta("?X"),))
        result = b.check(
            (Atom(">", (neg_meta, Const(-10))),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)

    def test_division_term(self):
        """Func('/', (a, b)) — division — translates correctly."""
        b = Z3Bridge()
        half = Func("/", (Const(1), Const(2)))
        result = b.check(
            (Atom(">", (half, Const(0))),),
            timeout_ms=5000,
        )
        assert isinstance(result, Z3Sat)


# ---------------------------------------------------------------------------
# F. SymPyBridge translation error paths (coverage uplift for §14.3)
# ---------------------------------------------------------------------------


class TestSymPyBridgeTranslationErrors:
    def test_non_root_of_non_equals_raises_sympy_error(self):
        """Arithmetic atom (not root_of/Equals) reaching SymPy → SymPyError."""
        b = SymPyBridge()
        result = b.solveset(Atom(">", (Meta("?X"), Const(2))))
        assert isinstance(result, SymPyError)

    def test_constant_polynomial_no_var(self):
        """Polynomial with no free symbols (constant) → FiniteRoots(())."""
        b = SymPyBridge()
        result = b.solveset(Atom("root_of", (Meta("?X"), Const(5))))
        assert isinstance(result, SymPyFiniteRoots)
        assert result.roots == ()

    def test_string_const_sympy_error(self):
        """Const('abc') in polynomial → SymPyError."""
        b = SymPyBridge()
        result = b.solveset(Atom("root_of", (Meta("?X"), Const("abc"))))
        assert isinstance(result, SymPyError)

    def test_equals_no_free_symbols_equal(self):
        """Equals(2, 2) — no variable — FiniteRoots(()) (trivially true)."""
        b = SymPyBridge()
        result = b.solveset(Equals(Const(2), Const(2)))
        assert isinstance(result, SymPyFiniteRoots)
        assert result.roots == ()

    def test_equals_no_free_symbols_unequal(self):
        """Equals(2, 3) — no variable, false — NoRealRoots."""
        b = SymPyBridge()
        result = b.solveset(Equals(Const(2), Const(3)))
        assert isinstance(result, SymPyNoRealRoots)

    def test_fraction_const_in_polynomial(self):
        """Fraction coefficients translate correctly via sympy.Rational."""
        b = SymPyBridge()
        # 2x - 1/2 = 0 → x = 1/4
        poly = Func("-", (Func("*", (Const(2), Var("x"))), Const(Fraction(1, 2))))
        result = b.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyFiniteRoots)
        assert len(result.roots) == 1
        assert result.roots[0] == Fraction(1, 4)

    def test_unary_negation_term(self):
        """Func('-', (Var('x'),)) — unary negation in polynomial."""
        b = SymPyBridge()
        # -x + 3 = 0 → x = 3
        poly = Func("+", (Func("-", (Var("x"),)), Const(3)))
        result = b.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyFiniteRoots)
        assert result.roots == (3,)

    def test_division_term_in_polynomial(self):
        """Func('/', (a, b)) — division in SymPy expression."""
        b = SymPyBridge()
        # x/2 - 1 = 0 → x = 2
        poly = Func("-", (Func("/", (Var("x"), Const(2))), Const(1)))
        result = b.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyFiniteRoots)
        assert result.roots == (2,)

    def test_unknown_func_name_sympy_error(self):
        """An unrecognised Func name in the polynomial → SymPyError."""
        b = SymPyBridge()
        poly = Func("unknown_op", (Var("x"), Const(1)))
        result = b.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyError)

    def test_multiple_free_symbols_error(self):
        """Polynomial with >1 free symbols → SymPyError (multi-var not supported)."""
        b = SymPyBridge()
        # x + y (two free symbols) — should raise SymPyTranslationError
        poly = Func("+", (Var("x"), Var("y")))
        result = b.solveset(Atom("root_of", (Meta("?X"), poly)))
        assert isinstance(result, SymPyError)


# ---------------------------------------------------------------------------
# G. solvers/__init__.py lazy re-export (coverage uplift)
# ---------------------------------------------------------------------------


def test_solvers_init_real_z3_bridge_import():
    """The __getattr__ lazy re-export of RealZ3Bridge works."""
    from hlmr import solvers
    klass = solvers.RealZ3Bridge
    assert klass is Z3Bridge


def test_solvers_init_real_sympy_bridge_import():
    """The __getattr__ lazy re-export of RealSymPyBridge works."""
    from hlmr import solvers
    klass = solvers.RealSymPyBridge
    assert klass is SymPyBridge


def test_solvers_init_unknown_attr_raises():
    """__getattr__ raises AttributeError for unknown names."""
    import hlmr.solvers as s
    import pytest
    with pytest.raises(AttributeError):
        _ = s.NonExistentThing
