% Peano multiplication, on top of Peano addition.
% mult(A, B, C) means A * B = C.
%
% Examples to try in the REPL:
%
%   ?- mult(s(s(0)), s(s(0)), ?R).         % 2 * 2 = ?     -> ?R = s(s(s(s(0))))
%     Picker: [1, 1, 0, 0, 1, 1, 0]
%
%   ?- mult(s(s(s(0))), s(s(0)), ?R).      % 3 * 2 = ?     -> ?R = s(s(s(s(s(s(0))))))
%     Picker: [1, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0]
%
%   ?- mult(s(s(0)), s(0), ?R).            % 2 * 1 = ?     -> ?R = s(s(0))
%     Picker: [1, 1, 0, 0, 1, 1, 0]

plus(0, Y, Y).
plus(s(X), Y, s(Z)) :- plus(X, Y, Z).

mult(0, Y, 0).
mult(s(X), Y, Z) :- mult(X, Y, W), plus(W, Y, Z).
