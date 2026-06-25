# `boundary` family

Graph-question family **boundary** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `boundary/allowed_boundary_crossing`

- **Question:** Does this edge, import, or reference cross only allowed package/layer boundaries?
- **Selector:** edges/imports/references with source and target ownership metadata
- **Traversal:** source node/package -> edge/import/ref -> target node/package -> boundary policy
- **Invariant:** boundary_policy.allows(source, target, edge_type)
- **Auto-capture:** a new node is included if it declares ownership/package/layer metadata and participates in edges
- **Failure evidence:** source, target, edge_type, source_boundary, target_boundary, violated_policy
- **Non-membership:** a node is NOT in `boundary/allowed_boundary_crossing` when it does not match the selector above (its schema/metadata does not opt it into this question).
