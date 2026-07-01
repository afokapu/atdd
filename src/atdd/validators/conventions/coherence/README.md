# `coherence` family

Graph-question family **coherence** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `coherence/resolved_fact_agreement`

- **Question:** After references resolve, do the resolved facts agree with each other?
- **Selector:** nodes declaring coherence checks or semantic comparison rules
- **Traversal:** source node -> resolved fact A; source node -> resolved fact B; compare A and B
- **Invariant:** facts satisfy comparison predicate
- **Auto-capture:** partial; a new node is included only if it declares a known coherence predicate
- **Failure evidence:** source_node, fact_a, fact_b, predicate, actual_values
- **Non-membership:** a node is NOT in `coherence/resolved_fact_agreement` when it does not match the selector above (its schema/metadata does not opt it into this question).
