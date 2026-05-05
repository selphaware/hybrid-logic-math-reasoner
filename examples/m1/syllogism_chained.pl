% syllogism_chained.pl — Three universals chained for M1 corpus
% Exercises multiple forallE + impE cycles in the renderer.
%
% Clause index reference:
%   human_1:    human(socrates).
%   mortal_1:   mortal(X) :- human(X).
%   temporal_1: temporal(X) :- mortal(X).
%
% Fixture: syllogism_chained
%   Query:  ?- temporal(socrates).
%   Picker: [0, 0, 0]

human(socrates).
mortal(X) :- human(X).
temporal(X) :- mortal(X).
