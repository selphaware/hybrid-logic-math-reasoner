% finite_puzzle_4var.pl — 4-item ring puzzle for M1 corpus
% Items a, b, c, d are arranged in a ring: a->b->c->d->a.
% ring4(A,B,C,D) holds when A,B,C,D are cyclically adjacent.
% 4 variables, 5 constraints (ring4 rule + 4 adjacency checks).
%
% Clause index reference:
%   left_of_1: left_of(a, b).
%   left_of_2: left_of(b, c).
%   left_of_3: left_of(c, d).
%   left_of_4: left_of(d, a).
%   adjacent_1: adjacent(X, Y) :- left_of(X, Y).
%   ring4_1: ring4(A, B, C, D) :- adjacent(A,B), adjacent(B,C), adjacent(C,D), adjacent(D,A).
%
% Fixture: finite_puzzle_4var
%   Query:  ?- ring4(a, b, c, d).
%   Picker: [0, 0, 0, 0, 1, 0, 2, 0, 3]

left_of(a, b).
left_of(b, c).
left_of(c, d).
left_of(d, a).
adjacent(X, Y) :- left_of(X, Y).
ring4(A, B, C, D) :- adjacent(A, B), adjacent(B, C), adjacent(C, D), adjacent(D, A).
