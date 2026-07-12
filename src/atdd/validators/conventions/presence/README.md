# `presence` family

Graph-question family **presence** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `presence/required_field_presence`

- **Question:** Does every eligible node declare the fields required by its convention/schema?
- **Selector:** nodes whose schema/kind declares required fields
- **Traversal:** node -> required_fields
- **Invariant:** every required field exists and is non-empty
- **Auto-capture:** a new node is included if its schema/kind declares required fields
- **Failure evidence:** node_id, missing_field, schema_id, node_location
- **Non-membership:** a node is NOT in `presence/required_field_presence` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `presence/required_relationship_presence`

- **Question:** Does every eligible node have a required outgoing relationship or child edge?
- **Selector:** nodes whose schema/kind declares required relationships
- **Traversal:** node -> required_relationship_type -> target nodes
- **Invariant:** required relationship target set is non-empty
- **Auto-capture:** a new node is included if its schema declares required relationships
- **Failure evidence:** node_id, missing_relationship, expected_target_kind, node_location
- **Non-membership:** a node is NOT in `presence/required_relationship_presence` when it does not match the selector above (its schema/metadata does not opt it into this question).

## `presence/conditional_requirement`

- **Question:** If condition A is true on a node, does field/edge B exist?
- **Selector:** nodes declaring conditional requirements
- **Traversal:** node -> condition field/value -> required field/edge
- **Invariant:** if condition is true, required target exists
- **Auto-capture:** a new node is included if its schema declares conditional requirements
- **Failure evidence:** node_id, condition, missing_requirement, node_location
- **Non-membership:** a node is NOT in `presence/conditional_requirement` when it does not match the selector above (its schema/metadata does not opt it into this question).
