% syllogism_andE.pl — Two-literal rule body for M1 corpus
% The rule body has two literals, exercising the multi-body code path
% in the renderer (andI to combine body subproofs before impE).
%
% Clause index reference:
%   athlete_1: athlete(X) :- person(X), healthy(X).
%   person_1:  person(socrates).
%   healthy_1: healthy(socrates).
%
% Fixture: syllogism_andE
%   Query:  ?- athlete(socrates).
%   Picker: [0, 0, 0]

athlete(X) :- person(X), healthy(X).
person(socrates).
healthy(socrates).
