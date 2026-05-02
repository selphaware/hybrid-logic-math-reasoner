"""Re-export of Meta from formula.py.

Meta is defined in formula.py alongside the other Term subclasses
so the closed Term hierarchy lives in one file. This module exists
to preserve the import path documented in the M1 PRD §5.1.
"""

from hlmr.ir.formula import Meta

__all__ = ["Meta"]
