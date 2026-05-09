# Coach v9 — Track / Train / Wagon / Archetype map

**Train**: `0002-coach-drives-lifecycle` — single train. Journey: replace
polling-and-trust with an event-driven, observer-augmented coach that drives
the issue → merged-PR lifecycle (per spec §1, §2).

**Wagons**: 9 wagons, named by what each wagon delivers (action verbs that
parallel the train's journey), one per spec track.

| Track | Issues | Wagon | Wagon URN | Archetypes |
|-------|--------|-------|-----------|------------|
| C0 | C0 | `freeze-runtime-contracts` | `wagon:freeze-runtime-contracts` | coach |
| J | J1, J2, J3, J4, J5, J6 | `drive-state-machine` | `wagon:drive-state-machine` | coach |
| K | K1, K2, K3, K4, K5 | `spawn-agents` | `wagon:spawn-agents` | coach (K2 also: tester) |
| L | L1, L2, L3, L4, L5, L6, L7, L8 | `observe-and-correct` | `wagon:observe-and-correct` | coach (L4, L5 also: tester) |
| M | M1, M2, M3, M4, M5 | `dispatch-validators` | `wagon:dispatch-validators` | coach + tester (entire track) |
| N | N1, N2, N3, N4, N5 | `review-phase-boundaries` | `wagon:review-phase-boundaries` | coach |
| O | O1, O2, O3, O4, O5 | `judge-ambiguous-decisions` | `wagon:judge-ambiguous-decisions` | coach |
| P | P1, P2, P3, P4, P5, P6 | `discover-and-decommission` | `wagon:discover-and-decommission` | coach |
| Q | Q1 | `integrate-end-to-end` | `wagon:integrate-end-to-end` | coach |

## WMBT URN convention for these wagons

WMBT URN format: `wmbt:<wagon>:<step-prefix><NNN>`
- step prefixes: D=define, E=execute, C=confirm, L=locate, R=resolve, M=monitor, P=prepare
- example: `wmbt:freeze-runtime-contracts:D001`

Acceptance URN format: `acc:<wagon>:<WMBT-step><NNN>-<HARNESS>-<NUM>-<slug>`
- HARNESS ∈ {UNIT, INTEGRATION, CONTRACT, SMOKE} (matches harness.type field uppercased)
- example: `acc:freeze-runtime-contracts:D001-UNIT-001-six-schemas-exist`

## Topological filing order (dependency-respecting)

Wave w0:  C0, P1, P2, P4
Wave w1:  J1, J2, J3, K1, L1, O1
Wave w1b: J4, K2, K3, K4, L2, L3, O5, P3
Wave w2:  J5, J6, K5, L4, L5, L6, L7, M1, M2, M3, M4, M5, O2, O3, O4
Wave w3:  L8, N1, N2, N3, N4, N5
Wave w4:  P5, P6, Q1

(Within each wave, file in the order listed above. C0 is the absolute first
because all schemas freeze before parallel work begins.)

## Filing instructions per issue

- **Title** — `feat(coach): <terse summary>` (≤70 chars). No internal-spec-id
  prefix; the body's Issue Metadata table carries the `Internal-Spec-Id`.
- **Body** — author per `briefing/compliant-issue-template.md`. Replace every
  `#J1`-style internal reference with the actual GH issue number once
  predecessors are filed. Mapping lives at
  `.coach-v9-bootstrap/mapping/internal-to-gh.json`.
- **Labels** — apply on creation:
  - `atdd-issue`, `atdd:INIT`
  - `track-<track-letter>` (e.g., `track-j`, `track-c0`)
  - `wave-w<N>` (per the spec issue, e.g., `wave-w1`)
  - `archetype:coach` plus any extra archetype the table above prescribes
  - For C0 only: also `coordination`
  - For absorbed-from-orchestrate-or-babysit issues: also `absorbed`
  - For `K5` and `L8`: also `parity-test`, `gating-decommission`
  - For `P5` and `P6`: also `decommission`
  - For substrate-aware tracks (K2, L5, M3, M5): also `substrate-integration`

## Train / Wagon trailer in the body

Inside the **Issue Metadata** table (per #477/#481), set:

| Field | Value |
|-------|-------|
| Train | `0002-coach-drives-lifecycle` |
| Wagon | `<wagon from table above>` |
| Archetypes | `<archetypes from table above>` |
| Type | `implementation` (default) |
| Internal-Spec-Id | `<C0 \| J1 \| K2 \| ...>` |

No "(proposed)" suffix anywhere — the train YAML and wagon manifests land
BEFORE issues file, so all URN bindings are real.
