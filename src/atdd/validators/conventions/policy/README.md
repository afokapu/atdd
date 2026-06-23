# `policy` family

Graph-question family **policy** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `policy/forbidden_construct_absence`

- **Question:** Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?
- **Selector:** graph nodes/artifacts matched by a policy scope
- **Traversal:** scope -> scan nodes/fields/edges/artifacts -> forbidden matcher
- **Invariant:** forbidden match set is empty
- **Auto-capture:** usually explicit; a new node is included if it falls inside a policy scope
- **Failure evidence:** matched_construct, policy_id, location, reason, suggested_replacement
- **Non-membership:** a node is NOT in `policy/forbidden_construct_absence` when it does not match the selector above (its schema/metadata does not opt it into this question).
