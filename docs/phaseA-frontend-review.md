# Phase A review — coder.frontend cluster (PARTIAL de-monolith)

Atomized the **3 core-agnostic** rules of `src/atdd/coder/conventions/frontend.convention.yaml`
into single-node `nodes/` files via `atdd author convention-node --core --role coder`.
Every JSX/React/route-coverage rule (`arrow-function-*`, `function-or-*`,
`empty-fragment-*`, `self-closing-*`, `conditional-*`, `negative-rule-*`,
`trainid-*`, `resolved-train-*`) was **left in the monolith untouched**
(extension-bound; migrate in Phase B).

Rules atomized:
- `coder.frontend.boundaries-fe-layers`        (was top-level `rules:[]`)
- `coder.frontend.boundaries-fe-imports`       (was top-level `rules:[]`)
- `coder.frontend.allowlist-entry-must-include` (was nested `frontend.no_stub_presentation.rules`)

## Pass 1 — extraction fidelity (high_fidelity)

| field | boundaries-fe-layers | boundaries-fe-imports | allowlist-entry-must-include |
|-------|----------------------|-----------------------|------------------------------|
| statement (= description verbatim) | ✓ | ✓ | ✓ |
| severity | 3 ✓ | 3 ✓ | 2 ✓ |
| disposition | documentation-only ✓ | documentation-only ✓ | documentation-only ✓ |
| aliases | BOUNDARIES-FE-LAYERS-001 ✓ | BOUNDARIES-FE-IMPORTS-001 ✓ | PRESENTATION-NOSTUB-010 ✓ |
| introduced_in | 1.67.0 ✓ | 1.67.0 ✓ | 1.67.0 (source had none; sibling NOSTUB family is 1.67.0) |
| implementation / validator | none (documentation-only) ✓ | none ✓ | none ✓ |
| source.* | legacy_path + legacy_section=`rules` + legacy_rule_id + high_fidelity ✓ | `rules` ✓ | legacy_section=`frontend.no_stub_presentation.rules` (precise nested location) ✓ |

- All three rules are `disposition: documentation-only` in the monolith, so — per the
  reverse-coherence contract (`test_rule_validator_binding`) — the nodes carry **no**
  `implementation`/`validator:` field. This mirrors the committed documentation-only
  coder nodes (`coder.dto.placement`, `coder.presentation.layer-is-thin`).
- One `term` synthesized per node (matching the proven committed pattern); a concise,
  faithful `content.fix_hint` was derived from each rule's own description — no new
  normative scope introduced.
- `allowlist-entry-must-include` source statement had no `introduced_in`; its NOSTUB
  sibling family is `1.67.0`, used for consistency (documentation-only — advisory only).

## Pass 2 — partial de-monolith correctness

- Top-level `rules:[]` held **exactly** the two boundaries rules; both removed and the
  block reduced to `rules: []` with a comment marking the move and that the nested
  JSX/route-coverage families remain for Phase B.
- The single `PRESENTATION-NOSTUB-010` entry removed from
  `frontend.no_stub_presentation.rules`; a comment marker notes the move and that the
  remaining `arrow-function-*` … `negative-rule-*` stub rules stay.
- **No migration marker claiming the whole file moved** — it didn't; the large
  `frontend:` layer-catalog and all EXT rules remain.
- `test_no_duplicate_rule_representation` green: no rule_id (or alias) lives in both a
  monolith `rules:[]` block and a `nodes/` file.
- **Monolith-reading test strengthened, not weakened:**
  `test_no_stub_presentation_rules_declared_in_convention` now merges `conventions/nodes/`
  (rule_id + `metadata.severity`) into its `rules_by_id` so the migrated allowlist rule
  satisfies the contract from its canonical `nodes/` location with severity 2 intact.

## Pass 3 — graph wiring / no orphans

- All 3 new rule_ids are relationship endpoints in `relationships.yaml`:
  - hub `coder.frontend.boundaries-fe-layers` → `boundaries-fe-imports` (runs_alongside)
  - hub `coder.frontend.boundaries-fe-layers` → `allowlist-entry-must-include` (runs_alongside)
- `test_no_orphan_nodes` green (clean baseline 0). `test_sentinels` green.
- `build_registry()` resolves all 3 nodes (disposition=documentation-only, validator=None)
  and the 3 aliases map back to their canonical ids.

## ⚠ Flag for overseer (STEP 4)

No semantic-mirror of an existing core node was found for any of the 3 rules, so **no
`refines` edge** was added.
- `boundaries-fe-layers` / `boundaries-fe-imports` are the *frontend* (4-layer, pragmatic
  hooks-can-import-integration) counterparts of the backend boundary rules; they are
  intentionally distinct (the frontend dependency policy differs — see the monolith
  `dependency:` note), not restatements.
- `allowlist-entry-must-include` is wired to the frontend hub as a `runs_alongside` peer
  even though it belongs to the NOSTUB presentation-quality family (still in the monolith
  until Phase B); this keeps it a non-orphan endpoint without prematurely coupling it to
  rules that haven't been atomized yet.

## Verification

`PYTHONPATH=src … pytest test_no_orphan_nodes test_sentinels test_rule_validator_binding
test_no_duplicate_rule_representation src/atdd/coder/validators/` → **197 passed, 112
skipped, 0 failed** (warnings are pre-existing advisory disposition notices, unrelated to
this slice).
