# P0 Legacy-vs-Convention Behavioral Gap Report (#1206)

Measured per the verification levels:

- **L1 — template fixture test**: archetype detects synthetic valid/invalid cases.
- **L2 — real graph selector test**: variant selects real repo nodes (cardinality > 0)
  and detects an injected real fault.
- **L3 — fault-injection parity**: target catches what the *actual legacy validator*
  catches on the same injected fault.
- **L4 — shadow CI**: both run safely in parallel.

## Status

| pair / sentinel | level | selector cardinality (real graph) | evidence |
|---|---|---|---|
| `grammar/theme_must_be_canonical` | **L3** | 27 wagons | injected non-canonical theme caught by BOTH legacy pytest AND convention sentinel; clean repo = 0 |
| `uniqueness/scoped_identifier_uniqueness` | **L3** | 152 rules | injected duplicate rule-id caught by BOTH legacy `test_rule_id_uniqueness` AND convention sentinel; clean = 0 |
| `resolution/direct_reference_resolution` | **L2** | 170 nodes / 536 edges | injected dangling ref caught; clean repo = 0 |
| `resolution/reference_chain_resolution` | **L2** | 27 wagons / 505 hops | injected broken wagon→feature→wmbt hop caught; clean = 0 |
| `binding/rule_validator_roundtrip` | **L2+** | 95 rules | finds 2 real roundtrip gaps on live data (same class as legacy literal-bind scanner) |
| `binding/declaration_to_implementation_binding` | **L2** | 95 rules | injected rule→missing validator file caught; clean = 0 |
| `grammar/identifier_grammar_conformance` | **L2** | 393 wmbts | injected malformed wmbt urn caught; clean = 0 |
| `composition/composed_graph_loads` | **L2** | 715 nodes | injected unparseable convention source caught; clean = 0 |
| remaining P0 pairs (artifact-resolution, node-schema) | **L1 only** | — | fixture/contract scaffold; not yet ported to real-graph checks |
| all P1 pairs | **L1 only** | — | scaffold |

## What this proves

- The **approach is sound**: `real graph -> normalized indexes -> selector ->
  traversal -> invariant -> failure evidence -> parity` works end-to-end. The
  three sentinels (field-inspection, traversal, rule-validator roundtrip) all
  select real nodes (non-vacuous) and detect real faults on the live repo; theme
  has black-box parity with its legacy validator.
- The **prior 0/32 was an implementation artifact**: the first engine used a toy
  loader + synthetic-field evaluators, so selectors inspected ~0 real nodes and
  passed vacuously. The real `_support/graph_loader.py` normalizes 715 nodes
  (27 wagons / 138 features / 393 wmbts / 5 trains / 152 rules / 106 emitted
  rule_ids), which is what the sentinels query.

## What remains (real parity)

1. **Port the remaining 29 P0 pairs** to real-graph selectors/invariants using the
   sentinel pattern (`_support/sentinels.py`), each with a vacuity guard
   (`selected_nodes > 0`) and a fault-injection parity test vs its legacy validator.
2. **Black-box parity harness** for pytest-coupled legacy validators (only 2/32
   expose a callable API): inject fault → run legacy pytest + convention → compare
   failure class. The theme sentinel demonstrates this pattern.
3. Then P1.

Until every P0 pair reaches L3, **legacy is authoritative and decommission is BLOCKED.**
