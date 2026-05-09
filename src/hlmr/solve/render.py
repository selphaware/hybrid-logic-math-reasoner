from __future__ import annotations

from hlmr.ir.formula import (
    And,
    Atom,
    Equals,
    ForAll,
    Formula,
    Func,
    Implies,
    Meta,
    Term,
    Var,
    subst,
)
from hlmr.ir.justification import Premise, RuleApp
from hlmr.ir.kb import Clause, KnowledgeBase
from hlmr.ir.proof import Proof, ProofLine
from hlmr.solve.sld import (
    ClauseResolvedStep,
    DispatcherResolvedStep,
    SLDState,
    SLDStep,
    _vars_in_order,
)
from hlmr.unify.substitution import Substitution, apply_to_formula, apply_to_term


class RenderError(Exception):
    """Raised when the renderer cannot produce a valid proof.

    Indicates a renderer bug or an unsaturated substitution, not a
    soundness issue — the kernel is the final arbiter.
    """


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _saturate(s: Substitution, max_iter: int = 30) -> Substitution:
    """Iteratively apply s to its own values until stable.

    apply_to_term is one-pass and does not chase chains like
    ?A -> ?X_1 -> alice.  This resolves all chains.
    Private to render.py; do not promote to unify/ without discussion.
    """
    for _ in range(max_iter):
        s_new = {k: apply_to_term(s, v) for k, v in s.items()}
        if s_new == s:
            return s
        s = s_new
    return s  # pragma: no cover — unreachable for finite acyclic substitutions


def _term_has_meta(t: Term) -> bool:
    match t:
        case Meta():
            return True
        case Func(args=args):
            return any(_term_has_meta(a) for a in args)
    return False


def _formula_has_meta(f: Formula) -> bool:
    """Return True if any Meta term appears anywhere inside f."""
    match f:
        case Atom(args=args):
            return any(_term_has_meta(a) for a in args)
        case Equals(lhs=lhs, rhs=rhs):
            return _term_has_meta(lhs) or _term_has_meta(rhs)
        case And(left=left, right=right) | Implies(left=left, right=right):
            return _formula_has_meta(left) or _formula_has_meta(right)
        case ForAll(body=body):
            return _formula_has_meta(body)
        case _:  # pragma: no cover  # Not/Or/Iff/Exists/Bot not produced by M1 renderer
            return False


def _extract_var_map(
    clause_used: Clause, clause_renamed: Clause
) -> dict[str, str]:
    """Walk clause_used and clause_renamed in parallel.

    For every Var(name) in clause_used, the corresponding position in
    clause_renamed must hold Meta(meta_name).  Returns the mapping
    original-var-name -> fresh-meta-name.

    Raises RenderError if the parallel structure is violated (which would
    indicate a bug in _rename_clause).
    """
    var_map: dict[str, str] = {}

    def walk_term(orig: Term, renamed: Term) -> None:
        match orig:
            case Var(name=name):
                if not isinstance(renamed, Meta):
                    raise RenderError(
                        f"_extract_var_map: Var({name!r}) paired with non-Meta"
                        f" {renamed!r} — _rename_clause bug"
                    )
                var_map[name] = renamed.name
            case Func(args=orig_args):
                if not isinstance(renamed, Func) or len(orig_args) != len(
                    renamed.args
                ):  # pragma: no cover  # unreachable: _rename_clause preserves Func structure
                    raise RenderError(
                        f"_extract_var_map: Func arity/type mismatch"
                        f" orig={orig!r} renamed={renamed!r}"
                    )
                for a, b in zip(orig_args, renamed.args):
                    walk_term(a, b)
            # Const and Meta in orig are not renaming targets — nothing to record

    def walk_atom(orig_a: Atom | Equals, renamed_a: Atom | Equals) -> None:
        match orig_a:
            case Atom(args=orig_args):
                assert isinstance(renamed_a, Atom)
                for a, b in zip(orig_args, renamed_a.args):
                    walk_term(a, b)
            case Equals(lhs=lhs, rhs=rhs):
                assert isinstance(renamed_a, Equals)
                walk_term(lhs, renamed_a.lhs)
                walk_term(rhs, renamed_a.rhs)

    walk_atom(clause_used.head, clause_renamed.head)
    for orig_b, renamed_b in zip(clause_used.body, clause_renamed.body):
        walk_atom(orig_b, renamed_b)

    return var_map


