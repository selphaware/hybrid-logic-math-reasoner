from __future__ import annotations

from hlmr.ir.proof import Proof


def is_accessible(m: int, n: int, proof: Proof) -> bool:
    """True iff line m is accessible from line n (m < n).

    Line m is accessible from n iff for every k with m < k <= n,
    box_depth(k) >= box_depth(m). Equivalently: m's box is still open at n.
    """
    if m >= n:
        return False
    depth_m = proof.line(m).box_depth
    for k in range(m + 1, n + 1):
        if proof.line(k).box_depth < depth_m:
            return False
    return True


def is_box(start: int, end: int, proof: Proof, from_line: int) -> tuple[bool, str]:
    """Check whether (start, end) is a well-formed, discharged box reference
    as seen from from_line.

    Returns (True, "") on success, (False, reason) on failure.

    Conditions (prd_milestone_0.md §7.2):
    - 1 <= start <= end < from_line
    - box_depth(start) > 0
    - For all k in [start, end]: box_depth(k) >= box_depth(start)
    - box_depth(from_line) < box_depth(start)  (box is discharged)
    """
    if not (1 <= start <= end < from_line):
        return False, f"box ({start},{end}) out of range for line {from_line}"
    depth_start = proof.line(start).box_depth
    if depth_start == 0:
        return False, f"box start line {start} is at depth 0 (not inside a box)"
    for k in range(start, end + 1):
        if proof.line(k).box_depth < depth_start:
            return False, (
                f"line {k} inside box ({start},{end}) has depth "
                f"{proof.line(k).box_depth} < {depth_start}"
            )
    depth_n = proof.line(from_line).box_depth
    if depth_n >= depth_start:
        return False, (
            f"box ({start},{end}) not discharged before line {from_line}: "
            f"depth {depth_n} >= {depth_start}"
        )
    return True, ""


def current_depth(proof: Proof) -> int:
    """Box depth of the last line, or 0 for an empty proof."""
    if not proof.lines:
        return 0
    return proof.lines[-1].box_depth
