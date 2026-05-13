"""Tests for src/hlmr/repl/commands.py — pure parsing, no I/O."""
from __future__ import annotations

import pytest

from hlmr.ir.formula import Atom, Const, Meta, Var
from hlmr.ir.kb import Clause
from hlmr.repl.commands import Command, CommandError, parse_command

# ---------------------------------------------------------------------------
# Noop / empty
# ---------------------------------------------------------------------------


def test_empty_line_is_noop() -> None:
    assert parse_command("", False).type == "noop"


def test_whitespace_only_is_noop() -> None:
    assert parse_command("   \t  ", False).type == "noop"


def test_empty_line_query_mode_is_noop() -> None:
    assert parse_command("", True).type == "noop"


# ---------------------------------------------------------------------------
# Meta-commands — no-arg forms
# ---------------------------------------------------------------------------


def test_help_command() -> None:
    assert parse_command(":help", False).type == "help"


def test_quit_command() -> None:
    assert parse_command(":quit", False).type == "quit"


def test_query_mode_transition() -> None:
    cmd = parse_command(":query", False)
    assert cmd.type == "query_mode"


def test_edit_mode_transition() -> None:
    cmd = parse_command(":edit", True)
    assert cmd.type == "edit_mode"


def test_quit_with_trailing_arg_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":quit now", False)


def test_unknown_meta_command_raises() -> None:
    with pytest.raises(CommandError, match="unknown command"):
        parse_command(":foo", False)


def test_bare_colon_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":", False)


# ---------------------------------------------------------------------------
# :load / :save / :export
# ---------------------------------------------------------------------------


def test_load_command() -> None:
    cmd = parse_command(":load /some/path.pl", False)
    assert cmd.type == "load"
    assert cmd.args["path"] == "/some/path.pl"


def test_load_missing_path_raises() -> None:
    with pytest.raises(CommandError, match="requires a file path"):
        parse_command(":load", False)


def test_save_command() -> None:
    cmd = parse_command(":save out.pl", False)
    assert cmd.type == "save"
    assert cmd.args["path"] == "out.pl"


def test_save_missing_path_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":save", False)


def test_export_command() -> None:
    cmd = parse_command(":export proof.json", False)
    assert cmd.type == "export"
    assert cmd.args["path"] == "proof.json"


def test_export_missing_path_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":export", False)


# ---------------------------------------------------------------------------
# :show
# ---------------------------------------------------------------------------


def test_show_kb() -> None:
    assert parse_command(":show kb", False).type == "show_kb"


def test_show_last() -> None:
    assert parse_command(":show last", False).type == "show_last"


def test_show_kb_extra_spaces() -> None:
    assert parse_command(":show   kb", False).type == "show_kb"


def test_show_bad_arg_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":show foo", False)


def test_show_missing_arg_raises() -> None:
    with pytest.raises(CommandError):
        parse_command(":show", False)


# ---------------------------------------------------------------------------
# ?- queries (both modes)
# ---------------------------------------------------------------------------


def test_query_in_kb_mode() -> None:
    cmd = parse_command("?- mortal(socrates).", False)
    assert cmd.type == "query"
    # M2: cmd.args["goals"] is a tuple (1-element for single-goal queries).
    assert cmd.args["goals"] == (Atom("mortal", (Const("socrates"),)),)


def test_query_in_query_mode() -> None:
    cmd = parse_command("?- mortal(socrates).", True)
    assert cmd.type == "query"


def test_query_with_meta() -> None:
    cmd = parse_command("?- ancestor(?X, alice).", False)
    assert cmd.type == "query"
    from hlmr.ir.formula import Atom, Const, Meta
    # M2: cmd.args["goals"] is a tuple (1-element for single-goal queries).
    assert cmd.args["goals"] == (Atom("ancestor", (Meta("?X"), Const("alice"))),)


def test_query_bad_syntax_raises() -> None:
    with pytest.raises(CommandError):
        parse_command("?- .", False)


# ---------------------------------------------------------------------------
# KB mode: clauses
# ---------------------------------------------------------------------------


def test_clause_fact_in_kb_mode() -> None:
    cmd = parse_command("human(socrates).", False)
    assert cmd.type == "clause"
    c = cmd.args["clause"]
    assert isinstance(c, Clause)
    assert c.head == Atom("human", (Const("socrates"),))
    assert c.body == ()


def test_clause_rule_in_kb_mode() -> None:
    cmd = parse_command("mortal(X) :- human(X).", False)
    assert cmd.type == "clause"
    c = cmd.args["clause"]
    assert c.head == Atom("mortal", (Var("X"),))
    assert c.body == (Atom("human", (Var("X"),)),)


def test_clause_bad_syntax_raises() -> None:
    with pytest.raises(CommandError):
        parse_command("not valid syntax at all", False)


def test_bare_numeric_in_kb_mode_raises() -> None:
    with pytest.raises(CommandError):
        parse_command("1", False)


def test_back_in_kb_mode_raises() -> None:
    with pytest.raises(CommandError):
        parse_command("back", False)


# ---------------------------------------------------------------------------
# Query mode: pick / candidates / back / abort
# ---------------------------------------------------------------------------


def test_pick_bare_numeric() -> None:
    cmd = parse_command("1", True)
    assert cmd.type == "pick"
    assert cmd.args["index"] == 1


def test_pick_bare_two_digit() -> None:
    cmd = parse_command("12", True)
    assert cmd.type == "pick"
    assert cmd.args["index"] == 12


def test_pick_keyword_prefix() -> None:
    cmd = parse_command("pick 2", True)
    assert cmd.type == "pick"
    assert cmd.args["index"] == 2


def test_candidates_command() -> None:
    assert parse_command("candidates", True).type == "candidates"


def test_back_in_query_mode() -> None:
    assert parse_command("back", True).type == "back"


def test_abort_in_query_mode() -> None:
    assert parse_command("abort", True).type == "abort"


def test_unknown_in_query_mode_raises() -> None:
    with pytest.raises(CommandError):
        parse_command("frob", True)
