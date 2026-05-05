# M1 Proof Corpus

30 kernel-verified proof JSON files. Each file has a companion
`<name>.meta.json` sidecar recording the original query, the expected
witness, a sha256 of the KB source, and the expected final formula.

**Do not hand-edit sidecar files.** Regenerate with:

```powershell
python -m hlmr regenerate-corpus
```

Review `git diff proofs/m1/` before committing. Never blanket `git add proofs/m1/`.

See `HARDENING_FINDINGS.md` for property-test findings from the M1 hardening pass.

---

## Fixtures

| File | Query | Exercises | Lines |
|---|---|---|---|
| `kinship.json` | `?- ancestor(?A, carol).` | Recursive clause, one meta | 12 |
| `kinship_deep.json` | `?- ancestor(?X, alice).` | ancestor_2 + 2-hop parent chain; SLD depth 4 | 12 |
| `kinship_first_child.json` | `?- parent(alice, ?Y).` | Single fact lookup; direct predicate match | 1 |
| `kinship_two_metas.json` | `?- ancestor(?X, ?Y).` | Both metas bound from one resolution chain | 5 |
| `kinship_chain6.json` | `?- ancestor(?Top, leaf6).` | 6-deep parent chain; SLD depth 12; renaming-apart stress | 36 |
| `peano_even.json` | `?- even(s(s(s(s(0))))).` | Inductive predicate, Peano 4; SLD depth 2 | 6 |
| `peano_even_6.json` | `?- even(s^6(0)).` | Peano 6; SLD depth 3 | 8 |
| `peano_even_8.json` | `?- even(s^8(0)).` | Peano 8; SLD depth 4 | 10 |
| `peano_even_find_first.json` | `?- even(?N).` | Meta in query; base case fires immediately | 1 |
| `peano_plus_2_2.json` | `?- plus(s(s(0)), s(s(0)), ?R).` | Plus 2+2; SLD depth 3 | 11 |
| `peano_plus_3_2.json` | `?- plus(s(s(s(0))), s(s(0)), ?R).` | Plus 3+2; SLD depth 4 | 15 |
| `peano_plus_find_b.json` | `?- plus(0, ?B, s(s(s(0)))).` | Backward: find summand; immediate | 2 |
| `peano_plus_find_a.json` | `?- plus(?A, s(s(0)), s(s(s(s(0))))).` | Backward: find augend; SLD depth 3 | 11 |
| `peano_plus_5.json` | `?- plus(s(0), s^4(0), ?R).` | Plus 1+4; SLD depth 2 | 7 |
| `peano_times_2_2.json` | `?- times(s(s(0)), s(s(0)), ?R).` | Times 2×2; SLD depth 7; nested plus | 27 |
| `peano_times_2_3.json` | `?- times(s(s(0)), s(s(s(0))), ?R).` | Times 2×3; SLD depth 8; deepest nested-Func shapes | 31 |
| `peano_times_3_2.json` | `?- times(s(s(s(0))), s(s(0)), ?R).` | Times 3×2; SLD depth 13; stress-tests serialiser on nested Func | 50 |
| `peano_lt_2_4.json` | `?- lt(s(s(0)), s^4(0)).` | Structural less-than; anonymous variable in lt_1 | 9 |
| `peano_lt_find.json` | `?- lt(?X, s(s(s(0)))).` | lt base case; meta in query | 2 |
| `syllogism.json` | `?- mortal(socrates).` | Two-step forallE + impE chain | 4 |
| `syllogism_chained.json` | `?- temporal(socrates).` | Three universals chained; multiple forallE + impE cycles | 7 |
| `syllogism_andE.json` | `?- athlete(socrates).` | 2-literal rule body; exercises andI path in renderer | 6 |
| `finite_puzzle.json` | `?- chain(red, green, blue).` | 3-item colour-chain; multi-body rule | 15 |
| `finite_puzzle_4var.json` | `?- ring4(a, b, c, d).` | 4-variable ring; 5 constraint levels; SLD depth 9 | 26 |
| `capture_shared_xy.json` | `?- foo(?A, ?B).` | Two clauses sharing X, Y; chain through both | 9 |
| `capture_meta_clash.json` | `?- knows(?X).` | Clause var X vs query meta ?X; must rename apart | 4 |
| `capture_mutual_recursion.json` | `?- even3(?X, ?Y, ?Z).` | Two predicates both using X, Y, Z; each invocation renamed | 11 |
| `edge_single_fact.json` | `?- truth(a).` | KB = one ground fact; smallest valid M1 proof | 1 |
| `edge_query_is_fact.json` | `?- fact_pred(a).` | Mixed KB; query matches fact; rule clauses never used | 1 |
| `edge_all_meta.json` | `?- triple(?A, ?B, ?C).` | All query args are metas; all bind from one ground fact | 1 |
