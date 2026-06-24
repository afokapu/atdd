# Shadow-Run Report (#1207)

> ⚠️ **STRUCTURAL PARITY ONLY — BEHAVIORAL PARITY IS NOT ESTABLISHED.**
>
> - Convention variants currently validate **metadata/scaffolding**, not real graph traversal.
> - **Legacy validators remain authoritative.** They are the only enforcement in effect.
> - **Decommission is BLOCKED.** No legacy validator may be removed or shimmed.
> - This report does **not** claim zero P0 behavioral gaps. Behavioral P0 gaps are
>   **unknown/unverified** until the #1206 graph-traversal engine + fixture-backed
>   shadow harness prove each target variant catches its legacy counterpart's failure class.

## What is true today (structural)

- Every buildable P0/P1 `direct`/`split`/`merged` legacy validator has a **target
  variant file** at its mapped path with the template metadata contract +
  `LEGACY_PARITY_SOURCES`. (See `legacy-validator-map.yaml`.)
- Target variants and legacy validators **run in parallel** without collision.

## Progress (P0 template engine — landed under #1206)

- `_support/graph_loader.py` composes plan sources into a real node graph;
  `_support/evaluators.py` implements the **8 P0 template engines**;
  `TemplateContract.evaluate()` makes archetypes **executable** (selector →
  traversal → invariant → evidence).
- Per-family good/bad fixtures exist for the 6 P0 families; the fixture-backed
  shadow harness (`tests/test_shadow_parity.py`, driven by `legacy-validator-map.yaml`)
  is **green** — each P0 template catches a representative bad case and emits
  template-shaped evidence.

## What is STILL NOT established (behavioral parity vs legacy)

- The shadow harness proves parity at the **template/fixture level**, NOT per
  legacy-validator scenario. Fixtures are representative per template — they are
  **not** cloned from each legacy validator's actual logic, and no real
  **legacy-vs-convention diff on identical inputs** has been run.
- P1 + the remaining 14 of 22 templates have **no engine yet**.
- The live fault-injection gap still stands: legacy `theme.must-be-canonical`
  catches a non-canonical wagon theme; wiring each variant to run against the live
  graph is not done.

## Measured gap (P0)

See `p0-legacy-vs-convention-gap-report.md`: **0 of 32 P0 pairs are behaviorally
verified vs legacy.** All 32 are GAP — the template engines detect nothing on the
real composed graph (they pass only against hand-authored fixtures), and only 2/32
legacy validators expose a callable API to diff against. Real parity requires
per-rule convention checks wired to the real graph + a diff per pair.

## Decommission gate (ALL must hold before ANY legacy removal)

- [x] #1206 graph-traversal engine implemented — **P0 only** (8 of 22 templates)
- [x] family `archetype.py` executes selector → traversal → invariant → evidence — **P0 only**
- [x] per-family fixtures: known-good passes, known-bad fails — **P0 families only**
- [x] target variant emits template-shaped failure evidence — **P0 only**
- [ ] shadow harness shows, **per pair, that the target catches the same failure
      class as the actual legacy validator** (real diff, not representative fixture)
- [ ] every P0 *legacy* validator's specific scenario verified (not just its template)
- [ ] P1 + remaining template engines implemented
- [ ] zero unverified P0 pairs in a legacy-vs-convention gap report

Until every box is checked, **legacy is authoritative and nothing is decommissioned.**
