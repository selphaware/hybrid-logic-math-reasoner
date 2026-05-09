"""Pure command parsing for the HLMR REPL. No I/O here."""
from __future__ import annotations

from dataclasses import dataclass, field

from hlmr.parse import ParseError, parse_clause, parse_query


class CommandError(Exception):
    """Raised on malformed command input. Caught by the REPL loop."""


@dataclass(frozen=True)
class Command:
    """Parsed REPL command.

    type is one of: 'noop', 'help', 'load', 'save', 'show_kb', 'show_last',
    'export', 'quit', 'query_mode', 'edit_mode', 'clause', 'query',
    'pick', 'candidates', 'back', 'abort', 'solver'.
    """

    type: str
    args: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_command(line: str, in_query_mode: bool) -> Command:
    """Parse one line of input into a Command.

    in_query_mode controls whether bare text is a clause or a query keyword.
    Raises CommandError on malformed input.
    Empty / whitespace-only lines return Command('noop', {}).
    """
    stripped = line.strip()

    if not stripped:
        return Command("noop", {})

    # Meta-commands always start with ':'
    if stripped.startswith(":"):
        return _parse_meta(stripped[1:].strip())

    # ?- prefix works in both modes
    if stripped.startswith("?-"):
        try:
            goal = parse_query(stripped)
        except ParseError as e:
            raise CommandError(str(e)) from e
        return Command("query", {"goal": goal})

    if in_query_mode:
        return _parse_query_mode(stripped)

    return _parse_kb_mode(stripped)


# ---------------------------------------------------------------------------
# Private parsers
# ---------------------------------------------------------------------------


def _parse_meta(rest: str) -> Command:
    parts = rest.split(None, 1)
    if not parts:
        raise CommandError("empty command after ':'")

    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None

    _no_arg = {"help", "quit", "query", "edit", "solver"}
    if verb in _no_arg:
        if arg is not None:
            raise CommandError(f":{verb} takes no arguments")
        _map = {
            "help": "help",
            "quit": "quit",
            "query": "query_mode",
            "edit": "edit_mode",
            "solver": "solver",
        }
        return Command(_map[verb], {})

    if verb == "load":
        if not arg:
            raise CommandError(":load requires a file path")
        return Command("load", {"path": arg.strip()})

    if verb == "save":
        if not arg:
            raise CommandError(":save requires a file path")
        return Command("save", {"path": arg.strip()})

    if verb == "export":
        if not arg:
            raise CommandError(":export requires a file path")
        return Command("export", {"path": arg.strip()})

    if verb == "show":
        if not arg:
            raise CommandError(":show requires 'kb' or 'last'")
        what = arg.strip().lower()
        if what == "kb":
            return Command("show_kb", {})
        if what == "last":
            return Command("show_last", {})
        raise CommandError(f":show expects 'kb' or 'last', got {arg!r}")

    raise CommandError(f"unknown command :{verb!r}")


def _parse_query_mode(stripped: str) -> Command:
    lower = stripped.lower()

    if lower == "candidates":
        return Command("candidates", {})
    if lower == "back":
        return Command("back", {})
    if lower == "abort":
        return Command("abort", {})

    # "pick N" or bare "N"
    token = lower
    if token.startswith("pick"):
        token = token[4:].strip()

    if token.isdigit():
        n = int(token)
        if n < 1:
            raise CommandError("candidate index must be >= 1")
        return Command("pick", {"index": n})

    raise CommandError(
        f"in query mode use: pick N, N, candidates, back, abort, or ?- goal.; got {stripped!r}"
    )


def _parse_kb_mode(stripped: str) -> Command:
    try:
        clause = parse_clause(stripped)
    except ParseError as e:
        raise CommandError(str(e)) from e
    return Command("clause", {"clause": clause})
