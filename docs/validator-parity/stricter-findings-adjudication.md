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

## Rule

A convention-only finding may be presented as **better coverage** only after it is
classified **real-gap** AND confirmed a true positive (e.g. via the #1212 catch
matrix). `schema-bug` / `loader-bug` findings are **not** parity improvements — they
are fixed in the convention layer (schema or loader), not claimed against legacy.

Decommission stays BLOCKED while any P0 finding is unclassified or any `real-gap`
remains unconfirmed.
