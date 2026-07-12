# `schema` family

Graph-question family **schema** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `schema/node_schema_conformance`

- **Question:** Does each node conform to its declared schema?
- **Selector:** nodes where node.schema exists
- **Traversal:** node -> schema_id -> schema document -> validate node payload
- **Invariant:** jsonschema validation passes
- **Auto-capture:** a new node is included if it declares `schema`
- **Failure evidence:** node_id, schema_id, schema_error_path, schema_error_message, node_location
- **Non-membership:** a node is NOT in `schema/node_schema_conformance` when it does not match the selector above (its schema/metadata does not opt it into this question).
