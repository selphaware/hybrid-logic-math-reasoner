"""CLI entry point: `python -m hlmr check <proof.json>` and `... show ...`."""

from __future__ import annotations

import argparse
import json
import sys

from hlmr.ir.justification import Assumption, Premise, RuleApp
from hlmr.ir.proof import Proof
from hlmr.ir.serialise import from_json
from hlmr.kernel import check_proof
from hlmr.kernel.errors import CheckFailure, Verified

# ---------------------------------------------------------------------------
# Fitch-style ASCII renderer
# ---------------------------------------------------------------------------

_BOX_CHAR = "|"
_INDENT = "  "


def _just_str(line_number: int, proof: Proof) -> str:
    line = proof.line(line_number)
    j = line.justification
    match j:
        case Premise():
            return "Premise"
        case Assumption():
            return "Assumption"
        case RuleApp(rule=rule, line_refs=lr, box_refs=br, extra=ex):
            parts = [rule]
            if lr:
                parts.append(", ".join(str(r) for r in lr))
            if br:
                box_strs = ", ".join(f"({s},{e})" for s, e in br)
                parts.append(box_strs)
            if ex:
                ex_str = ", ".join(f"{k}={v!r}" for k, v in ex.items())
                parts.append(f"[{ex_str}]")
            return " ".join(parts)
        case _:
            return str(j)


def render_fitch(proof: Proof) -> str:
    lines_out: list[str] = []
    n = len(proof.lines)
    width = len(str(n))  # line number column width

    for i, line in enumerate(proof.lines):
        depth = line.box_depth
        prev_depth = proof.lines[i - 1].box_depth if i > 0 else 0

        # Draw box separators
        prefix = _BOX_CHAR * depth + _INDENT * depth

        # Opening separator: depth increased
        if depth > prev_depth:
            outer = _BOX_CHAR * (depth - 1) + _INDENT * (depth - 1)
            sep_line = " " * (width + 2) + outer + _BOX_CHAR + "-" * 30
            lines_out.append(sep_line)

        formula_str = repr(line.formula)
        just_str = _just_str(line.number, proof)
        num_str = str(line.number).rjust(width)
        lines_out.append(f"{num_str}. {prefix}{formula_str:<35}  {just_str}")

    # Closing separator for any open box at end (shouldn't happen in valid proof)
    return "\n".join(lines_out)


# ---------------------------------------------------------------------------
# check subcommand
# ---------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    path: str = args.proof
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"hlmr: cannot open {path!r}: {e}", file=sys.stderr)
        return 2

    try:
        proof = from_json(text)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"hlmr: malformed proof file: {e}", file=sys.stderr)
        return 2

    result = check_proof(proof)
    if isinstance(result, Verified):
        print(f"verified ({len(proof.lines)} lines)")
        return 0
    else:
        assert isinstance(result, CheckFailure)
        reason_type = type(result.reason).__name__
        print(f"rejected at line {result.line}: {reason_type}: {result.reason}")
        return 1


# ---------------------------------------------------------------------------
# show subcommand
# ---------------------------------------------------------------------------


def _cmd_show(args: argparse.Namespace) -> int:
    path: str = args.proof
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"hlmr: cannot open {path!r}: {e}", file=sys.stderr)
        return 2

    try:
        proof = from_json(text)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"hlmr: malformed proof file: {e}", file=sys.stderr)
        return 2

    print(render_fitch(proof))
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _cmd_repl(args: argparse.Namespace) -> int:
    from hlmr.repl import run_repl

    run_repl(no_log=args.no_log)
    return 0


def _cmd_regenerate_corpus(args: argparse.Namespace) -> int:
    import sys
    from pathlib import Path

    _repo_root = Path(__file__).parent.parent.parent
    _scripts = str(_repo_root / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from m1_corpus.regenerate import main  # noqa: PLC0415

    main()
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from hlmr.demos import DEMOS

    name: str | None = getattr(args, "name", None)
    if not name:
        print("Available demos:")
        for n in DEMOS:
            print(f"  {n}")
        return 0
    if name not in DEMOS:
        available = ", ".join(DEMOS)
        print(f"unknown demo: {name!r}. Available: {available}", file=sys.stderr)
        return 1
    _, proof = DEMOS[name]()
    print(render_fitch(proof))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hlmr",
        description="HLMR — Hybrid Logic-Math Reasoner",
    )
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="verify a proof JSON file")
    p_check.add_argument("proof", metavar="PROOF.JSON")

    p_show = sub.add_parser("show", help="pretty-print a proof in Fitch style")
    p_show.add_argument("proof", metavar="PROOF.JSON")

    p_repl = sub.add_parser("repl", help="open the interactive REPL")
    p_repl.add_argument(
        "--no-log",
        action="store_true",
        default=False,
        help="disable JSONL session logging",
    )

    p_demo = sub.add_parser("demo", help="run a built-in demo and print its proof")
    p_demo.add_argument(
        "name",
        nargs="?",
        default=None,
        metavar="NAME",
        help="demo name (omit to list available demos)",
    )

    sub.add_parser(
        "regenerate-corpus",
        help="regenerate all proofs/m1/ fixtures and sidecar metadata",
    )

    args = parser.parse_args()

    if args.command == "check":
        sys.exit(_cmd_check(args))
    elif args.command == "show":
        sys.exit(_cmd_show(args))
    elif args.command == "repl":
        sys.exit(_cmd_repl(args))
    elif args.command == "demo":
        sys.exit(_cmd_demo(args))
    elif args.command == "regenerate-corpus":
        sys.exit(_cmd_regenerate_corpus(args))
    else:
        parser.print_help()
        sys.exit(2)
