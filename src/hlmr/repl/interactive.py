"""REPL main loop. Wires parser, KB, SLD engine, renderer, and recorder."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

from prompt_toolkit import PromptSession
from prompt_toolkit.output import DummyOutput

from hlmr.dispatch import MultipleSolutions, NoSolution, OutsideFragment, RouteTarget, Underdetermined, UniqueSolution
from hlmr.dispatch.route import Dispatcher, DispatchResult
from hlmr.ir.formula import Atom, Equals, Func, Meta, Term, Var
from hlmr.ir.formula import Const
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof
from hlmr.ir.serialise import to_json
from hlmr.kernel.check import check_proof
from hlmr.kernel.errors import Verified
from hlmr.log import SessionRecorder
from hlmr.parse import ParseError, parse_file
from hlmr.repl.commands import Command, CommandError, parse_command
from hlmr.repl.outcome_format import format_classify_decision, format_outcome, format_substitution
from hlmr.solve import _is_ground, _query_meta_names
from hlmr.solve.render import RenderError, _saturate, render
from hlmr.solve.sld import DispatcherResolvedStep, FreshNameGen, SLDState, candidates, resolve
from hlmr.unify.substitution import Substitution, apply_to_formula, apply_to_term, compose

# ---------------------------------------------------------------------------
# Mutable REPL state
# ---------------------------------------------------------------------------


class _ReplState:
    def __init__(self) -> None:
        self.kb: KnowledgeBase = KnowledgeBase(())
        self.last_proof: Proof | None = None
        self.last_subst: Substitution | None = None
        self.in_query_mode: bool = False
        self.dispatcher: Dispatcher | None = None


# ---------------------------------------------------------------------------
# ASCII surface-syntax formatters
# ---------------------------------------------------------------------------


def _fmt_term(t: Term) -> str:
    match t:
        case Var(name=n):
            return n
        case Meta(name=n):
            return n
        case Const(value=v):
            return str(v)
        case Func(name=n, args=args):
            return f"{n}({', '.join(_fmt_term(a) for a in args)})"
    return repr(t)  # pragma: no cover


def _fmt_literal(f: Atom | Equals) -> str:
    match f:
        case Atom(pred=p, args=()):
            return p
        case Atom(pred=p, args=args):
            return f"{p}({', '.join(_fmt_term(a) for a in args)})"
        case Equals(lhs=lhs, rhs=rhs):
            return f"{_fmt_term(lhs)} = {_fmt_term(rhs)}"
    return repr(f)  # pragma: no cover


def _fmt_clause(c: Clause) -> str:
    head = _fmt_literal(c.head)
    if c.body:
        body = ", ".join(_fmt_literal(b) for b in c.body)
        return f"{head} :- {body}."
    return f"{head}."


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------

_HELP = """\
Commands:
  :help              show this help
  :load <path>       load clauses from a .pl file
  :save <path>       save current KB to a .pl file
  :show kb           display the knowledge base
  :show last         display last proof in Fitch style
  :export <path>     save last proof to JSON
  :solver            show most recent dispatcher activity (M2)
  :quit              exit
  :query             switch to query mode
  :edit              switch back to KB mode

In KB mode, any line ending in '.' is a clause to add.
In query mode:
  ?- goal.           start a new query
  pick N  or  N      choose candidate clause N (KB goals only)
  candidates         re-display candidates
  back               undo last KB pick
  abort              cancel current query

