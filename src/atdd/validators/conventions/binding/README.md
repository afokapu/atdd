# `binding` family

Graph-question family **binding** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `binding/declaration_to_implementation_binding`

- **Question:** Does a declaration point to a real implementation, validator, or artifact that claims to enforce it?
- **Selector:** rule/declaration nodes where enforcement requires implementation
- **Traversal:** declaration node -> implementation_ref -> implementation index
- **Invariant:** implementation exists and declares compatibility with the declaration
- **Auto-capture:** a new node is included if it declares enforcement=validator or equivalent implementation binding metadata
- **Failure evidence:** declaration_node, implementation_ref, missing_or_incompatible_implementation, declaration_location
- **Non-membership:** a node is NOT in `binding/declaration_to_implementation_binding` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `binding/emitted_identity_roundtrip`

- **Question:** Does implementation output round-trip to the declaring rule or node?
- **Selector:** implementations/validators that emit rule_ids or node_ids
- **Traversal:** declaration -> implementation -> emitted identity -> declaration index
- **Invariant:** emitted identity resolves back to the same declaring rule/node
- **Auto-capture:** a new node is included if its implementation declares emitted identities in standard metadata
- **Failure evidence:** declaration_id, implementation_id, emitted_identity, expected_identity, actual_resolved_target
- **Non-membership:** a node is NOT in `binding/emitted_identity_roundtrip` when it does not match the selector above (its schema/metadata does not opt it into this question).
