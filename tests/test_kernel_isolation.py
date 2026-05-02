"""Kernel isolation guardrail (prd_milestone_0.md §4, §9.1).

Walks kernel/*.py, parses imports with ast, and asserts every imported
module is either stdlib, hlmr.ir.*, or hlmr.kernel.* (intra-kernel).

The invariant being enforced: the kernel package must never import from
untrusted modules (hlmr.unify, hlmr.solve, hlmr.parse, etc.). Intra-kernel
imports are permitted because all kernel files are within the trust boundary.
Never add untrusted modules to _is_allowed().
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_KERNEL_DIR = Path(__file__).parent.parent / "src" / "hlmr" / "kernel"

_STDLIB_MODULES = sys.stdlib_module_names  # Python 3.10+


def _is_allowed(module_name: str) -> bool:
    """True iff module_name is in the kernel trust perimeter.

    Allowed: stdlib, hlmr.ir.*, hlmr.kernel.* (intra-kernel).
    Forbidden: everything else (hlmr.unify, hlmr.solve, hlmr.parse, etc.)
    """
    root = module_name.split(".")[0]
    if root in _STDLIB_MODULES:
        return True
    if module_name == "hlmr.ir" or module_name.startswith("hlmr.ir."):
        return True
    if module_name == "hlmr.kernel" or module_name.startswith("hlmr.kernel."):
        return True
    return False


def _collect_imports(source: str) -> list[str]:
    """Return all top-level module names imported in source."""
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                modules.append(node.module)
    return modules


def _kernel_python_files() -> list[Path]:
    return sorted(_KERNEL_DIR.glob("*.py"))


@pytest.mark.parametrize("path", _kernel_python_files(), ids=lambda p: p.name)
def test_kernel_file_imports_only_trusted(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    modules = _collect_imports(source)
    violations = [m for m in modules if not _is_allowed(m)]
    assert not violations, (
        f"{path.name} imports untrusted modules outside kernel/ir/stdlib: {violations}\n"
        "The kernel must only import from hlmr.ir, hlmr.kernel, and stdlib.\n"
        "DO NOT add untrusted modules to _is_allowed() to fix this."
    )
