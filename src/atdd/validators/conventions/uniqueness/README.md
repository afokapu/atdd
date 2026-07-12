# `uniqueness` family

Graph-question family **uniqueness** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `uniqueness/scoped_identifier_uniqueness`

- **Question:** Within a declared scope, does each identifier appear only once?
- **Selector:** nodes grouped by identity_scope
- **Traversal:** scope -> collect node ids -> count occurrences
- **Invariant:** count(id) == 1 within scope
- **Auto-capture:** a new node is included if it declares an id and identity scope
- **Failure evidence:** duplicate_id, scope, locations, node_kinds
- **Non-membership:** a node is NOT in `uniqueness/scoped_identifier_uniqueness` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `uniqueness/duplicate_edge_absence`

- **Question:** Does a source node avoid declaring the same edge to the same target more than once?
- **Selector:** nodes with outgoing edges
- **Traversal:** source node -> outgoing edges grouped by edge_type + target_id
- **Invariant:** each source/edge_type/target tuple appears once
- **Auto-capture:** a new node is included if it declares graph edges using standard edge metadata
- **Failure evidence:** source_node, edge_type, target_node, duplicate_locations
- **Non-membership:** a node is NOT in `uniqueness/duplicate_edge_absence` when it does not match the selector above (its schema/metadata does not opt it into this question).
