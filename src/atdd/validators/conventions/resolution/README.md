# `resolution` family

Graph-question family **resolution** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `resolution/direct_reference_resolution`

- **Question:** Does every declared reference resolve to an existing graph target?
- **Selector:** nodes with refs/node_refs/rule_refs/relationship_targets
- **Traversal:** source node -> reference value -> target index
- **Invariant:** target_index.contains(reference)
- **Auto-capture:** a new node is included if it declares references using standard ref fields
- **Failure evidence:** source_node, ref_field, missing_ref, expected_target_kind, source_location
- **Non-membership:** a node is NOT in `resolution/direct_reference_resolution` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `resolution/artifact_reference_resolution`

- **Question:** Does every file, schema, fixture, or URN artifact reference resolve to a real artifact?
- **Selector:** nodes with artifact_refs/file_refs/schema_refs/fixture_refs
- **Traversal:** node -> artifact reference -> repository artifact index
- **Invariant:** artifact exists and is addressable from repo root/package root
- **Auto-capture:** a new node is included if it declares artifact references with standard metadata
- **Failure evidence:** node_id, artifact_ref, artifact_kind, expected_path, node_location
- **Non-membership:** a node is NOT in `resolution/artifact_reference_resolution` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `resolution/reference_chain_resolution`

- **Question:** Does a multi-hop reference chain resolve completely?
- **Selector:** nodes that declare chained references or transitive dependencies
- **Traversal:** start node -> ref A -> target node -> ref B -> final target
- **Invariant:** all hops resolve; no missing intermediate target
- **Auto-capture:** a new node is included if it declares a chain shape using standard traversal metadata
- **Failure evidence:** start_node, chain_path, failed_hop, missing_ref
- **Non-membership:** a node is NOT in `resolution/reference_chain_resolution` when it does not match the selector above (its schema/metadata does not opt it into this question).
