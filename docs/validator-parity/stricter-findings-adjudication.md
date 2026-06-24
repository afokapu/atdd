# Stricter-Finding Adjudication (#1211, E024)

The convention validators are often **stricter** than legacy. Strictness is usually a
good sign (legacy was lenient/flaky), but each convention-only finding must be
classified before it counts as "better coverage" vs noise. Classes:

- **real-gap** — a genuine defect legacy missed; the convention check is correct.
- **schema-bug** — the convention check applies a JSON schema that is out of sync
  with real, accepted usage; fix the schema, not the content.
- **loader-bug** — the convention graph loader used the wrong representation; fix the
  loader.

| finding | count | class | status |
|---|---|---|---|
| acceptance harness `type: smoke` rejected (enum lacked `smoke`) | 128 | **schema-bug** | **FIXED** (#1211 E026 — added `smoke` to `acceptance.schema` harness enum) |
| train nodes failed `train.schema` (`'wagons' unexpected`) | 25 | **loader-bug** | **FIXED** (#1211 E025 — loader now reads `plan/_trains/*.yaml` detail files) |
| train `sequence.artifact` pattern (1-colon regex vs `commons:plan:manifest` 2-colon) | all trains | **schema-bug** | OPEN — `train.schema` artifact regex too strict for real 2+-segment artifacts; deferred (broader schema fix) |
| feature `components` declares `adapters` (not in `feature.schema` enum) | 383 | **real-gap (candidate)** | OPEN — needs decision: extend enum vs. correct features; verify a sample is a true defect |
| feature `description` constraint vs long prose | 107 | **schema-vs-content** | OPEN — decide whether the schema constraint is intended; legacy did not enforce |
| `scoped_identifier_uniqueness` sentinel is **rule-scoped** only | 1 | **real-gap (candidate)** | OPEN — legacy uniqueness spans 7 id-classes (wagon-slug, train-id, wmbt-id, feature-urn, contract-urn, telemetry-urn, produce-artifact; see `test_plan_uniqueness.py`); the convention sentinel covers rule-ids only. Needs additional uniqueness variants before the uniqueness family can claim full parity. NOT a parity improvement — a coverage gap in the convention layer. |
| `declaration_to_implementation_binding` is **disposition-agnostic** vs legacy disposition-scoped | 1 | **semantics-divergence** | OPEN — legacy `test_every_enforced_rule_has_real_validator` only gates rules with `disposition ∈ {strict, suppress-and-clean, advisory}`; a no-disposition rule with a `validator:` is "unmigrated / out of scope" and routed to a different gate. The convention sentinel flags any rule whose `validator:` does not resolve, regardless of disposition. Discovered via the #1212 catch matrix (the `rule-validator-missing-impl` case is parity only after adding `disposition: strict`). Decide whether the binding family should mirror legacy's disposition scoping or remain intentionally stricter. |

## Measurement learnings (#1212 catch matrix)

- **Counterpart pairing must match representation.** The `duplicate-wmbt-id` probe was
  dropped: legacy `test_wmbt_ids_unique_per_wagon` reads the manifest's *declared* `wmbt`
  section, not the wmbt YAML files on disk, so a duplicate-urn *file* is out of its scope.
  A "neither" cell there was a mis-injection artifact, not a shared blind spot — not recorded.
- **Legacy-green-on-clean guard added.** The harness now runs each legacy target on the
  clean tree too; a target already red on clean is marked **inconclusive** and excluded
  from the parity count, so pre-existing legacy red can never be miscredited as "catching"
  an injected fault.
- **Corpus now = 7 differential P0 pairs at parity (was 2)**, covering 7 of the 10 sentinel
  templates: theme grammar, identifier grammar, scoped uniqueness, node-schema conformance,
  direct-reference resolution, reference-chain resolution, declaration→implementation binding.
  Still uncovered by a matrix case: `composed_graph_loads` (meta/parse — no single legacy
  counterpart), `artifact_reference_resolution` (legacy uses produce-URN→dir; sentinel uses
  the `references` field — representation differs, needs a matched fault), and
  `rule_validator_roundtrip` (overlaps binding + forward coherence).

## Rule

A convention-only finding may be presented as **better coverage** only after it is
classified **real-gap** AND confirmed a true positive (e.g. via the #1212 catch
matrix). `schema-bug` / `loader-bug` findings are **not** parity improvements — they
are fixed in the convention layer (schema or loader), not claimed against legacy.

Decommission stays BLOCKED while any P0 finding is unclassified or any `real-gap`
remains unconfirmed.
