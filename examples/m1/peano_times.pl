% peano_times.pl — Peano multiplication (includes plus) for M1 corpus
% times(A, B, C) means A * B = C (successor structure only, not arithmetic).
%
% Clause index reference:
%   plus_1:  plus(0, Y, Y).
%   plus_2:  plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
%   times_1: times(0, Y, 0).
%   times_2: times(s(X), Y, Z) :- times(X, Y, W), plus(W, Y, Z).
%
% Fixtures and their pickers:
%   peano_times_2_2: ?- times(s(s(0)), s(s(0)), ?R).      picker=[1,1,0,0,1,1,0]    ?R=s(s(s(s(0))))
%   peano_times_2_3: ?- times(s(s(0)), s(s(s(0))), ?R).   picker=[1,1,0,0,1,1,1,0]  ?R=s(s(s(s(s(s(0))))))
%   peano_times_3_2: ?- times(s(s(s(0))), s(s(0)), ?R).   picker=[1,1,1,0,0,1,1,0,1,1,1,1,0]

plus(0, Y, Y).
plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
times(0, Y, 0).
times(s(X), Y, Z) :- times(X, Y, W), plus(W, Y, Z).
