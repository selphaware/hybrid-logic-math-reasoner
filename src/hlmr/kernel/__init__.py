from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import (
    BadBoxRef,
    CheckFailure,
    CheckResult,
    EigenvarViolation,
    FormulaMismatch,
    GoalMismatch,
    MissingExtra,
    OutOfScope,
    RuleError,
    StructuralError,
    UnknownRule,
    Verified,
    WrongFormulaShape,
    WrongRefCount,
)
from hlmr.kernel.rules import RULES

__all__ = [
    "check_proof",
    "RULES",
    "Verified",
    "CheckFailure",
    "CheckResult",
    "RuleError",
    "UnknownRule",
    "WrongRefCount",
    "WrongFormulaShape",
    "FormulaMismatch",
    "OutOfScope",
    "BadBoxRef",
    "EigenvarViolation",
    "MissingExtra",
    "StructuralError",
    "GoalMismatch",
]
