from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Premise:
    pass


@dataclass(frozen=True)
class Assumption:
    pass


@dataclass(frozen=True)
class RuleApp:
    rule: str
    line_refs: tuple[int, ...] = ()
    box_refs: tuple[tuple[int, int], ...] = ()
    # extra holds rule-specific data (eigenvar, term, template, etc.).
    # Excluded from hash because dict isn't hashable; still included in __eq__.
    extra: dict = field(default_factory=dict, hash=False)  # type: ignore[assignment]


Justification = Premise | Assumption | RuleApp
