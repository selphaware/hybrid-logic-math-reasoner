% peano_plus.pl — Peano addition for M1 corpus
% plus(A, B, C) means A + B = C (successor structure only, not arithmetic).
%
% Clause index reference:
%   plus_1: plus(0, Y, Y).
%   plus_2: plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
%
% Fixtures and their pickers:
%   peano_plus_2_2    : ?- plus(s(s(0)), s(s(0)), ?R).              picker=[1,1,0]  ?R=s(s(s(s(0))))
%   peano_plus_3_2    : ?- plus(s(s(s(0))), s(s(0)), ?R).           picker=[1,1,1,0]
%   peano_plus_find_b : ?- plus(0, ?B, s(s(s(0)))).                 picker=[0]      ?B=s(s(s(0)))
%   peano_plus_find_a : ?- plus(?A, s(s(0)), s(s(s(s(0))))).        picker=[1,1,0]  ?A=s(s(0))
%   peano_plus_5      : ?- plus(s(0), s(s(s(s(0)))), ?R).           picker=[1,0]

plus(0, Y, Y).
plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
