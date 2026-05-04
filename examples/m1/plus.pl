% Peano addition. Naturals encoded as 0, s(0), s(s(0)), ...
% plus(A, B, C) means A + B = C.
%
% Examples to try in the REPL:
%
%   ?- plus(s(s(0)), s(0), ?R).            % 2 + 1 = ?     -> ?R = s(s(s(0)))
%     Picker: [1, 1, 0]
%
%   ?- plus(s(s(0)), s(s(0)), ?R).         % 2 + 2 = ?     -> ?R = s(s(s(s(0))))
%     Picker: [1, 1, 0]
%
%   ?- plus(s(s(0)), ?X, s(s(s(0)))).      % 2 + ? = 3     -> ?X = s(0)
%     Picker: [1, 1, 0]
%
%   ?- plus(?A, ?B, s(s(0))).              % ? + ? = 2     -> first witness ?A=0, ?B=s(s(0))
%     Picker: [0]    (just pick the base case to get the trivial split)

plus(0, Y, Y).
plus(s(X), Y, s(Z)) :- plus(X, Y, Z).