M2 arithmetic goals (plus, minus, times, divides, root_of) are
dispatched automatically to Z3/SymPy — no pick required."""


# ---------------------------------------------------------------------------
# Query sub-loop (owns the SLD stack; supports 'back')
# ---------------------------------------------------------------------------


def _show_candidates(sld_state: SLDState, cs: list[Clause], stdout: IO) -> None:
    goal = sld_state.goals[0]
    applied = apply_to_formula(sld_state.subst, goal)
    n_total = len(sld_state.goals)
    print(f"\nGoal ({n_total} remaining): {_fmt_literal(applied)}", file=stdout)
    print("Candidates:", file=stdout)
    for i, c in enumerate(cs, 1):
        kind = "fact" if not c.body else "rule"
        print(f"  {i}. {_fmt_clause(c)}  ({kind}, {c.name})", file=stdout)


def _solver_picker_interactive(
    outcome: MultipleSolutions,
    session: PromptSession,
    stdout: IO,
) -> int | None:
    """Prompt the user to pick one solution from a MultipleSolutions outcome."""
    print("\nMultiple solutions found. Pick one:", file=stdout)
    for i, sol in enumerate(outcome.solutions):
        print(f"  [{i}] {format_substitution(sol)}", file=stdout)
    while True:
        try:
            raw = session.prompt("choice: ")
        except (EOFError, KeyboardInterrupt):
            return None
        stripped = raw.strip()
        if not stripped:
            print("  Aborted.", file=stdout)
            return None
        if stripped.isdigit():
            idx = int(stripped)
            if 0 <= idx < len(outcome.solutions):
                return idx
            print(f"  Choose 0–{len(outcome.solutions) - 1}.", file=stdout)
        else:
            print("  Enter a number or press Enter to abort.", file=stdout)


def _run_query_loop(
    goals: tuple[Atom | Equals, ...],
    repl_state: _ReplState,
    session: PromptSession,
    recorder: SessionRecorder,
    stdout: IO,
) -> None:
    """Execute one manual SLD query.  Updates repl_state.last_proof on success.

    M2 extension: arithmetic goals (Z3/SYMPY/REJECTED) are dispatched
    automatically when a Dispatcher is available. KB goals use the manual
    pick loop as before. 'back' only undoes KB picks. Multi-goal queries
    (`?- g1, g2, g3.`) are accepted as a tuple of goals.
    """
    kb = repl_state.kb
    dispatcher = repl_state.dispatcher
    gen = FreshNameGen()
    sld = SLDState(goals=goals, subst={}, history=())
    stack: list[SLDState] = []  # for 'back' (KB steps only)

    # Recorder logs the first goal; M2 v2 events (emitted by the dispatcher)
    # capture per-goal classify/route info for multi-goal queries.
    recorder.query_start(goals[0])

    while sld.goals:
        current = sld.goals[0]

        # M2: classify current goal if dispatcher is available.
        # Auto-dispatch Z3/SYMPY goals. For REJECTED goals: dispatch only if
        # the rejection has a meaningful arithmetic reason (TRANSCENDENTAL,
        # CONTESTED_CONVENTION, NON_LINEAR_BEYOND_SYMPY) — these produce
        # informative OutsideFragment messages. UNRECOGNISED_SHAPE rejections
        # fall through to the KB path so users see "No matching clauses" for
        # predicates that are simply not in the KB (preserves M1 UX).
        if dispatcher is not None:
            from hlmr.dispatch import OutsideFragmentReason
            decision = dispatcher.classify(current, sld.subst)
            _meaningful_rejection = (
                decision.target == RouteTarget.REJECTED
                and decision.reason
                in (
                    OutsideFragmentReason.TRANSCENDENTAL,
                    OutsideFragmentReason.CONTESTED_CONVENTION,
                    OutsideFragmentReason.NON_LINEAR_BEYOND_SYMPY,
                )
            )
            if decision.target in (RouteTarget.Z3, RouteTarget.SYMPY) or _meaningful_rejection:
                # Arithmetic goal — dispatch immediately, no user pick.
                applied = apply_to_formula(sld.subst, current)
                assert isinstance(applied, (Atom, Equals))
                print(f"\nDispatching: {_fmt_literal(applied)} ({decision.target.value})", file=stdout)
                result = dispatcher.dispatch(current, sld.subst)

                if isinstance(result.outcome, (OutsideFragment,)):
                    print(
                        f"\nQuery rejected: {format_outcome(result.outcome)}",
                        file=stdout,
                    )
                    recorder.query_end("abort")
                    return

                if isinstance(result.outcome, NoSolution):
                    print("\nNo solution for this arithmetic goal.", file=stdout)
                    recorder.query_end("no_candidates")
                    return

                if isinstance(result.outcome, Underdetermined):
                    partial = _saturate(result.outcome.partial_binding)
                    print(
                        f"\nQuery underdetermined: {format_outcome(result.outcome)}",
                        file=stdout,
                    )
                    recorder.query_end("no_candidates")
                    return

                if isinstance(result.outcome, MultipleSolutions):
                    chosen = _solver_picker_interactive(result.outcome, session, stdout)
                    if chosen is None:
                        recorder.query_end("abort")
                        return
                    binding = result.outcome.solutions[chosen]
                    step = result.outcome.steps[chosen]
                elif isinstance(result.outcome, UniqueSolution):
                    binding = result.outcome.binding
                    step = result.step
                    if step is None:
                        # Shouldn't happen for UniqueSolution, but be safe.
                        print("\nInternal: missing step for UniqueSolution.", file=stdout)
                        recorder.query_end("abort")
                        return
                else:
                    # InfinitelyManySolutions or unknown — treat as underdetermined.
                    print(f"\n{format_outcome(result.outcome)}", file=stdout)
                    recorder.query_end("no_candidates")
                    return

                # Advance the SLD state with the dispatcher step.
                new_subst = compose(sld.subst, binding)
                sld = SLDState(
                    goals=sld.goals[1:],
                    subst=new_subst,
                    history=sld.history + (step,),
                )
                continue  # next goal

        # KB goal (or no dispatcher) — manual pick.
        cs = candidates(sld, kb)
        if not cs:
            print("\nNo matching clauses for current goal.", file=stdout)
            recorder.query_end("no_candidates")
            return

        _show_candidates(sld, cs, stdout)

        # Inner pick loop — repeats until the user commits a pick or back
        picked = False
        while not picked:
            try:
                raw = session.prompt("> ")
            except (EOFError, KeyboardInterrupt):
                recorder.query_end("abort")
                return

            try:
                cmd = parse_command(raw, in_query_mode=True)
            except CommandError as e:
                print(f"  Error: {e}", file=stdout)
                continue

            if cmd.type == "pick":
                idx = int(cmd.args["index"]) - 1  # convert to 0-based
                if idx < 0 or idx >= len(cs):
                    print(f"  Choose 1–{len(cs)}.", file=stdout)
                    continue
                before = sld
                new_sld = resolve(sld, cs[idx], gen)
                if new_sld is None:
                    print("  Unification failed — try another candidate.", file=stdout)
                    continue
                recorder.pick(before, new_sld, idx, cs[idx].name)
                stack.append(before)
                sld = new_sld
                picked = True

            elif cmd.type == "candidates":
                _show_candidates(sld, cs, stdout)

            elif cmd.type == "back":
                if not stack:
                    print("  Nothing to undo.", file=stdout)
                else:
                    sld = stack.pop()
                    picked = True  # exit inner loop; outer re-shows candidates

            elif cmd.type == "abort":
                recorder.query_end("abort")
                return

            elif cmd.type == "noop":
                pass

            else:
                print("  Use: pick N, N, candidates, back, abort.", file=stdout)

    # All goals exhausted — check for underdetermined result before render.
    # For multi-goal queries, the query metas are the union over all goals.
    _sat_pre = _saturate(sld.subst)
    _qmetas: set[str] = set()
    for _g in goals:
        _qmetas |= _query_meta_names(_g)
    if any(not _is_ground(apply_to_term(_sat_pre, Meta(n))) for n in _qmetas):
        sat_str = format_substitution(_sat_pre)
        print(
            f"\nQuery underdetermined: substitution found but no ground witness.\n"
            f"Bindings: {sat_str}",
            file=stdout,
        )
        recorder.query_end("no_candidates")
        return

    try:
        # The M2 renderer accepts a tuple of goals; for single-goal queries,
        # pass the tuple as-is — the renderer handles the 1-element case.
        render_query: Atom | Equals | tuple[Atom | Equals, ...] = (
            goals[0] if len(goals) == 1 else goals
        )
        proof = render(sld, kb, render_query)
    except RenderError as e:
        print(f"\nRender error: {e}", file=stdout)
        recorder.query_end("render_error")
        return

    check_result = check_proof(proof)
    if not isinstance(check_result, Verified):
        print("\nWarning: kernel rejected rendered proof.", file=stdout)
        recorder.query_end("render_error")
        return

    sat = _saturate(sld.subst)
    repl_state.last_proof = proof
    repl_state.last_subst = sat

    if sat:
        b_str = ", ".join(f"{k} = {_fmt_term(v)}" for k, v in sorted(sat.items()))
        print(f"\nSolved: {b_str}", file=stdout)
    else:
        print("\nSolved.", file=stdout)
    print(f"Proof: {len(proof.lines)} lines, kernel-verified.", file=stdout)
    print("Type ':show last' to display, ':export proof.json' to save.", file=stdout)

    recorder.query_end("success", final_subst=sat, proof=proof)


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------


def _do_load(path: str, state: _ReplState, recorder: SessionRecorder, stdout: IO) -> None:
    try:
        kb = parse_file(path)
    except (OSError, ParseError) as e:
        print(f"  Error loading {path!r}: {e}", file=stdout)
        return
    for clause in kb.clauses:
        state.kb = KnowledgeBase(state.kb.clauses + (clause,))
        recorder.kb_add(clause)
    if state.dispatcher is not None:
        state.dispatcher.kb = state.kb
    print(f"  Loaded {len(kb.clauses)} clause(s) from {path!r}.", file=stdout)


def _do_save(path: str, state: _ReplState, stdout: IO) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            for clause in state.kb.clauses:
                f.write(_fmt_clause(clause) + "\n")
        print(f"  Saved {len(state.kb.clauses)} clause(s) to {path!r}.", file=stdout)
    except OSError as e:
        print(f"  Error saving: {e}", file=stdout)


def _do_export(path: str, state: _ReplState, stdout: IO) -> None:
    if state.last_proof is None:
        print("  No proof to export. Run a successful query first.", file=stdout)
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(to_json(state.last_proof))
        print(f"  Exported proof to {path!r}.", file=stdout)
    except OSError as e:
        print(f"  Error exporting: {e}", file=stdout)


def _do_show_kb(state: _ReplState, stdout: IO) -> None:
    if not state.kb.clauses:
        print("  KB is empty.", file=stdout)
        return
    for clause in state.kb.clauses:
        print(f"  {clause.name}: {_fmt_clause(clause)}", file=stdout)


def _do_show_last(state: _ReplState, stdout: IO) -> None:
    if state.last_proof is None:
        print("  No proof yet. Run a successful query first.", file=stdout)
        return
    from hlmr.cli import render_fitch

    print(render_fitch(state.last_proof), file=stdout)


def _do_solver(state: _ReplState, stdout: IO) -> None:
    """Show most recent dispatcher activity (:solver command)."""
    d = state.dispatcher
    if d is None:
        print("  No dispatcher active (M2 solvers not initialised).", file=stdout)
        return
    result = d.last_dispatch_result
    if result is None:
        print("  No dispatch result yet. Issue an arithmetic query first.", file=stdout)
        return
    print(f"  Classification: {format_classify_decision(result.decision)}", file=stdout)
    print(f"  Outcome: {format_outcome(result.outcome)}", file=stdout)
    if d.last_outside_fragment is not None:
        print(f"  Outside-fragment: {format_outcome(d.last_outside_fragment)}", file=stdout)


def _dispatch(
    cmd: Command,
    state: _ReplState,
    session: PromptSession,
    recorder: SessionRecorder,
    stdout: IO,
) -> bool:
    """Dispatch a top-level command. Returns False on :quit."""
    if cmd.type == "noop":
        pass
    elif cmd.type == "help":
        print(_HELP, file=stdout)
    elif cmd.type == "quit":
        return False
    elif cmd.type == "load":
        _do_load(str(cmd.args["path"]), state, recorder, stdout)
    elif cmd.type == "save":
        _do_save(str(cmd.args["path"]), state, stdout)
    elif cmd.type == "show_kb":
        _do_show_kb(state, stdout)
    elif cmd.type == "show_last":
        _do_show_last(state, stdout)
    elif cmd.type == "export":
        _do_export(str(cmd.args["path"]), state, stdout)
    elif cmd.type == "query_mode":
        state.in_query_mode = True
        print("Switched to query mode. Type '?- goal.' to query.", file=stdout)
    elif cmd.type == "edit_mode":
        state.in_query_mode = False
        print("Switched to KB mode.", file=stdout)
    elif cmd.type == "clause":
        clause = cmd.args["clause"]
        assert isinstance(clause, Clause)
        state.kb = KnowledgeBase(state.kb.clauses + (clause,))
        recorder.kb_add(clause)
        if state.dispatcher is not None:
            state.dispatcher.kb = state.kb
        print(f"  Added: {_fmt_clause(clause)}", file=stdout)
    elif cmd.type == "query":
        # M2: parse_query returns tuple[Atom | Equals, ...] (1-tuple for
        # single-goal queries; n-tuple for multi-goal). The query loop
        # accepts the tuple directly.
        goals = cmd.args["goals"]
        assert isinstance(goals, tuple) and len(goals) >= 1
        if not state.in_query_mode:
            state.in_query_mode = True
        _run_query_loop(goals, state, session, recorder, stdout)
    elif cmd.type == "solver":
        _do_solver(state, stdout)
    elif cmd.type in ("pick", "candidates", "back", "abort"):
        print(f"  '{cmd.type}' is only valid during a query.", file=stdout)
    return True


# ---------------------------------------------------------------------------
# Main REPL entry point
# ---------------------------------------------------------------------------


def run_repl(
    no_log: bool = False,
    _input=None,
    _output=None,
    _stdout: IO | None = None,
    _corpus_dir: Path | str | None = None,
) -> None:
    """Start the interactive REPL.

    Parameters prefixed with '_' are for testing only and should not be
    set by callers in production use.
    """
    recorder = SessionRecorder(
        enabled=not no_log,
        corpus_dir=_corpus_dir or "corpus",
    )
    stdout: IO = _stdout or sys.stdout

    # Build the prompt_toolkit session, injecting I/O only when supplied
    pt_kwargs: dict = {}
    if _input is not None:
        pt_kwargs["input"] = _input
    if _output is not None:
        pt_kwargs["output"] = _output
    session: PromptSession = PromptSession(**pt_kwargs)

    state = _ReplState()

    # Initialise M2 dispatcher with real solver bridges.
    try:
        from hlmr.solvers.z3_bridge import Z3Bridge
        from hlmr.solvers.sympy_bridge import SymPyBridge
        from hlmr.dispatch.route import Dispatcher
        state.dispatcher = Dispatcher(
            z3_bridge=Z3Bridge(),
            sympy_bridge=SymPyBridge(),
            kb=state.kb,  # kb reference; dispatcher.kb updated when KB changes
            logger=recorder if not no_log else None,
        )
    except ImportError:
        state.dispatcher = None  # z3 or sympy not installed; M1 mode only

    print(f"HLMR REPL — session {recorder.session_id}", file=stdout)
    if recorder.log_path:
        print(f"Logging to: {recorder.log_path}", file=stdout)
    m2_status = "M2 arithmetic enabled" if state.dispatcher else "M2 arithmetic unavailable (z3/sympy not installed)"
    print(f"M2: {m2_status}", file=stdout)
    print("Type ':help' for commands.", file=stdout)

    try:
        while True:
            prompt_str = "?- " if state.in_query_mode else "kb> "
            try:
                line = session.prompt(prompt_str)
            except (EOFError, KeyboardInterrupt):
                print("\nBye.", file=stdout)
                break

            try:
                cmd = parse_command(line, state.in_query_mode)
            except CommandError as e:
                print(f"  Error: {e}", file=stdout)
                continue

            if not _dispatch(cmd, state, session, recorder, stdout):
                print("Bye.", file=stdout)
                break
    finally:
        recorder.close()
