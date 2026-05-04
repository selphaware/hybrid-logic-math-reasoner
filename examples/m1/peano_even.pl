% Demo 4: Inductive predicate over Peano naturals
% Query:   ?- even(s(s(s(s(0))))).
% Witness: direct (no unknowns); proves even(s(s(s(s(0))))).
% Picker:  [1, 1, 0]  (even_step twice, then even_zero)

even(0).
even(s(s(N))) :- even(N).
