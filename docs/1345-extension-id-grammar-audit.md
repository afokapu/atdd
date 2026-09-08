# #1345 — Audit: extension-ID grammar assumptions in core

**Issue:** afokapu/atdd#1345 · **Parent protocol:** #1343 · **Rename:** #1344
**Store artifact (SoT):** work_item uid
`audit-validators-enforcement-and-substrate-binding-for-extension-id-assumptions`
(shared parent store `/.atdd/state/state.sqlite`, external_ref `github/issue/1345`).

## Scope of this deliverable (Option 2 — audit-only)

This issue is an **audit**. It catalogs every core path that parses, validates,
stores, loads, or compares extension package IDs and records a disposition for
each. It **does not** flip the grammar live: the persona-aware split
(`<publisher>.extension.<persona>.<artifact-name>`) is enumerated in parent
**#1343**'s "Expected core changes," and the installed official extensions stay
three-segment until **#1344** renames them. Flipping here would (a) collide with
#1343 and (b) reject the still-installed three-segment official extensions before
#1344 lands.

Therefore the acceptance criterion *"Store/lock/install paths work with
four-segment extension IDs"* is **GATED on #1343 + #1344**. This PR delivers the
audit + a **prepared-migration** boundary test (xfail, `strict=True`) that will
flip to XPASS — and fail the `strict` xfail, prompting removal — the moment
#1343 makes the grammar persona-aware. No `author_context` change rejects
three-segment IDs here; no compatibility aliases are introduced (a #1345
non-goal).

## Method

Search strings from the issue body, run across `src/atdd/**` (`*.py`, `*.json`,
`*.yaml`, `*.yml`):

```
atdd.extension.coder   atdd.extension.tester   extension_id
validate_extension_id  extension_package_home  .atdd/extensions
substrate.lock         <publisher>.<scope>.<artifact-name>   expected_scope
```

"Proof no old-grammar assumption survives" = two structural facts established by
the sweep:

1. **Exactly one** regex in the codebase encodes the package-ID grammar —
   `_PKG_ID_RE` at `author_context.py:26`. No duplicate three-segment pattern
   exists in validators, enforcement, substrate, or schemas.
2. **No** code parses a package ID by segment position. The only `.rsplit`/index
   on an ID (`_name_of`, `author_init.py:41`) uses `rsplit(".", 1)[-1]` — the
   **last** segment — which is four-segment-safe. (`[2]`/`parts[2]` hits in the
   sweep are `wagon:`/interlocking URNs, not package IDs.)

