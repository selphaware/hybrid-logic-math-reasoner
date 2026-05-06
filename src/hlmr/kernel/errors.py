from __future__ import annotations

from dataclasses import dataclass

from hlmr.ir.formula import Formula

# ---------------------------------------------------------------------------
# Check results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Verified:
    @property
    def ok(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True


@dataclass(frozen=True)
class CheckFailure:
    line: int
    reason: RuleError

    @property
    def ok(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False


CheckResult = Verified | CheckFailure


# ---------------------------------------------------------------------------
# Rule errors — all frozen dataclasses, no string-only errors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleError(Exception):
    pass


@dataclass(frozen=True)
class UnknownRule(RuleError):
    rule: str


@dataclass(frozen=True)
class WrongRefCount(RuleError):
    rule: str
    expected_lines: int
    got_lines: int
    expected_boxes: int
    got_boxes: int


@dataclass(frozen=True)
class WrongFormulaShape(RuleError):
    rule: str
    line: int
    expected_shape: str


@dataclass(frozen=True)
class FormulaMismatch(RuleError):
    rule: str
    expected: Formula
    got: Formula


@dataclass(frozen=True)
class OutOfScope(RuleError):
    rule: str
    referenced_line: int
    from_line: int


@dataclass(frozen=True)
class BadBoxRef(RuleError):
    rule: str
    start: int
    end: int
    reason: str


@dataclass(frozen=True)
class EigenvarViolation(RuleError):
    rule: str
    eigenvar: str
    reason: str


@dataclass(frozen=True)
class MissingExtra(RuleError):
    rule: str
    key: str


@dataclass(frozen=True)
class StructuralError(RuleError):
    reason: str


@dataclass(frozen=True)
class GoalMismatch(RuleError):
    expected: Formula
    got: Formula


@dataclass(frozen=True)
class UnresolvedMeta(RuleError):
    line: int
    meta_name: str


@dataclass(frozen=True)
class MalformedArithmetic(RuleError):
    line: int
    formula: Formula
    reason: str


@dataclass(frozen=True)
class EvaluationFalse(RuleError):
    line: int
    formula: Formula
