% Demo 2: Syllogism
% Query:   ?- mortal(socrates).
% Witness: direct (no unknowns); proves mortal(socrates).
% Picker:  [0, 0]  (mortal_rule then human_1)

human(socrates).
mortal(X) :- human(X).
