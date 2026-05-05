% capture_stress.pl — Adversarial variable naming for M1 corpus
% All three capture-avoidance stress fixtures share this KB.
% Each fixture uses a different predicate group.
%
% Group 1: capture_shared_xy
%   Two clauses both use X, Y; chain through both.
%   Clause index reference:
%     foo_1: foo(X, Y) :- bar(X, Y).
%     bar_1: bar(X, Y) :- baz(X, Y).
%     baz_1: baz(a, b).
%   Query: ?- foo(?A, ?B).   Picker: [0,0,0]   ?A=a, ?B=b
%
% Group 2: capture_meta_clash
%   Clause uses X; query uses ?X. Renamer must keep them distinct.
%   Clause index reference:
%     knows_1:  knows(X) :- exists(X).
%     exists_1: exists(socrates).
%   Query: ?- knows(?X).   Picker: [0,0]   ?X=socrates
%
% Group 3: capture_mutual_recursion
%   Two predicates both using X, Y, Z; each invocation must rename apart.
%   Clause index reference:
%     even3_1:  even3(X, Y, Z) :- odd3(X, Y, Z).
%     odd3_1:   odd3(X, Y, Z) :- triple(X, Y, Z).
%     triple_1: triple(a, b, c).
%   Query: ?- even3(?X, ?Y, ?Z).   Picker: [0,0,0]   ?X=a, ?Y=b, ?Z=c

foo(X, Y) :- bar(X, Y).
bar(X, Y) :- baz(X, Y).
baz(a, b).
knows(X) :- exists(X).
exists(socrates).
even3(X, Y, Z) :- odd3(X, Y, Z).
odd3(X, Y, Z) :- triple(X, Y, Z).
triple(a, b, c).
