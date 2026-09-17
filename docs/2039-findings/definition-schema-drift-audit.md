# Definition-node ↔ schema drift audit (#2039)

Every `*.definition` convention node compared against the schema it describes and
against the real `plan/` corpus. Measured 2026-09-17 at `main`.

## Verdict per node

| node | schema | verdict |
|---|---|---|
| `planner.wmbt.definition` | `wmbt.schema.json` | **drifted** — expands WMBT as "What-Might-Break Test"; "a way an artifact might break" cannot express `maximize` |
| `planner.feature.definition` | `feature.schema.json` | **drifted** — names `status` and `acceptance`; neither exists. Omits `description`, `sizing`, `components`, all required |
| `planner.interlocking.definition` | `train-interlocking.schema.json` | **drifted** — "keyed by a produced artifact"; `route` requires `guard_ref` → a guard `expression` over fields |
| `planner.wagon.definition` | `wagon.schema.json` | clean |
| `planner.train.definition` | `train.schema.json` | clean |
| `planner.artifact.definition` | — | clean |
| `planner.theme.definition` | none exists | not assessable against a schema; internally consistent |

## Acronym expansions in tracked source

| expansion | files |
|---|---|
| What Must Be True | 12 |
| What-Might-Break Test | 1 — `planner.wmbt.definition.convention.yaml:6` |
| Write Meaningful Before Tests | 1 — `coach/commands/inventory.py:514` |
| Way My Brain Tests | 0 in source; `graphify-out/` only (generated, untracked) |

## Corpus measurements

```
WMBTs by direction (484):  minimize 397 (82%)   maximize 87 (18%)
  -> the "might break" framing cannot describe the 87

feature files (190):  urn/wagon/wmbts 190/190; description/sizing/components 187
                      status 0/190      acceptance 0/190

atdd coach inventory:  334 of 484 counted — misses 150 (31%)
                       by step code: D:74  Y:29  R:20  M:19  K:8

real guard expressions:  exists(overlay_events)
                         bound == true and violations == 0
```

## Systemic cause

All seven definition nodes are `status: draft`, `kind: family`, self-described
"advisory semantic anchor — it enforces nothing directly", with **zero** entries in
`.atdd/binding.lock.yaml`.

The repo validates artifact **shape** exhaustively — `test_wmbt_vocabulary`,
`test_hierarchy_coverage`, `test_wmbt_has_smoke_acceptance`, `test_wmbt_consistency`,
plus per-acceptance schema validation — and has never validated that its own
**definitions** describe that shape. `wmbt.schema.json`'s `$comment` records the
same asymmetry from the other side: the schema "is NOT applied as a file-level gate
to WMBT files". Neither half validates the other.

## Authority

The schema wins, structurally rather than by preference:

1. `acceptances` is a *property* of a WMBT (`$ref acceptance.schema.json#/definitions/embedded_acceptance`). A thing that has acceptances is not an acceptance criterion.
2. `planner.wmbt.shape`, a sibling node already correct, calls them "the artifacts that **prove** the statement".
3. "A way an artifact might break" cannot describe 87 `maximize` WMBTs.

## Corrected definition (proposed)

> **WMBT (What Must Be True)** — a single measurable outcome that must hold for a
> wagon's job to be done. It names one `object_of_control`, moved in one `direction`
> along exactly one `dimension`, at one `lens`, qualified by a `context_clarifier`,
> and placed at one JTBD `step`. Its `statement` is composed as
> `{direction} {dimension} of {object_of_control} [context_clarifier]`.
>
> A WMBT is **not** itself a test or an acceptance criterion: the `acceptances` it
> carries are the artifacts that prove it, of which at least one must be a SMOKE
> acceptance.
