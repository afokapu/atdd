# `composition` family

Graph-question family **composition** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `composition/composed_graph_loads`

- **Question:** Can all convention sources be loaded into one composed graph?
- **Selector:** all convention source files/packages
- **Traversal:** source files -> parse -> local graph fragments -> composed graph
- **Invariant:** graph construction succeeds with no parse/load errors
- **Auto-capture:** a new node is included if it lives in a convention source path included by the graph loader
- **Failure evidence:** source_file, parse_error, node_id_if_available, package_id
- **Non-membership:** a node is NOT in `composition/composed_graph_loads` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `composition/composition_merge_identity`

- **Question:** When graph fragments compose, are node identities merged, duplicated, or shadowed correctly?
- **Selector:** all nodes grouped by canonical id across packages/fragments
- **Traversal:** package graph fragments -> canonical node id -> merge policy
- **Invariant:** duplicate ids are either forbidden or explicitly allowed by merge/override policy
- **Auto-capture:** a new node is included if it declares canonical identity and package ownership
- **Failure evidence:** node_id, conflicting_packages, merge_policy, locations
- **Non-membership:** a node is NOT in `composition/composition_merge_identity` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `composition/post_composition_edge_legality`

- **Question:** After composition, are all edges legal under composed graph rules?
- **Selector:** composed_graph.edges
- **Traversal:** edge -> source node -> target node -> allowed edge type matrix
- **Invariant:** edge type is allowed between source kind/package and target kind/package
- **Auto-capture:** a new node is included if it participates in edges in the composed graph
- **Failure evidence:** edge_type, source_node, target_node, source_kind, target_kind, reason
- **Non-membership:** a node is NOT in `composition/post_composition_edge_legality` when it does not match the selector above (its schema/metadata does not opt it into this question).