def _build_premise_formula(clause: Clause) -> Formula:
    """Build the universally-quantified formula for a clause's premise line.

    Facts (empty body): just the head, possibly wrapped in ForAlls.
    Single-body rules: ForAlls over (body[0] -> head).
    Multi-body rules: ForAlls over (((b_1 & b_2) & ... & b_k) -> head),
    left-associated.
    Variable order: clause-level appearance order (same as _vars_in_order).
    """
    vars_in_order = _vars_in_order(clause)

    if not clause.body:
        inner: Formula = clause.head
    elif len(clause.body) == 1:
        inner = Implies(clause.body[0], clause.head)
    else:
        conj: Formula = clause.body[0]
        for b in clause.body[1:]:
            conj = And(conj, b)
        inner = Implies(conj, clause.head)

    for v in reversed(vars_in_order):
        inner = ForAll(v, inner)

    return inner


def _build_step_tree(history: tuple[SLDStep, ...]) -> list[list[int]]:
    """Recover parent-child relationships from the linear SLD history.

    Returns children[i] = ordered list of child step indices for step i.
    Step 0 is the root (resolves the original query).
    The tree is recovered by treating the history as a DFS pre-order walk:
    each step's body atoms are resolved by the immediately-following steps,
    depth-first left-to-right.

    Raises RenderError if the history is structurally inconsistent (e.g.
    more steps than needed or dangling unresolved body atoms).
    """
    n = len(history)
    children: list[list[int]] = [[] for _ in range(n)]

    # Stack of (parent_idx, remaining_child_count).
    # Top holds the most-recent parent with unresolved body atoms.
    stack: list[tuple[int, int]] = []

    for i, step in enumerate(history):
        if stack:
            parent_idx, remaining = stack[-1]
            children[parent_idx].append(i)
            remaining -= 1
            if remaining == 0:
                stack.pop()
            else:
                stack[-1] = (parent_idx, remaining)

        match step:
            case ClauseResolvedStep(clause_renamed=renamed):
                body_len = len(renamed.body)
            case DispatcherResolvedStep():
                # Dispatcher steps are leaves — no body atoms to resolve.
                body_len = 0
        if body_len > 0:
            stack.append((i, body_len))

    if stack:
        unresolved = sum(r for _, r in stack)
        raise RenderError(
            f"_build_step_tree: {unresolved} body atom(s) left unresolved "
            f"— history may be incomplete"
        )

    return children


def _choose_equality_rule(f: Atom | Equals) -> str:
    """Return 'eqRefl' or 'arithEval' for the given ground atom.

    Policy per RENDER_M2_DESIGN.md §4.4: prefer eqRefl for syntactically
    reflexive Equals(t, t); arithEval for everything else.
    The check uses Python == on frozen-dataclass IR objects.
    """
    match f:
        case Equals(lhs=lhs, rhs=rhs) if lhs == rhs:
            return "eqRefl"
        case _:
            return "arithEval"


