% Demo 3: Finite colour-chain puzzle
% Query:   ?- chain(red, green, blue).
% Witness: direct (no unknowns); proves chain(red, green, blue).
% Picker:  [0, 0, 0, 0, 1]  (chain_rule, adjacent_rule x2, left_of_1, left_of_2)

left_of(red, green).
left_of(green, blue).
adjacent(X, Y) :- left_of(X, Y).
chain(X, Y, Z) :- adjacent(X, Y), adjacent(Y, Z).
