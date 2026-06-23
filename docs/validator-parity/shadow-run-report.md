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

## What is NOT true yet (behavioral)

- Target variants do **not** execute `selector -> traversal -> invariant ->
  failure evidence` against the composed convention graph. The `_support` engine
  (`convention_loader`, `graph_loader`, `node_index`, `rule_index`, `package_index`,
  `assertions`, `report_adapter`) is **not implemented**; `archetype.py` modules
  only expose template IDs/metadata, they do not evaluate.
- A live fault-injection proves the gap: a non-canonical wagon theme is **caught by
  the legacy** `theme.must-be-canonical` validator but the convention `grammar`
  variant is **blind** (passes) — the same failure class is NOT yet caught by the target.

## Decommission gate (ALL must hold before ANY legacy removal)

- [ ] #1206 graph-traversal engine implemented (`_support/*` executable)
- [ ] every family `archetype.py` executes selector → traversal → invariant → evidence
- [ ] per-family fixtures: known-good passes, known-bad fails
- [ ] target variant emits template-shaped failure evidence
- [ ] fixture-backed **shadow harness** (driven by `legacy-validator-map.yaml`) shows,
      per pair, that the target catches the **same failure class** as legacy
- [ ] zero unverified P0 pairs in the shadow harness gap report

Until every box is checked, **legacy is authoritative and nothing is decommissioned.**
