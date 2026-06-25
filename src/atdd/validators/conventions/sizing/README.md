# `sizing` family

Graph-question family **sizing** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `sizing/cardinality_bounds`

- **Question:** Is the number of related nodes within allowed min/max bounds?
- **Selector:** nodes or scopes with declared cardinality constraints
- **Traversal:** source/scope -> collect related nodes -> count
- **Invariant:** min <= count <= max
- **Auto-capture:** a new node is included if it declares cardinality constraints
- **Failure evidence:** source_node_or_scope, relationship, actual_count, min, max, targets
- **Non-membership:** a node is NOT in `sizing/cardinality_bounds` when it does not match the selector above (its schema/metadata does not opt it into this question).
