% kinship_extended.pl — Extended kinship KB for M1 corpus
% parent(P, C) means P is a direct parent of C.
%
% Clause index reference (for driver picker arguments):
%   parent_1: parent(carol, mid1)
%   parent_2: parent(mid1, alice)
%   parent_3: parent(alice, bob)
%   parent_4: parent(bob, carol2)
%   parent_5: parent(carol2, dave)
%   parent_6: parent(dave, eve)
%   parent_7: parent(eve, fred)
%   parent_8: parent(fred, leaf6)
%   ancestor_1: ancestor(X, Y) :- parent(X, Y).
%   ancestor_2: ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
%
% Fixtures and their pickers:
%   kinship_deep       : ?- ancestor(?X, alice).     picker=[1,0,0,1]  ?X=carol
%   kinship_first_child: ?- parent(alice, ?Y).        picker=[2]        ?Y=bob
%   kinship_two_metas  : ?- ancestor(?X, ?Y).         picker=[0,0]      ?X=carol,?Y=mid1
%   kinship_chain6     : ?- ancestor(?Top, leaf6).    picker=[1,2,1,3,1,4,1,5,1,6,0,7]  ?Top=alice

parent(carol, mid1).
parent(mid1, alice).
parent(alice, bob).
parent(bob, carol2).
parent(carol2, dave).
parent(dave, eve).
parent(eve, fred).
parent(fred, leaf6).
ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
