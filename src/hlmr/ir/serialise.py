from __future__ import annotations

import json

from hlmr.ir.formula import (
    And,
    Atom,
    Bot,
    Const,
    Equals,
    Exists,
    ForAll,
    Formula,
    Func,
    Iff,
    Implies,
    Not,
    Or,
    Term,
    Var,
)
from hlmr.ir.justification import Assumption, Justification, Premise, RuleApp
from hlmr.ir.proof import Proof, ProofLine

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Term serialisation
# ---------------------------------------------------------------------------


def _term_to_dict(t: Term) -> dict:
    match t:
        case Var(name=name):
            return {"_type": "Var", "name": name}
        case Const(value=value):
            return {"_type": "Const", "value": value}
        case Func(name=name, args=args):
            return {
                "_type": "Func",
                "name": name,
                "args": [_term_to_dict(a) for a in args],
            }
        case _:
            raise TypeError(f"Unknown term type: {type(t)}")


def _term_from_dict(d: dict) -> Term:
    match d["_type"]:
        case "Var":
            return Var(d["name"])
        case "Const":
            return Const(d["value"])
        case "Func":
            return Func(d["name"], tuple(_term_from_dict(a) for a in d["args"]))
        case _:
            raise ValueError(f"Unknown term type tag: {d['_type']}")


# ---------------------------------------------------------------------------
# Formula serialisation
# ---------------------------------------------------------------------------


def _formula_to_dict(f: Formula) -> dict:
    match f:
        case Atom(pred=pred, args=args):
            return {
                "_type": "Atom",
                "pred": pred,
                "args": [_term_to_dict(a) for a in args],
            }
        case Equals(lhs=lhs, rhs=rhs):
            return {
                "_type": "Equals",
                "lhs": _term_to_dict(lhs),
                "rhs": _term_to_dict(rhs),
            }
        case Not(body=body):
            return {"_type": "Not", "body": _formula_to_dict(body)}
        case And(left=left, right=right):
            return {
                "_type": "And",
                "left": _formula_to_dict(left),
                "right": _formula_to_dict(right),
            }
        case Or(left=left, right=right):
            return {
                "_type": "Or",
                "left": _formula_to_dict(left),
                "right": _formula_to_dict(right),
            }
        case Implies(left=left, right=right):
            return {
                "_type": "Implies",
                "left": _formula_to_dict(left),
                "right": _formula_to_dict(right),
            }
        case Iff(left=left, right=right):
            return {
                "_type": "Iff",
                "left": _formula_to_dict(left),
                "right": _formula_to_dict(right),
            }
        case Bot():
            return {"_type": "Bot"}
        case ForAll(var=var, body=body):
            return {"_type": "ForAll", "var": var, "body": _formula_to_dict(body)}
        case Exists(var=var, body=body):
            return {"_type": "Exists", "var": var, "body": _formula_to_dict(body)}
        case _:
            raise TypeError(f"Unknown formula type: {type(f)}")


def _formula_from_dict(d: dict) -> Formula:
    match d["_type"]:
        case "Atom":
            return Atom(d["pred"], tuple(_term_from_dict(a) for a in d["args"]))
        case "Equals":
            return Equals(_term_from_dict(d["lhs"]), _term_from_dict(d["rhs"]))
        case "Not":
            return Not(_formula_from_dict(d["body"]))
        case "And":
            return And(_formula_from_dict(d["left"]), _formula_from_dict(d["right"]))
        case "Or":
            return Or(_formula_from_dict(d["left"]), _formula_from_dict(d["right"]))
        case "Implies":
            return Implies(
                _formula_from_dict(d["left"]), _formula_from_dict(d["right"])
            )
        case "Iff":
            return Iff(_formula_from_dict(d["left"]), _formula_from_dict(d["right"]))
        case "Bot":
            return Bot()
        case "ForAll":
            return ForAll(d["var"], _formula_from_dict(d["body"]))
        case "Exists":
            return Exists(d["var"], _formula_from_dict(d["body"]))
        case _:
            raise ValueError(f"Unknown formula type tag: {d['_type']}")


# ---------------------------------------------------------------------------
# RuleApp.extra serialisation
# Values may be Term or Formula objects; wrap with a _type discriminator.
# ---------------------------------------------------------------------------


def _extra_val_to_json(v: object) -> object:
    if isinstance(v, Term):
        return {"_type": "term", "value": _term_to_dict(v)}
    if isinstance(v, Formula):
        return {"_type": "formula", "value": _formula_to_dict(v)}
    return v


def _extra_val_from_json(v: object) -> object:
    if isinstance(v, dict) and "_type" in v:
        match v["_type"]:
            case "term":
                return _term_from_dict(v["value"])
            case "formula":
                return _formula_from_dict(v["value"])
    return v


# ---------------------------------------------------------------------------
# Justification serialisation
# ---------------------------------------------------------------------------


def _just_to_dict(j: Justification) -> dict:
    match j:
        case Premise():
            return {"_type": "Premise"}
        case Assumption():
            return {"_type": "Assumption"}
        case RuleApp(rule=rule, line_refs=line_refs, box_refs=box_refs, extra=extra):
            return {
                "_type": "RuleApp",
                "rule": rule,
                "line_refs": list(line_refs),
                "box_refs": [list(pair) for pair in box_refs],
                "extra": {k: _extra_val_to_json(v) for k, v in extra.items()},
            }
        case _:
            raise TypeError(f"Unknown justification type: {type(j)}")


def _just_from_dict(d: dict) -> Justification:
    match d["_type"]:
        case "Premise":
            return Premise()
        case "Assumption":
            return Assumption()
        case "RuleApp":
            return RuleApp(
                rule=d["rule"],
                line_refs=tuple(d["line_refs"]),
                box_refs=tuple(tuple(pair) for pair in d["box_refs"]),
                extra={
                    k: _extra_val_from_json(v)
                    for k, v in d.get("extra", {}).items()
                },
            )
        case _:
            raise ValueError(f"Unknown justification type tag: {d['_type']}")


# ---------------------------------------------------------------------------
# Proof serialisation
# ---------------------------------------------------------------------------


def _proof_to_dict(p: Proof) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "goal": _formula_to_dict(p.goal) if p.goal is not None else None,
        "lines": [
            {
                "number": line.number,
                "formula": _formula_to_dict(line.formula),
                "justification": _just_to_dict(line.justification),
                "box_depth": line.box_depth,
            }
            for line in p.lines
        ],
    }


def _proof_from_dict(d: dict) -> Proof:
    version = d.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported schema version: {version!r} (expected {SCHEMA_VERSION})"
        )
    goal = _formula_from_dict(d["goal"]) if d.get("goal") is not None else None
    lines = tuple(
        ProofLine(
            number=line["number"],
            formula=_formula_from_dict(line["formula"]),
            justification=_just_from_dict(line["justification"]),
            box_depth=line["box_depth"],
        )
        for line in d["lines"]
    )
    return Proof(lines=lines, goal=goal)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def to_json(p: Proof, indent: int = 2) -> str:
    return json.dumps(_proof_to_dict(p), indent=indent)


def from_json(s: str) -> Proof:
    return _proof_from_dict(json.loads(s))
