# Phase A Review — coder.technology governance atomization

Scope: atomize the 3 **governance** rule ids from
`src/atdd/coder/conventions/technology.convention.yaml` into
`src/atdd/coder/conventions/nodes/`. The concrete technology STACK-TREE
(Supabase/Flutter/etc. defaults — extension-bound) is **intentionally left**
in the monolith.

## Pass 1 — High-fidelity extraction

| rule_id | statement (verbatim from `description`) | severity | disposition | aliases | introduced_in |
|---|---|---|---|---|---|
| coder.technology.new-components-default-to | New components default to the technology.<layer>.default for their layer; deviations declare an approved alternative | 2 | documentation-only | COACH-TECH-STACK-001 | 1.66.0 |
| coder.technology.approved-alternatives-are-taken | Approved alternatives are taken only when the use_when criteria are met; tradeoff is documented in the wagon | 2 | documentation-only | COACH-TECH-STACK-002 | 1.66.0 |
| coder.technology.unapproved-technology-choices-require | Unapproved technology choices require a SPEC edit before they can ship | 2 | documentation-only | COACH-TECH-STACK-003 | 1.66.0 |

- Statements copied verbatim from the monolith `description` fields.
- `metadata` preserves `severity`, `disposition`, `aliases`, `introduced_in`.
- `source` block records `legacy_path`/`legacy_section: rules`/`legacy_rule_id`
  with `extraction_mode: high_fidelity`.
- **No `implementation` block** — these are `documentation-only` rules with no
  Python validator (grep confirmed no `bind_rule`/reference for the ids or the
  `COACH-TECH-STACK-*` aliases). Mirrors the dto precedent (same disposition).
- A single-line `content.fix_hint` and a clarifying `terms` entry were added per
  the atomization template (pure documentation; no binding impact).

## Pass 2 — Partial de-monolith integrity

- Deleted **only** the 3 governance rule blocks (the `rules:` list) from
  `technology.convention.yaml`.
- The entire `technology:` STACK-TREE (backend/frontend/media/ai/telemetry
  defaults, alternatives, rationales, cost comparisons, fallback paths) and the
  trailing `notes:` block are preserved **verbatim**.
- A replacement comment points readers to the atomized nodes and explicitly
  marks the stack-tree as extension-bound / do-NOT-atomize.

## Pass 3 — Graph wiring (no orphans)

- Hub = `coder.technology.new-components-default-to` (the foundational
  layer-default selection rule).
- Two `runs_alongside` edges (mirroring dto/frontend precedent), hub → each peer:
  - hub → `coder.technology.approved-alternatives-are-taken`
  - hub → `coder.technology.unapproved-technology-choices-require`
- All 3 node ids therefore appear as a `source_ref` or `target_ref`; none orphaned.

## Verification

```
PYTHONPATH=src .../python -m pytest \
  src/atdd/validators/conventions/coverage/test_no_orphan_nodes.py \
  src/atdd/validators/conventions/tests/test_sentinels.py \
  src/atdd/coach/validators/test_rule_validator_binding.py \
  src/atdd/coach/validators/test_no_duplicate_rule_representation.py \
  src/atdd/coder/validators/ -p no:cacheprovider -q
→ 197 passed, 112 skipped, 3 warnings  (0 failures)
```

The 3 warnings are pre-existing advisories (xlang-entity / xlang-contract /
hierarchy-coverage) unrelated to this slice.
