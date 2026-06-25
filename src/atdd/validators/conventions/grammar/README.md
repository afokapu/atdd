# `grammar` family

Graph-question family **grammar** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `grammar/identifier_grammar_conformance`

- **Question:** Does an identifier, URN, rule id, or node id follow canonical grammar?
- **Selector:** nodes with id/rule_id/urn/name fields
- **Traversal:** node -> identifier field -> grammar parser
- **Invariant:** parser accepts identifier and parsed parts match graph context
- **Auto-capture:** a new node is included if it declares a grammar-governed identifier field
- **Failure evidence:** node_id, field, value, grammar_name, parse_error
- **Non-membership:** a node is NOT in `grammar/identifier_grammar_conformance` when it does not match the selector above (its schema/metadata does not opt it into this question).
