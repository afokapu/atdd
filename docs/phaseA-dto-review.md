# Phase A review — coder `dto` cluster atomization

Cluster: `src/atdd/coder/conventions/dto.convention.yaml` → `nodes/`
Pattern source: `tester.acceptance-violation.*` (proven, committed).

## Pass 1 — completeness

The monolith `rules:` block declared exactly three rules, all core-agnostic
(no stack-specific EXT rule present → nothing skipped per the EXT stop-rule):

| legacy id            | node file                                  |
|----------------------|--------------------------------------------|
| `coder.dto.placement`| `nodes/coder.dto.placement.convention.yaml`|
| `coder.dto.purity`   | `nodes/coder.dto.purity.convention.yaml`   |
| `coder.dto.mapper`   | `nodes/coder.dto.mapper.convention.yaml`   |

All three authored via `atdd author convention-node --core --role coder`.
The monolith `rules:` list was removed and replaced with the migration-marker
comment (same shape as `acceptance-violation.convention.yaml`). No rule dropped,
none added.

## Pass 2 — fidelity

Every legacy field preserved into the node form:

- `id` → `rule_id`
- `description` → `statement` (verbatim)
- `severity` (3) → `metadata.severity`
- `disposition` (`documentation-only`) → `metadata.disposition`
- `aliases` (`DTO-*-001`) → `metadata.aliases`
- `introduced_in` (`1.67.0`) → `metadata.introduced_in`
- provenance → `source.{legacy_path,legacy_section,legacy_rule_id}` +
  `extraction_mode: high_fidelity`

`terms` is required by the authoring schema (§5.2) but the legacy doc-only rules
carried none, so one term per rule was synthesized from the rule's own central
concept (`contract_dto`, `dto_purity`, `dto_mapper`) — definitional only, adding
no new normative force. These rules are `documentation-only` with no validator
binding, so no `implementation`/`fix_hint`/`recipe` was fabricated (faithful:
the legacy rules had none).

## Pass 3 — graph wiring + green

Intra-cluster hub wired in `src/atdd/coach/graph/relationships.yaml`, mirroring
the tester hub (`acceptance-must-be-measurable` → peers via `runs_alongside`):

- `coder.dto.placement` → `coder.dto.purity`  (`runs_alongside`)
- `coder.dto.placement` → `coder.dto.mapper`  (`runs_alongside`)

All three rule_ids now appear as relationship endpoints → no orphans.

Verification (0 failures):

```
src/atdd/validators/conventions/coverage/test_no_orphan_nodes.py
src/atdd/validators/conventions/tests/test_sentinels.py
src/atdd/coach/validators/test_rule_validator_binding.py
src/atdd/coach/validators/test_no_duplicate_rule_representation.py
src/atdd/coder/validators/
→ 197 passed, 112 skipped, 3 warnings (pre-existing advisories, unrelated)
```

No-duplicate-representation green confirms the rule now lives in exactly one
place (nodes/), not both the monolith and nodes/.
