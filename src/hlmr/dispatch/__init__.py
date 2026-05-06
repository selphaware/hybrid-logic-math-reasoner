"""Minimal dispatch stub for M2.

This module will grow to include Dispatcher, DispatchResult, outcome
dataclasses, RouteTarget, and ClassifyDecision as Tasks B and C land.
For now it exports only RouteTarget so that solve/sld.py can import
the enum without the full dispatcher implementation being present.
"""

from __future__ import annotations

from enum import Enum


class RouteTarget(Enum):
    KB = "kb"
    Z3 = "z3"
    SYMPY = "sympy"
    REJECTED = "rejected"


__all__ = ["RouteTarget"]