def _peel_forall(f: Formula, t: Term) -> Formula:
    """Strip the outermost ForAll, substituting t for its bound variable."""
    if not isinstance(f, ForAll):
        raise RenderError(
            f"_peel_forall: expected ForAll, got {type(f).__name__}"
        )
    return subst(f.body, f.var, t)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(
    state: SLDState,
    kb: KnowledgeBase,
    query: Atom | Equals | tuple[Atom | Equals, ...],
) -> Proof:
    """Convert a successful SLD derivation into a Fitch-style ND proof.

    Pre:  state.goals == () (SLD has succeeded).
    Post: returned Proof has goal = apply_to_formula(saturated_subst, query)
          (or the andI-chained conjunction for multi-goal queries) and
          passes check_proof.

    Raises RenderError on precondition violations or detected renderer bugs
    (unsaturated metas, structural mismatches, etc.).

    M1 alphabet: {Premise, forallE, andI, impE}.
    M2 alphabet: {Premise, forallE, andI, impE, arithEval, eqRefl}.
    All lines at depth 0; no boxes, no assumptions.
    """
    if state.goals:
        raise RenderError(
            f"render: SLD not complete — {len(state.goals)} goal(s) remain"
        )
    history = state.history
    if not history:
        raise RenderError("render: empty history — no SLD steps were taken")

    goals: tuple[Atom | Equals, ...] = (
        (query,) if isinstance(query, (Atom, Equals)) else tuple(query)
    )

    sat = _saturate(state.subst)
    children = _build_step_tree(history)

    # Identify root steps (no parent). Roots correspond 1-to-1 with goals.
    has_parent: set[int] = set()
    for child_list in children:
        for c in child_list:
            has_parent.add(c)
    roots = [i for i in range(len(history)) if i not in has_parent]

    if len(roots) != len(goals):
        raise RenderError(
            f"render: {len(roots)} top-level history step(s) for "
            f"{len(goals)} goal(s) — history/goal count mismatch"
        )

    # Unique KB clauses from ClauseResolvedSteps, in first-use order.
    seen: set[int] = set()
    unique_clauses: list[Clause] = []
    for step in history:
        if not isinstance(step, ClauseResolvedStep):
            continue
        c = step.clause_used
        if id(c) not in seen:
            seen.add(id(c))
            unique_clauses.append(c)

    # Emit premise lines.
    lines: list[ProofLine] = []
    clause_premise_line: dict[int, int] = {}  # id(clause) -> line number

    for c in unique_clauses:
        line_num = len(lines) + 1
        lines.append(ProofLine(line_num, _build_premise_formula(c), Premise(), 0))
        clause_premise_line[id(c)] = line_num

    # -----------------------------------------------------------------------
    # Helpers that close over `lines` and `clause_premise_line`.
    # -----------------------------------------------------------------------

    def _emit(formula: Formula, justification: RuleApp) -> int:
        line_num = len(lines) + 1
        lines.append(ProofLine(line_num, formula, justification, 0))
        return line_num

    def _get_formula(line_num: int) -> Formula:
        return lines[line_num - 1].formula

    def render_step(i: int) -> int:
        """Emit the subproof for step i; return the line number of its head."""
        step = history[i]

        # M2: DispatcherResolvedStep — one arithEval or eqRefl line (leaf).
        if isinstance(step, DispatcherResolvedStep):
            rule_name = _choose_equality_rule(step.ground_atom)
            return _emit(
                step.ground_atom,
                RuleApp(rule=rule_name, line_refs=(), box_refs=(), extra={}),
            )

        # M1: ClauseResolvedStep — DFS render of body children, then head.
        body_line_nums: list[int] = []
        for child_idx in children[i]:
            body_line_nums.append(render_step(child_idx))

        clause = step.clause_used
        var_map = _extract_var_map(clause, step.clause_renamed)

        # Apply forallE chain outermost-first, one peel per clause variable.
        current_line = clause_premise_line[id(clause)]
        for v in _vars_in_order(clause):
            fresh_meta = var_map[v]
            term = apply_to_term(sat, Meta(fresh_meta))
            if _term_has_meta(term):
                raise RenderError(
                    f"unsaturated meta in forallE term for var {v!r}: {term!r}"
                )
            new_formula = _peel_forall(_get_formula(current_line), term)
            current_line = _emit(
                new_formula,
                RuleApp("forallE", line_refs=(current_line,), extra={"term": term}),
            )

        if not clause.body:
            # Fact: the forallE chain (or premise directly, for ground facts)
            # already holds the grounded head atom.
            return current_line

        # Rule: build the conjunction of body-subproof lines, then impE.
        if len(body_line_nums) == 1:
            conj_line = body_line_nums[0]
        else:
            conj_formula = _get_formula(body_line_nums[0])
            conj_line = body_line_nums[0]
            for j in range(1, len(body_line_nums)):
                next_formula = _get_formula(body_line_nums[j])
                conj_formula = And(conj_formula, next_formula)
                conj_line = _emit(
                    conj_formula,
                    RuleApp("andI", line_refs=(conj_line, body_line_nums[j])),
                )

        impl_formula = _get_formula(current_line)
        if not isinstance(impl_formula, Implies):  # pragma: no cover
            raise RenderError(
                f"expected Implies after forallE chain, got"
                f" {type(impl_formula).__name__} at line {current_line}"
            )

        return _emit(
            impl_formula.right,
            RuleApp("impE", line_refs=(current_line, conj_line)),
        )

    # Render each top-level goal subproof and collect the final line number.
    final_line_per_goal: list[int] = []
    for root_idx in roots:
        final_line_per_goal.append(render_step(root_idx))

    # For multi-goal queries: emit a left-associated andI chain combining
    # the per-goal final lines (RENDER_M2_DESIGN.md §4.6).
    if len(goals) > 1:
        running_line = final_line_per_goal[0]
        running_formula = _get_formula(running_line)
        for j in range(1, len(final_line_per_goal)):
            right_line = final_line_per_goal[j]
            right_formula = _get_formula(right_line)
            running_formula = And(running_formula, right_formula)
            running_line = _emit(
                running_formula,
                RuleApp("andI", line_refs=(running_line, right_line)),
            )
        proof_goal: Formula = running_formula
    else:
        proof_goal = _get_formula(final_line_per_goal[0])

    # Validate: no Meta terms survived into the rendered proof.
    for line in lines:
        if _formula_has_meta(line.formula):  # pragma: no cover
            raise RenderError(
                f"meta survived in rendered proof at line {line.number}"
            )

    return Proof(tuple(lines), proof_goal)
