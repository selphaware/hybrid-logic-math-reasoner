% Demo 1: Kinship (recursive ancestor)
% Query:   ?- ancestor(?A, carol).
% Witness: ?A = alice  (via recursive ancestor_rec clause)
% Picker:  [1, 0, 0, 1]  (ancestor_rec, parent_1, ancestor_base, parent_2)

parent(alice, bob).
parent(bob, carol).
ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
