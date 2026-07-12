# `coverage` family

Graph-question family **coverage** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `coverage/reachability_no_orphan`

- **Question:** Is every required node reachable from a valid root or owner?
- **Selector:** nodes where requires_reachability != false
- **Traversal:** root nodes -> allowed edges -> reachable set
- **Invariant:** eligible node is in reachable set
- **Auto-capture:** a new node is included if its kind/package requires reachability by default
- **Failure evidence:** orphan_node, expected_root, allowed_paths, node_location
- **Non-membership:** a node is NOT in `coverage/reachability_no_orphan` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `coverage/source_has_required_target`

- **Question:** For every source node of type X, does required downstream target Y exist?
- **Selector:** nodes where node.coverage.requires exists
- **Traversal:** source node -> required relationship/path -> target node set
- **Invariant:** target set is non-empty and satisfies required target kind/filter
- **Auto-capture:** a new node is included if it declares coverage requirements
- **Failure evidence:** source_node, required_target_kind, required_path, actual_targets
- **Non-membership:** a node is NOT in `coverage/source_has_required_target` when it does not match the selector above (its schema/metadata does not opt it into this question).
