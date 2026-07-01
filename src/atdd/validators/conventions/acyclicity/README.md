# `acyclicity` family

Graph-question family **acyclicity** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `acyclicity/forbidden_cycle_absence`

- **Question:** Does a traversal avoid cycles where cycles are forbidden?
- **Selector:** edge types or relationship subgraphs marked acyclic
- **Traversal:** nodes -> selected edge type/path -> depth-first traversal
- **Invariant:** no node appears twice in the same traversal path
- **Auto-capture:** a new node is included if it participates in an edge type declared acyclic
- **Failure evidence:** cycle_path, edge_type, start_node, repeated_node
- **Non-membership:** a node is NOT in `acyclicity/forbidden_cycle_absence` when it does not match the selector above (its schema/metadata does not opt it into this question).
