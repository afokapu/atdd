# Compliant ATDD issue body template

Drawn from #477 and #481. Every coach-v9 issue must follow this structure.
Sections marked **REQUIRED** are non-negotiable; **OPTIONAL** sections may
be omitted if not applicable but should be flagged with "N/A — <reason>"
rather than silently dropped when material to the issue.

---

## Title (REQUIRED)

`feat(coach): <terse imperative summary, ≤70 chars>` for new features.
`fix(coach): <terse summary>` for fixes.
Do NOT prepend the issue number to the title — GitHub does that. Internal
spec IDs (C0, J1, …) belong only in the body's metadata, not the title.

---

## Body sections

### `## Issue Metadata` (REQUIRED)

Markdown table, exactly these rows in this order:

```
| Field | Value |
|-------|-------|
| Date | `YYYY-MM-DD` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | `feat/<kebab-slug>-<short-id>` |
| Archetypes | `coach` (and any extras per track-wagon-map) |
| Train | `0002-coach-drives-lifecycle` |
| Wagon | `<wagon name per track-wagon-map.md>` (e.g., `freeze-runtime-contracts`) |
| Internal-Spec-Id | `<C0|J1|K2|…>` (the v3-spec internal ID; only on coach-v9 issues) |
| Feature | <one-line feature summary, identical to or compatible with the
            wagon-feature YAML's description> |
```

### `---` separator (REQUIRED)

### `## Scope` (REQUIRED)

Three subsections:

#### `### In Scope`
Bullets for everything this issue delivers. Be exhaustive. Reference exact
file paths where known (`src/atdd/coach/commands/coach.py`, etc.). State
the rule_id any new validators emit. State the schema any new artifact
conforms to.

#### `### Out of Scope`
Bullets for the lookalikes that callers might confuse with this issue.
At minimum, name every issue elsewhere in the v3 spec that overlaps
boundary concerns and clarify the boundary.

#### `### Dependencies`
Bullets. Each bullet is one of:
- `#<GH#>` — when the predecessor coach-v9 issue is already filed; substitute
  the actual GH number from `.coach-v9-bootstrap/mapping/internal-to-gh.json`.
- An existing repo path/symbol — when the dep is on shipped machinery.
Pre-filing draft uses placeholder `#<INTERNAL_ID>` (e.g. `#J1`); the filing
pane substitutes real GH numbers in topological order.

### `---` separator (REQUIRED)

### `## Context` (REQUIRED)

Three subsections:

#### `### Problem Statement`
Markdown table with columns `| Aspect | Current | Target | Issue |` —
3-6 rows summarising the structural gap this issue closes. Each Aspect
is one slice of the system; Current = today's state; Target = the
state after this issue lands; Issue = why the gap matters.

#### `### User Impact`
1-3 paragraphs. For coach-v9 internals, the "user" is usually a coach
operator, downstream toolkit consumer, or an agent under coach orchestration.
State concretely what fails today (or fails to be possible) and what
becomes possible after this issue. Reference the v3-spec section
(e.g., "Per spec §6.4 step 4, …") where useful.

#### `### Root Cause` (OPTIONAL — include only if there's a concrete
existing-code root; for greenfield C0/J1-style issues, replace with
`### Design Anchor` describing why the chosen abstraction matches the
v3-spec.)

### `---` separator (REQUIRED)

### `## Acceptance` (REQUIRED)

Bulleted list. Each bullet is one acceptance criterion. Cross-reference
the corresponding `acc:<wagon>:<WMBT-ID>-<HARNESS>-<NUM>-<slug>` URN
created in the wagon's WMBT YAML. Example:

- `acc:drive-state-machine:J1-UNIT-001-state-machine-skeleton`:
  `atdd coach 358` initializes a state machine in INIT for issue 358 and
  prints the planned state path without executing transitions.
- `acc:drive-state-machine:J1-UNIT-002-flag-parsing`: All §5.1 flags
  parse correctly (verified by `atdd coach --help` output match).
- `acc:drive-state-machine:J1-INTEGRATION-001-no-scope-leak`: Code review
  confirms no scope leak into J5/M3/L1/K1/J4/J3/J6 territory.

Where the v3-spec issue body has plain bullets, lift them verbatim and
prepend the matching `acc:` URN — do not invent new criteria.

### `---` separator (REQUIRED)

### `## References` (REQUIRED)

Bulleted list of pointers:
- `atdd-coach-spec-v9.md §<sections>`
- `atdd-coach-issues-v3.md` issue `#<INTERNAL_ID>`
- Wagon manifest `plan/coach_<wagon-slug>/_<wagon-slug>.yaml`
- Predecessor issues by GH number
- Substrate v12 spec sections when relevant

---

## Body length expectation

Compliant issues run 80–250 lines (cf. #477's ~250 lines, #481's ~120 lines).
Coach-v9 issues whose v3-spec body is terse (~20 lines) need expansion via
the Problem Statement table and User Impact paragraphs to reach this floor.
Do NOT pad — every sentence carries weight. If a section truly has nothing
to add, write `N/A — <reason>` and move on.

---

## Final checklist before filing (the filer pane runs through this)

- [ ] Title ≤70 chars, prefix matches `feat(coach):` or `fix(coach):`
- [ ] Issue Metadata table present, all REQUIRED rows populated
- [ ] Train = `0002-coach-drives-lifecycle` (no parenthetical)
- [ ] Wagon = `<wagon name from track-wagon-map.md>` (no parenthetical), and the wagon manifest exists at `plan/<wagon-snake-case>/_<wagon-snake-case>.yaml`
- [ ] Every `#<INTERNAL_ID>` in the body has been rewritten to `#<GH#>` per the mapping
- [ ] Every `acc:<wagon>:<WMBT-ID>-...` in Acceptance resolves to a YAML in the wagon directory
- [ ] Labels applied on creation per track-wagon-map.md
- [ ] Mapping file updated with the new GH issue number