Consequence: the single behavioral migration lives in `_PKG_ID_RE` /
`_validate_package_id` (owned by #1343). Every other path carries the ID as an
**opaque string** — a dict value, a directory segment, a lock/manifest field —
and already works with a four-segment ID unchanged.

## Checked file list (issue scope checklist)

Disposition legend — **MIGRATE(#1343)**: behavioral change owned by #1343;
**N/A-opaque**: ID handled as an opaque string/path, four-segment-safe as-is;
**N/A-none**: path does not touch extension IDs; **TEST**: covered by the
prepared boundary test / current fixtures unaffected.

| Path | Disposition | Note |
|------|-------------|------|
| `planner/commands/author_context.py` | **MIGRATE(#1343)** | `_PKG_ID_RE` (L26) is the **sole** grammar regex; `_validate_package_id` (L32) is the shared spine both `validate_extension_id` (L65) and `validate_workspace_id` (L77) delegate to. #1343 splits extension → four-segment persona-aware, workspace stays three-segment, and validates persona ∈ {planner,tester,coder,coach}. Path builders (`extension_package_home` L149, node/relationship/scope/gate homes L162–193) use the ID as an **opaque dir segment** → four-segment-safe. Audit anchor comment added at the grammar block. |
| `planner/commands/author_init.py` | **N/A-opaque** | Scaffolder writes `extension_id` verbatim into the manifest and derives the package dir via `extension_package_home`. `_name_of` (L41) = `rsplit(".",1)[-1]` → last segment, four-segment-safe. Only the docstring says `<publisher>.<scope>.<name>` — stale wording, not a code assumption; refreshed to note segment-count-agnostic. |
| `planner/commands/author_manifest.py` | **N/A-opaque** | L179 delegates to `validate_extension_id`; carries no independent grammar. Behavior follows #1343 automatically. |
| `planner/commands/author.py` | **N/A-opaque** | `--extension` arg help strings say `<publisher>.extension.<name>` (L961) — doc text, updated by #1343 alongside the grammar; no parsing. |
| `planner/commands/compose.py` | **N/A-opaque** | Reads `manifest.get("extension_id")` (L284/334/371) as an opaque view/edge key. No segment parsing. |
| `substrate/admission.py` | **N/A-opaque** | L124 `manifest.get("extension_id") or manifest.get("workspace_id")` — opaque `package_id`. Admission never parses it. |
| `substrate/installer.py` | **N/A-opaque** | Records `installed_path = .atdd/extensions/<id>/<version>` — ID as a path segment; four-segment-safe. |
| `substrate/binding/` (`plan.py`, `lock_loader.py`, `resolver.py`, `commands.py`) | **N/A-opaque** | Binds by lock digest + enabled flag; the only `.split(".")` (`resolver.py:38`) is on the **version**, not the ID. |
| `planner/schemas/*.schema.json` (`substrate.schema.json`, `substrate-lock.schema.json`, `binding-lock.schema.json`) | **N/A-none** | `grep -l extension_id *.schema.json` → **no schema constrains `extension_id`**. Patterns exist only for `schema_version`/`version`/`digest`. Four-segment IDs already validate. |
| `enforce/` | **N/A-none** | **Zero** extension-ID references in the entire package. No enforcement path hardcodes the grammar. |
| Tests & fixtures (`substrate/tests/**`, `substrate/binding/tests/**`, `planner/commands/tests/**`, `state/tests/**`) | **TEST** | All use three-segment IDs (`acme.extension.demo`, `bromohub.extension.*`, `atdd.extension.demo`). Under audit-only they remain valid and green — **no fixture change needed**. The renaming of official three-segment fixtures/installed packages is **#1344**. |
| Workspace impl manifests referring to owning extension packages | **N/A-opaque** | Reference owning package by opaque ID string; four-segment-safe. Renames tracked by #1344. |

## Acceptance criteria — status

- [x] The audit produces a checked list of all affected files. *(table above)*
- [x] Any old-grammar assumption is migrated or explicitly documented N/A.
      *(single MIGRATE site → #1343; all others N/A with reason)*
- [x] No validator/enforcement path hardcodes the old three-segment extension
      grammar **except** the one intended, single-sourced site (`_PKG_ID_RE`),
      whose migration is owned by #1343. `enforce/` has none.
- [ ] **Store/lock/install paths work with four-segment extension IDs.**
      *Structurally ready today (all opaque); the grammar that accepts a
      four-segment ID is **GATED on #1343**. Proven by the xfail boundary test.*
- [x] Existing workspace IDs continue to validate with their current grammar.
      *(workspace three-segment invariant asserted by a passing boundary test)*
- [x] Tests cover both extension and workspace grammar boundaries.
      *(prepared-migration boundary tests, this PR)*

## Non-goals held

- No planner/coach extraction from core.
- No rule-ID grammar change (`coder.*` / `tester.*` untouched).
- No compatibility aliases (old→new).
- No `author_context` change that rejects three-segment IDs (deferred to #1343).
- No installed-package rename / `substrate.lock` digest churn (that is #1344).

## Follow-ups this audit hands to the parent work

- **#1343** — split `_PKG_ID_RE`/`_validate_package_id`: extension →
  `<publisher>.extension.<persona>.<artifact-name>`, persona ∈
  {planner,tester,coder,coach}; workspace stays three-segment; refresh the
  `<publisher>.<scope>.<name>` doc/help strings in `author_context.py`,
  `author_init.py`, `author.py`. When it lands, the xfail boundary tests XPASS
  (strict) → remove the `xfail` marks.
- **#1344** — rename installed `atdd.extension.coder`/`tester` →
  `.coder.base`/`.tester.base` and the three-segment fixtures accordingly.
