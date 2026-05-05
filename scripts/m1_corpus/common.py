"""Shared helpers for M1 corpus generation drivers."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from hlmr.ir.formula import Atom, Equals, Func, Meta, Term
from hlmr.ir.kb import Clause
from hlmr.ir.proof import Proof
from hlmr.ir.serialise import to_json
from hlmr.parse.parser import parse_query
from hlmr.solve import SLDState
from hlmr.unify.substitution import Substitution

_REPO_ROOT = Path(__file__).parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples" / "m1"
_PROOFS = _REPO_ROOT / "proofs" / "m1"


def seq_picker(indices: list[int]) -> Callable[[list[Clause], SLDState], int | None]:
    """Return a picker that steps through a fixed sequence of 0-based indices."""
    it = iter(indices)
    return lambda cs, state: next(it, None)


def _query_metas(goal: Atom | Equals) -> set[str]:
    """Return the set of Meta names that appear directly in a query goal."""
    result: set[str] = set()

    def walk(t: Term) -> None:
        match t:
            case Meta(name=n):
                result.add(n)
            case Func(args=args):
                for a in args:
                    walk(a)

    match goal:
        case Atom(args=args):
            for a in args:
                walk(a)
        case Equals(lhs=lhs, rhs=rhs):
            walk(lhs)
            walk(rhs)
    return result


def _serialize_term(t: Term) -> object:
    """Serialize a Term to its JSON dict representation."""
    match t:
        case Meta(name=n):
            return {"_type": "Meta", "name": n}
        case Func(name=n, args=args):
            return {"_type": "Func", "name": n, "args": [_serialize_term(a) for a in args]}
        case _:
            # Const and Var: use the serialise module's format
            from hlmr.ir.serialise import _term_to_dict  # noqa: PLC0415
            return _term_to_dict(t)


def _serialize_formula(f: object) -> object:
    """Serialize a Formula to its JSON dict representation."""
    from hlmr.ir.serialise import _formula_to_dict  # noqa: PLC0415
    return _formula_to_dict(f)


def save_fixture(
    name: str,
    proof: Proof,
    query_str: str,
    sat_subst: Substitution,
    *,
    kb_path: Path | None = None,
    kb_source: str | None = None,
) -> None:
    """Write proofs/m1/<name>.json and proofs/m1/<name>.meta.json.

    Exactly one of kb_path or kb_source must be provided.
    The sidecar records the original query, the expected witness for
    user-visible metas, a sha256 of the KB source, and the serialized
    final formula (last proof line) for regression testing.
    """
    if (kb_path is None) == (kb_source is None):
        raise ValueError("provide exactly one of kb_path or kb_source")

    _PROOFS.mkdir(parents=True, exist_ok=True)

    # Write proof JSON
    (_PROOFS / f"{name}.json").write_text(to_json(proof) + "\n", encoding="utf-8")

    # Compute KB hash
    if kb_path is not None:
        raw = kb_path.read_text(encoding="utf-8")
        kb_file: str | None = kb_path.name
    else:
        assert kb_source is not None
        raw = kb_source
        kb_file = None
    kb_source_hash = hashlib.sha256(raw.encode()).hexdigest()

    # Extract only the user-visible metas from the original query
    query_goal = parse_query(query_str)
    original_metas = _query_metas(query_goal)
    expected_witness = {
        k: _serialize_term(v)
        for k, v in sat_subst.items()
        if k in original_metas
    }

    # Final formula from the last proof line
    final_formula = _serialize_formula(proof.lines[-1].formula)

    sidecar = {
        "fixture": name,
        "query": query_str,
        "expected_witness": expected_witness,
        "kb_file": kb_file,
        "kb_source_hash": kb_source_hash,
        "final_formula": final_formula,
    }
    (_PROOFS / f"{name}.meta.json").write_text(
        json.dumps(sidecar, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  {name}.json + {name}.meta.json")
