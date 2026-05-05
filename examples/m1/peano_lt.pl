% peano_lt.pl — Structural less-than over Peano naturals for M1 corpus
% lt(X, Y) means X < Y (successor structure, NOT arithmetic comparison).
%
% Note: the second argument of lt_1 uses Y (an unused variable) to avoid the
% bare _ wildcard, which the M1 parser requires to be at least _X (not lone _).
%
% Clause index reference:
%   lt_1: lt(0, s(Y)).
%   lt_2: lt(s(X), s(Y)) :- lt(X, Y).
%
% Fixtures and their pickers:
%   peano_lt_2_4 : ?- lt(s(s(0)), s(s(s(s(0))))).    picker=[1,1,0]
%   peano_lt_find: ?- lt(?X, s(s(s(0)))).             picker=[0]     ?X=0

lt(0, s(Y)).
lt(s(X), s(Y)) :- lt(X, Y).
