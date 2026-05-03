from __future__ import annotations

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
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
)
from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof
from hlmr.kernel.errors import (
    CheckFailure,
    CheckResult,
    GoalMismatch,
    StructuralError,
    UnknownRule,
    UnresolvedMeta,
    Verified,
)
from hlmr.kernel.rules import RULES


def _term_contains_meta(t: Term) -> str | None:
    match t:
        case Meta(name=name):
            return name
        case Func(args=args):
            for a in args:
                if (found := _term_contains_meta(a)) is not None:
                    return found
    return None


def _formula_contains_meta(f: Formula) -> str | None:
    """Walk f transitively; return the first Meta name found, or None.

    The kernel does not import unify/ or solve/; it knows Meta only as
    a Term subclass that must never appear in a finished proof.
    """
    match f:
        case Atom(args=args):
            for t in args:
                if (found := _term_contains_meta(t)) is not None:
                    return found
        case Equals(lhs=lhs, rhs=rhs):
            return _term_contains_meta(lhs) or _term_contains_meta(rhs)
        case Not(body=body):
            return _formula_contains_meta(body)
        case And(left=left, right=right) | Or(left=left, right=right) | Implies(left=left, right=right) | Iff(left=left, right=right):
            return _formula_contains_meta(left) or _formula_contains_meta(right)
        case ForAll(body=body) | Exists(body=body):
            return _formula_contains_meta(body)
    return None


def check_proof(proof: Proof) -> CheckResult:
    """Verify a Fitch-style proof, returning Verified() or CheckFailure.

    Algorithm (prd_milestone_0.md §7.4):
    1. Sanity checks: non-empty, sequential line numbers, depth constraints,
       premises at depth 0, depth increases only at Assumption lines.
    2. Per-line rule checking.
    3. Final depth must be 0 (all boxes discharged).
    4. Goal check if proof.goal is set.
    """
    lines = proof.lines

    # 1a. Empty proof rejected
    if not lines:
        return CheckFailure(0, StructuralError("proof has no lines"))

    # §5.3 Meta rejection. Must fire before rule dispatch (rule code can
    # pattern-match on Meta-bearing formulas and produce undefined behaviour).
    # Position relative to structural sanity is aesthetic — structural pass
    # is Meta-blind (reads only line.number, line.box_depth, line.justification).
    for line in lines:
        if (name := _formula_contains_meta(line.formula)) is not None:
            return CheckFailure(line.number, UnresolvedMeta(line.number, name))

    # 1b. Structural sanity pass
    for i, line in enumerate(lines):
        expected_number = i + 1
        if line.number != expected_number:
            return CheckFailure(
                line.number,
                StructuralError(
                    f"line {i + 1} has number {line.number}, expected {expected_number}"
                ),
            )
        if line.box_depth < 0:
            return CheckFailure(
                line.number,
                StructuralError(f"line {line.number} has negative box depth"),
            )
        # Depth may increase by at most 1
        prev_depth = lines[i - 1].box_depth if i > 0 else 0
        if line.box_depth > prev_depth + 1:
            return CheckFailure(
                line.number,
                StructuralError(
                    f"line {line.number} depth {line.box_depth} jumps more than 1 "
                    f"from previous depth {prev_depth}"
                ),
            )
        # Depth increases only at Assumption lines
        if line.box_depth > prev_depth and not isinstance(
            line.justification, Assumption
        ):
            return CheckFailure(
                line.number,
                StructuralError(
                    f"line {line.number} opens a new box but is not an Assumption"
                ),
            )
        # Assumptions must be at depth > 0. Sibling boxes (e.g. the two case
        # branches in orE) stay at the same depth, so we cannot require
        # every Assumption to strictly increase depth. But depth 0 is never
        # a valid Assumption — it can't be discharged by any rule.
        if isinstance(line.justification, Assumption) and line.box_depth == 0:
            return CheckFailure(
                line.number,
                StructuralError(
                    f"Assumption at line {line.number} is at depth 0"
                ),
            )
        # Premises must be at depth 0
        if isinstance(line.justification, Premise) and line.box_depth != 0:
            return CheckFailure(
                line.number,
                StructuralError(f"Premise at line {line.number} is not at depth 0"),
            )

    # 2. Per-line rule checking
    for line in lines:
        if isinstance(line.justification, (Premise, Assumption)):
            continue
        app = line.justification
        if not isinstance(app, RuleApp):
            return CheckFailure(
                line.number,
                StructuralError(f"unknown justification type at line {line.number}"),
            )
        checker = RULES.get(app.rule)
        if checker is None:
            return CheckFailure(line.number, UnknownRule(app.rule))
        error = checker(line, proof)
        if error is not None:
            return CheckFailure(line.number, error)

    # 3. Final depth must be 0
    final_depth = lines[-1].box_depth
    if final_depth != 0:
        return CheckFailure(
            lines[-1].number,
            StructuralError(
                f"proof ends at depth {final_depth} (unclosed box)"
            ),
        )

    # 4. Goal check
    if proof.goal is not None:
        final_formula = lines[-1].formula
        if final_formula != proof.goal:
            return CheckFailure(
                lines[-1].number,
                GoalMismatch(proof.goal, final_formula),
            )

    return Verified()
