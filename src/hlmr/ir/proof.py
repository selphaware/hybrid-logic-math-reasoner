from __future__ import annotations

from dataclasses import dataclass

from hlmr.ir.formula import Formula
from hlmr.ir.justification import Justification


@dataclass(frozen=True)
class ProofLine:
    number: int
    formula: Formula
    justification: Justification
    box_depth: int


@dataclass(frozen=True)
class Proof:
    lines: tuple[ProofLine, ...]
    goal: Formula | None = None

    def line(self, n: int) -> ProofLine:
        return self.lines[n - 1]

    def prefix(self, n: int) -> Proof:
        return Proof(self.lines[:n], self.goal)
