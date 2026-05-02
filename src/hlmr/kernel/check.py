from __future__ import annotations

from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof
from hlmr.kernel.errors import (
    CheckFailure,
    CheckResult,
    GoalMismatch,
    StructuralError,
    UnknownRule,
    Verified,
)
from hlmr.kernel.rules import RULES


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
