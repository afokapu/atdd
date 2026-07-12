# #1207 — Decommission legacy persona validators after convention parity

**Status:** REFACTOR. Infra prerequisites now MET; ready to begin Tier-1 retirement in batches.

This issue is a **reusable runbook**, not a planner+coach one-off. The same process retires
legacy validators for **planner, coach, tester, and coder** as each persona's convention
variants reach "executing + parity". Run the manifest script to get the current ready-set.

## Preconditions (both now in place, persona-agnostic)
1. **`conventions/` gates in CI** — `validate-conventions` job in `atdd-validate.yml`
   (+ gate `needs` + Check-results). Coverage *moves* to the convention layer rather than
   dropping when legacy is deleted. (was the hard blocker)
2. **`implementation.ref` is the live binding** — the engine ingests single-node author
   nodes and resolves `implementation.ref` (graph_loader two-pass + binding resolver), so a
   rule can bind to its convention variant. (#1212 a-fix)

## The ready-set (deterministic)
`scripts/decommission_manifest.py` (READ-ONLY) → `docs/validator-parity/decommission-manifest.md`.
Lists, per legacy validator referenced by a convention variant: the covering variant, whether
it **executes** (vs RED-stub), and the **rule(s) to repoint**. Current snapshot: **32
decommission-ready** candidates (planner+coach), 77 not-ready (CLAUDE.md-deferred + conservative).
**Verdict authority = `docs/validator-parity/family-parity-report.md`** — only retire `both`
(Tier-1); adjudicate `convention-only` (Tier-2) and `function-level`/`hermetic` (Tier-3)
separately.

## Runbook — per legacy file, atomic
1. **Repoint** the rule's `implementation.ref`/`validator` → the convention variant's nodeid
   (or `disposition: documentation-only` if intentionally unenforced). [coupling: rule decl]
2. **Delete** the legacy validator test file. [coupling: importers — confirm none]
3. **Drop the legacy-oracle assertion** in the convention variant (the `subprocess pytest
   <legacy nodeid>` cross-check). Parity is already proven/recorded; the variant's own
   clean-baseline + fault-injection remain the live coverage. [coupling: parity tests]
4. **CI-gate** the batch (`validate-conventions` + persona jobs green).

## Guard (committed with the pass — proves coverage didn't drop)
- **no dangling legacy reference**: no rule's `implementation.ref` points to a deleted
  `*/validators/test_*.py` persona-folder path.
- **coverage preserved**: each retired rule's convention variant *executes* (real traversal),
  not a RED `xfail` stub.

## Discipline
- **Batches** (per family / ~5 files), reversible per batch — not 31-at-once.
- **Tier-1 only** this pass. Tier-2/Tier-3 are separate decisions.
- Process is **persona-generic**: re-run `decommission_manifest.py` for tester/coder later;
  same runbook + guard apply.

## Done-when
All Tier-1 legacy validators retired, guard green, `validate-conventions` + persona CI green,
`family-parity-report.md` updated to "retired", with operator sign-off per batch (or upfront).
