# Tier-1 legacy-validator decommission runbook (canonical)

> **HISTORICAL — the scaffolding this runbook drives was retired in #1385.**
> `scripts/decommission_manifest.py` (the pre-flight classifier),
> `docs/validator-parity/legacy-validator-map.yaml`, and the Y001/Y002 guards no longer
> exist. The sweep they supported is complete, so the commands below will not run. The
> document is kept as the historical record of the procedure and of the two batches whose
> failures shaped it.

> Supersedes the batch-1 addendum embedded in issue **#1207**. This file is the single
> canonical procedure for safely retiring a **rule-bound** legacy validator once its
> convention variant is executing at parity. Run the pre-flight classifier first; then
> apply the four steps per file; the two named CI catches are the backstop.

## 0. Pre-flight — classify before you delete

```
PYTHONPATH=src python3 scripts/decommission_manifest.py
```

`scripts/decommission_manifest.py::classify` is **READ-ONLY**. For every
decommission-READY candidate (its convention variant *executes*, not a RED stub) it emits:

- a **label set**:
  - **PLATFORM** — no rule binding and no `# Acceptance:` header → clean delete (skips steps 1 + 2).
  - **RULE-BOUND** — a rule's `implementation.ref`/`validator` points at the legacy file → needs the repoint (step 1).
  - **ACCEPTANCE-ANCHORED** — the legacy test carries a `# Acceptance: acc:…` header → needs acceptance handling (step 2). A candidate can be BOTH RULE-BOUND and ACCEPTANCE-ANCHORED.
- the candidate's **current `legacy-validator-map.yaml` status**: `parity_status` and whether
  the recorded `proposed_target_path` resolves to an existing convention variant
  (`delete-ready=False` is a hard pre-flight stop — it is exactly what tripped batch 2).
- the **exact required steps**, with the responsible CI catch named on steps 1 and 2.

Verdict authority for *which* files are Tier-1 is `docs/validator-parity/family-parity-report.md`
(only retire `both`); the classifier tells you *what each retirement needs*.

## The four steps (per legacy file, atomic, reversible per batch)

1. **REPOINT** *(RULE-BOUND only)* — point each bound rule's `implementation.ref`/`validator`
   at the **convention variant nodeid** (or set `disposition: documentation-only` if intentionally
   unenforced). Equivalently, ensure the `legacy-validator-map.yaml` entry's
   `proposed_target_path` names the **shipped** variant file (not a planned/renamed filename)
   and `parity_status` is one of `{direct, split, merged, superseded}`.
2. **ACCEPTANCE** *(ACCEPTANCE-ANCHORED only)* — if the legacy test anchors a plan
   acceptance (`# Acceptance: acc:…`), either **retire** that acceptance (coverage has moved
   to the variant) or **re-anchor** it to a surviving test. Deleting the test without this
   orphans the acceptance.
3. **DELETE** the legacy validator test file (confirm no importers).
4. **DROP** the variant's legacy-oracle assertion (the `subprocess pytest <legacy nodeid>`
   cross-check). Parity is already proven/recorded; the variant's own clean-baseline +
   fault-injection remain the live coverage.

Then **CI-gate** the batch: `validate-conventions` + persona jobs green.

## The two CI catches (the backstop — do not rely on them, satisfy steps 1–2)

- **`test_no_unsafe_legacy_deletion`** (Y001,
  `src/atdd/validators/conventions/tests/test_y001_no_unsafe_deletion.py`) — fails if a
  legacy file is deleted while its map entry's `parity_status` is **not** in
  `{direct, split, merged, superseded}` **or** its `proposed_target_path` does **not**
  resolve. This is the **un-repointed implementation binding** catch (batch 2, #1260:
  `test_e026…` deleted with `proposed_target_path: …/test_bypass_inventory_baseline.py`
  while the shipped variant is `…/test_bypass_inventory.py`; same for `test_e032…`).
- **`tester.acceptance-violation.validator-binding-must-be-bidirectional`**
  (`src/atdd/validators/conventions/binding/test_validator_binding_bidirectional.py`) — fails
  if a plan acceptance has a `harness` but its anchoring validator no longer exists. This is
  the **orphaned acceptance** catch (batch 1, #1255: `e009`/`e032` anchor
  `acc:govern-lifecycle:E009-UNIT-001` / `acc:spawn-agents:E032-SMOKE-001`).

## Lessons banked from the two batches

| batch | PR | tripped | root cause | pre-flight signal now |
|---|---|---|---|---|
| 1 | #1255 | `validator-binding-must-be-bidirectional` | deleted an acceptance-anchored test → orphaned acceptance | candidate labelled **ACCEPTANCE-ANCHORED**, step 2 required |
| 2 | #1260 | `test_no_unsafe_legacy_deletion` | `proposed_target_path` named the planned filename, never repointed to the shipped variant | candidate shows `delete-ready=False`, FIX-map step emitted |

## Discipline

- **Batches** (per family / ~5 files), reversible per batch — never 31-at-once.
- **Tier-1 only** (`both` parity). Tier-2/Tier-3 are separate decisions.
- Process is **persona-generic**: re-run the classifier for tester/coder later; same four
  steps + two catches apply.
