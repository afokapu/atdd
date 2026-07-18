# ATDD State Projection Collaboration Model — Corrected Architecture and Delivery Plan

**Status:** Corrected implementation specification  
**Scope:** ATDD core repo + GitHub extension repo  
**Decision:** Core becomes git-native and provider-free. GitHub Issues becomes an optional mirror extension, not a lifecycle dependency.

---

## 1. Executive correction

The corrected model is:

> The local store is the private authoring workspace for uncommitted work. The committed deterministic projection is the shared source of truth. Git history plus structured ATDD trailers is the audit/event log. Git is the collaboration hub. CI is the merge authority. GitHub Issues is a non-authoritative human mirror implemented as an extension.

This replaces the earlier ambiguity around “the store is the source of truth.” The scoped truth rule is mandatory:

| Scope | Authoritative source | Why |
|---|---|---|
| Uncommitted local work | `.atdd/state/state.sqlite` local store | Fast private authoring workspace; can contain local overlay. |
| Shared project state | `.atdd/state/projection/<uid>.yaml` | Committed, deterministic, visible to peers and CI. |
| Audit/event order | Git commits + structured ATDD trailers | Reproducible event chain; no GitHub API needed. |
| Human dashboard | GitHub Issues | Mirror only; never consulted by lifecycle decisions. |

The architectural through-line is simple: local commands author in the store, projection materializes the shareable state, Git transports it, CI validates it, and GitHub only mirrors it.

---

## 2. Corrected architecture

### 2.1 Components

| Component | Path / form | Committed? | Authoritative for | Read by |
|---|---:|---:|---|---|
| Local store | `.atdd/state/state.sqlite` | No | Private uncommitted work | Local ATDD CLI |
| Projection | `.atdd/state/projection/<uid>.yaml` | Yes | Shared committed state | CI, peers, reconcile |
| Git history + trailers | Git commits | Yes | Audit/event order | CI, humans, tools |
| GitHub Issues | API | N/A | Nothing authoritative | Humans; drift alarm only |

Identity is always immutable UID, never slug:

```yaml
uid: wi_01J7Z...
slug: feature-x
```

The filename is `.atdd/state/projection/<uid>.yaml`. Slug/title are mutable display metadata and must not drive identity or file location.

### 2.2 Core invariants

| ID | Invariant | Enforcement |
|---|---|---|
| I1 | `project(store)` is byte-identical for the same logical store. No timestamps, host paths, or unstable ordering. | Golden-file tests; CI canonicality check. |
| I2 | Projection is derived and gated, never hand-authored. | Pre-push drift gate; CI canonicality and diff validators. |
| I3 | `store = hydrate(projection @ HEAD) + local_overlay`. | `store_base_commit`; overlay event log; reconcile. |
| I4 | Every shared transition is lifecycle-legal relative to parent/merge-base. | Legal-transition validator. |
| I5 | Reconcile is not overwrite. Dirty stores must preserve local overlay. | Dirty-store gate; backup; replay; conflict report. |
| I6 | Local hooks are convenience; CI/branch protection is authority. | Equivalent server-side checks. |
| I7 | GitHub mirror is non-authoritative. | Provider seam; `external_refs` quarantine; no lifecycle reads. |
| I8 | Git history contains no secrets. | Trailer schema; no-secrets validator. |

---

## 3. Required correction: explicit overlay, not inferred magic

The key implementation correction is to make local overlay explicit.

Do not rely on diffing SQLite against a hydrated baseline as the primary overlay mechanism. SQLite contains derived data, cache data, indexes, migrations, and potentially transient fields. Inferring user intent from DB differences is fragile.

Core should maintain an explicit overlay/event layer inside the local store:

```text
state.sqlite
  object_store          # hydrated public state + current local materialization
  event_store           # durable event history known locally
  overlay_events        # uncommitted local authoring events
  metadata              # store_base_commit, schema version, dirty marker
```

Every local authoring command records an overlay event until it is committed into projection. Examples:

```text
object_created
body_updated
phase_transition_requested
train_updated
wmbt_added
tombstone_requested
external_ref_applied_by_core_from_provider_update
```

`atdd state reconcile` then becomes deterministic:

```text
store_base_commit   = commit the local store was last hydrated from
base_projection     = projection at store_base_commit
incoming_projection = projection at new HEAD
local_overlay       = explicit overlay_events not yet committed

if no overlay:
    store := hydrate(incoming_projection)
else:
    backup current SQLite
    public := hydrate(incoming_projection)
    store := public + replay(local_overlay)
    re-project affected objects
    if replay invalid: stop with conflict report, keep backup
    store_base_commit := new HEAD
```

This is the mechanism that lets Dev B pull Dev A’s merged work without losing B’s private local work.

---

## 4. CI authority model

CI cannot compare against a gitignored developer SQLite store. The honest CI guarantee is:

```text
project(hydrate(committed projection)) == committed projection
```

plus schema, transition, trailer, field-writer, and code/convention validation.

Required CI checks:

| Check | Purpose |
|---|---|
| Projection canonicality | Prove projection is reproducible and deterministic. |
| Projection schema validation | Prove each YAML file conforms to schema. |
| Legal-transition validation | Reject canonical but illegal lifecycle jumps. |
| Trailer/diff cross-check | Prove git event log matches projection changes. |
| Field-writer validation | Prevent humans writing `external_refs` or extensions writing lifecycle fields. |
| No-secrets validation | Prevent raw tokens or credentials in projection/trailers. |
| Core no-provider test | Prove core works against a non-GitHub git remote. |

The legal-transition validator is the load-bearing gate. Canonical YAML alone is only well-formatted text; it is not correctness.

---

## 5. Commit trailers and event log contract

Git history is only a reliable event log if commit metadata is structured. Free prose is insufficient.

Canonical trailer group:

```text
ATDD-Object: wi_01J7Z...
ATDD-Transition: PLANNED->RED
ATDD-Token-Digest: sha256:<hex>
ATDD-Gate: E019
ATDD-Projection-Digest: sha256:<hex>
```

Rules:

1. A projection object diff must have an `ATDD-Object` trailer.
2. A phase diff must have an `ATDD-Transition` trailer.
3. A gated transition must have token digest and gate evidence trailers.
4. The projection digest trailer must match the generated projection digest.
5. Raw tokens, bearer tokens, secrets, or credentials are invalid.
6. Multiple object changes require either grouped trailers or an `ATDD-Summary` artifact.
7. Squash merges must preserve ATDD event semantics using trailers or an `ATDD-Summary` trailer.

Recommended squash summary:

```text
ATDD-Summary: .atdd/events/<merge_commit>.json
ATDD-Summary-Digest: sha256:<hex>
```

---

## 6. Lifecycle evidence model

The lifecycle policy must define the evidence required for each transition. The following is the first version to implement; names can be adjusted to match existing ATDD terms.

| Transition | Required evidence |
|---|---|
| `∅ -> INIT` | UID generated; slug/title/body initialized; projection digest. |
| `INIT -> PLANNED` | Plan/body complete; acceptance or WMBT references present. |
| `PLANNED -> RED` | Operator token digest; gate ID; failing test/WMBT evidence. |
| `RED -> GREEN` | Passing test evidence for the relevant WMBTs; implementation diff present. |
| `GREEN -> SMOKE` | Smoke evidence artifact or smoke gate result. |
| `SMOKE -> COMPLETE` | Derived from merge-to-main, or merge-queue injected before merge. |
| `* -> TOMBSTONED` | Reason digest; tombstone metadata; no physical file deletion. |

Recommendation: make `COMPLETE` derived from merge-to-main for the first implementation. Stored `COMPLETE` can be added later if there is a hard reporting requirement.

---

## 7. Merge semantics

Projection sharding by UID makes disjoint objects merge cleanly. Same-object conflicts must be validity-gated, not resolved by “max phase wins.”

### 7.1 Field ownership

| Field | Writer | Rule |
|---|---|---|
| `uid` | Core create | Immutable; never rewritten. |
| `slug` | Core authoring | Mutable display metadata. |
| `phase` | Core lifecycle | Monotonic and gate-validated. |
| `body` | Core authoring | Conflict unless single-owner rule proves safe. |
| `train` | Core train ops | Conflict unless same digest. |
| `wmbts` | Core test ops | Test-owned; policy-defined merge. |
| `extension_digests` | Core writes; provider supplies | Derived from lock/provider digest. |
| `external_refs.*` | Extension bot only | Non-authoritative; lifecycle code may not read it. |
| `state: TOMBSTONED` | Core | Retirement record; prevents resurrection. |

### 7.2 Phase merge

Auto-merge same-object phase divergence only when one of these is true:

1. the transitions are identical;
2. one side is a strict no-op relative to the other;
3. the further phase carries verifiable evidence for every skipped gate.

Otherwise, conflict and require explicit resolution. Never use blind max phase.

---

## 8. GitHub extension boundary

Core owns truth, lifecycle, projection, reconciliation, merge authority, and validation. The GitHub extension owns presentation only.

### 8.1 Boundary law

> Provider code imports core. Core never imports provider code.

Core must run a complete workflow with zero providers registered. If a module needs GitHub API, `gh`, issue labels, or issue numbers to make a lifecycle decision, it is not core.

### 8.2 SyncProvider seam

Core defines the interface:

```python
class SyncProvider(Protocol):
    name: str

    def mirror(self, objects: list[ObjectSnapshot]) -> list[ExternalRefUpdate]: ...

    def detect_drift(self, objects: list[ObjectSnapshot]) -> list[DriftAlarm]: ...

    def digest(self) -> ExtensionDigest: ...
```

Hard properties:

1. `mirror()` may return only bot-namespaced `ExternalRefUpdate` records.
2. `detect_drift()` is alarm-only and must not return authoritative state.
3. Extension never edits projection directly.
4. Core applies provider metadata only through a constrained `external_refs.*` update path.
5. Lifecycle code must not read `external_refs`.

---

## 9. Hooks and developer workflow

Local hooks improve feedback but do not enforce correctness. Every hook-backed check must have a CI equivalent.

| Trigger | Where | Job |
|---|---|---|
| `pre-commit` | Client | Optional quick drift check. |
| `pre-push` | Client | `project(store) == committed projection`; fast validation. |
| `pre-rebase` | Client | Dirty-store protection. |
| `post-merge` | Client | Reconcile after merge-based pull. |
| `post-checkout` | Client | Reconcile after branch or HEAD changes. |
| `post-rewrite` | Client | Reconcile after rebase/amend. |
| Push CI | Server | Validate projection and code. |
| PR CI | Server | Merge authority. |
| Main CI | Server | Revalidate after merge. |
| Mirror sync job | Server/bot | Push projection state to GitHub mirror after merge. |

Invariant: any operation that moves HEAD must reconcile local store state.

---

## 10. Data model rules

1. UID is immutable, globally unique, and never reused.
2. Slug/title are display metadata only.
3. Deletion creates a tombstone, not file deletion.
4. Physical removal is a separate archival/compaction operation.
5. `.atdd/extensions.lock` must lock core schema, lifecycle policy, merge policy, and provider digests.
6. Projection/trailers must never contain raw secrets.

Recommended lock file scope:

```yaml
schema_version: 1
core:
  atdd_version: <version>
  projection_schema_digest: sha256:<hex>
  lifecycle_policy_digest: sha256:<hex>
  merge_policy_digest: sha256:<hex>
providers:
  github:
    version: <version>
    digest: sha256:<hex>
```

---

## 11. End-to-end collaboration flow

1. Main contains projection files for shared objects.
2. Dev A and Dev B hydrate local stores from main projection.
3. Dev A authors `feature-x` in local store, projects it, commits with trailers, and pushes.
4. Push CI validates canonicality, schema, legal transition, trailers, field writers, and code.
5. Dev A opens PR. PR CI is the merge authority.
6. Dev B concurrently authors `feature-y` in a separate projection file.
7. Dev A merges first. Main CI validates. GitHub mirror may update after merge but does not affect truth.
8. Dev B pulls/rebases. Git merges disjoint projection files.
9. HEAD-change hook runs `atdd state reconcile`.
10. B’s store becomes `hydrate(new HEAD projection) + replay(B overlay)`.
11. B sees A’s state through Git/projection, without reading GitHub.

Same-object conflicts use the merge driver and legal evidence. Unsafe merges conflict by design.

---

## 12. Non-goals

1. Do not commit SQLite store.
2. Do not use GitHub Issues as a source of lifecycle truth.
3. Do not sync GitHub comments, reactions, assignment, or social layer.
4. Do not trust local hooks as enforcement.
5. Do not claim CI validates against a hidden store.
6. Do not let provider failure block core merge authority.

---

# Delivery plan for maximum efficiency

## 13. Planning principle

Max delivery efficiency means building the smallest vertical slice that proves the new collaboration model before implementing the full mirror, merge-driver, and migration surface.

The critical path is:

```text
projection schema → project/hydrate → store_base_commit + overlay → reconcile → canonical CI → legal-transition CI → trailer/diff cross-check → field-writer rules → provider seam → GitHub mirror
```

Build core first. The GitHub extension should not begin deep mirror behavior until the core `ExternalRefUpdate` contract and projection schema are stable.

---

## 14. Milestones

### M0 — Architecture lock and decision closure

**Goal:** Remove open semantic ambiguity before coding dependencies spread.

| Issue | Repo | Priority | Output |
|---|---|---:|---|
| Decide COMPLETE semantics | Core + Extension | P0 | Use derived COMPLETE for v1 unless explicitly overruled. |
| Define projection schema v1 | Core | P0 | Stable per-UID YAML schema. |
| Define lifecycle evidence policy v1 | Core | P0 | Required evidence per transition. |
| Define provider metadata write-back protocol | Core + Extension | P0 | `ExternalRefUpdate` contract. |
| Define merge/squash policy | Core | P0 | Allowed merge methods and ATDD summary format. |

**Exit criteria:** schema, lifecycle policy, external ref protocol, and merge policy are accepted.

---

### M1 — Projection spine

**Goal:** Make committed projection real, deterministic, and CI-readable.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Implement deterministic `project(store)` | Core | P0 | Schema v1 |
| Implement `hydrate(projection)` | Core | P0 | Schema v1 |
| Add projection digest | Core | P0 | `project()` |
| Add canonical CI: `project(hydrate(projection)) == projection` | Core | P0 | `project()`, `hydrate()` |
| Add UID generation and slug rename semantics | Core | P0 | Schema v1 |

**Exit criteria:** CI can validate projection without GitHub or developer SQLite.

---

### M2 — Reconcile spine

**Goal:** Solve the Dev A / Dev B local-store update problem.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Add `store_base_commit` metadata | Core | P0 | Hydrate |
| Implement explicit overlay event log | Core | P0 | Store schema update |
| Implement dirty-store gate | Core | P0 | Overlay log |
| Implement `atdd state reconcile` | Core | P0 | `store_base_commit`, overlay log, hydrate |
| Add HEAD-change hooks | Core | P1 | Reconcile |
| Build A/B collaboration test | Core | P0 | Reconcile, projection spine |

**Exit criteria:** Dev B can pull/rebase after Dev A merges and keep local private work intact.

---

### M3 — Merge authority

**Goal:** Make CI the real lifecycle authority, not just a formatting check.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Implement legal-transition validator | Core | P0 | Lifecycle policy, projection diffing |
| Implement trailer parser/schema | Core | P0 | Trailer contract |
| Implement trailer/projection diff cross-check | Core | P0 | Validator, parser |
| Add no-secrets-in-history validator | Core | P0 | Trailer parser |
| Add PR/push CI workflow | Core | P0 | Validators |
| Configure branch protection docs | Core | P1 | CI workflow |

**Exit criteria:** canonical but illegal projection changes are rejected in CI.

---

### M4 — Field ownership and safe conflicts

**Goal:** Prevent same-object and wrong-writer corruption.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Define field ownership policy file | Core | P0 | Schema v1 |
| Implement field-writer validator | Core | P0 | Field policy, trailer parser |
| Implement projection merge driver | Core | P1 | Field policy, legal-transition validator |
| Add merge-driver test matrix | Core | P1 | Merge driver |
| Implement tombstone lifecycle | Core | P1 | Schema v1, field policy |

**Exit criteria:** disjoint objects merge cleanly; unsafe same-object conflicts block with useful reports.

---

### M5 — Core/provider boundary

**Goal:** Prove core is provider-free and prepare extension integration.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Add `SyncProvider` interface in core | Core | P0 | ExternalRefUpdate contract |
| Add provider registration/discovery | Core | P0 | SyncProvider |
| Add import-boundary static test | Core | P0 | Provider seam |
| Add non-GitHub remote conformance suite | Core | P0 | Projection + reconcile + CI validators |
| Implement `.atdd/extensions.lock` | Core | P0 | Provider digest contract |

**Exit criteria:** core full workflow passes with zero providers and a bare git remote.

---

### M6 — GitHub extension MVP

**Goal:** Add human mirror without touching lifecycle authority.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Implement GitHub `SyncProvider` registration | Extension | P0 | Core seam |
| Implement provider digest | Extension | P0 | `extensions.lock` |
| Implement issue rendering contract | Extension | P1 | Projection schema |
| Implement mirror create/update/close | Extension | P0 | Rendering contract |
| Return issue number as `ExternalRefUpdate` only | Extension | P0 | ExternalRefUpdate protocol |
| Implement mirror job workflow | Extension | P1 | Mirror MVP |

**Exit criteria:** after merge, GitHub Issues reflect projection state; provider failure does not block merge.

---

### M7 — Drift alarm and hardening

**Goal:** Detect mirror drift while keeping GitHub off the hot path.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Implement `detect_drift` | Extension | P1 | Mirror MVP |
| Add drift alarm reporting | Extension | P1 | `detect_drift` |
| Add GitHub rate-limit/backoff handling | Extension | P2 | Mirror MVP |
| Implement GitHub issue lookup by UID | Extension | P1 | Rendering contract |
| Implement bot identity enforcement | Core + Extension | P1 | ExternalRefUpdate protocol |

**Exit criteria:** manual GitHub edits are detected and reported, never synced back into lifecycle state.

---

### M8 — Migration and decommission

**Goal:** Move from manifest/GitHub hot path to projection authority safely.

| Issue | Repo | Priority | Dependencies |
|---|---|---:|---|
| Implement manifest-to-projection migration tool | Core | P0 | Projection schema, hydrate/project |
| Add shadow-mode projection CI | Core | P1 | Migration tool, canonical CI |
| Remove GitHub hot-path reads | Core + Extension | P0 | Core CI authority, mirror MVP |
| Decommission manifest read-fallback | Core | P1 | Projection blocking mode |
| Write migration rollout docs | Core + Extension | P1 | Migration sequence |

**Exit criteria:** projection becomes the shared state; GitHub is optional mirror; legacy manifest no longer acts as fallback SoT.

---

## 15. Recommended issue backlog

### Core repo

| ID | Issue | Priority | Milestone |
|---|---|---:|---|
| CORE-001 | Decide COMPLETE semantics | P0 | M0 |
| CORE-002 | Define projection schema v1 | P0 | M0 |
| CORE-003 | Define lifecycle evidence policy v1 | P0 | M0 |
| CORE-004 | Define merge/squash event policy | P0 | M0 |
| CORE-005 | Implement deterministic `project(store)` | P0 | M1 |
| CORE-006 | Implement `hydrate(projection)` | P0 | M1 |
| CORE-007 | Add projection digest and golden-file tests | P0 | M1 |
| CORE-008 | Add canonical projection CI | P0 | M1 |
| CORE-009 | Implement UID generation and slug rename semantics | P0 | M1 |
| CORE-010 | Add `store_base_commit` metadata | P0 | M2 |
| CORE-011 | Implement explicit overlay event log | P0 | M2 |
| CORE-012 | Implement dirty-store gate | P0 | M2 |
| CORE-013 | Implement `atdd state reconcile` | P0 | M2 |
| CORE-014 | Add HEAD-change reconcile hooks | P1 | M2 |
| CORE-015 | Build A/B collaboration test | P0 | M2 |
| CORE-016 | Implement legal-transition validator | P0 | M3 |
| CORE-017 | Implement ATDD trailer parser/schema | P0 | M3 |
| CORE-018 | Implement trailer/projection diff cross-check | P0 | M3 |
| CORE-019 | Add no-secrets-in-history validator | P0 | M3 |
| CORE-020 | Add push/PR CI merge authority workflow | P0 | M3 |
| CORE-021 | Define field ownership policy | P0 | M4 |
| CORE-022 | Implement field-writer validator | P0 | M4 |
| CORE-023 | Implement projection merge driver | P1 | M4 |
| CORE-024 | Add merge-driver test matrix | P1 | M4 |
| CORE-025 | Implement tombstone lifecycle | P1 | M4 |
| CORE-026 | Add `SyncProvider` interface | P0 | M5 |
| CORE-027 | Add provider registration/discovery | P0 | M5 |
| CORE-028 | Add import-boundary static test | P0 | M5 |
| CORE-029 | Add non-GitHub remote conformance suite | P0 | M5 |
| CORE-030 | Implement `.atdd/extensions.lock` | P0 | M5 |
| CORE-031 | Implement manifest-to-projection migration tool | P0 | M8 |
| CORE-032 | Add shadow-mode projection CI | P1 | M8 |
| CORE-033 | Remove GitHub hot-path reads | P0 | M8 |
| CORE-034 | Decommission manifest read-fallback | P1 | M8 |
| CORE-035 | Write core migration/developer docs | P1 | M8 |

### GitHub extension repo

| ID | Issue | Priority | Milestone |
|---|---|---:|---|
| EXT-001 | Implement GitHub `SyncProvider` registration | P0 | M6 |
| EXT-002 | Implement provider digest | P0 | M6 |
| EXT-003 | Define GitHub issue rendering contract | P1 | M6 |
| EXT-004 | Implement mirror create/update/close | P0 | M6 |
| EXT-005 | Return issue number as `ExternalRefUpdate` only | P0 | M6 |
| EXT-006 | Implement mirror job workflow | P1 | M6 |
| EXT-007 | Implement `detect_drift` | P1 | M7 |
| EXT-008 | Add drift alarm reporting | P1 | M7 |
| EXT-009 | Add GitHub rate-limit/backoff handling | P2 | M7 |
| EXT-010 | Implement GitHub issue lookup by UID | P1 | M7 |
| EXT-011 | Implement bot identity enforcement integration | P1 | M7 |
| EXT-012 | Write extension operator docs | P1 | M8 |

### Cross-repo coordination

| ID | Issue | Priority | Milestone |
|---|---|---:|---|
| X-001 | Freeze projection schema and provider metadata protocol | P0 | M0 |
| X-002 | Freeze COMPLETE semantics | P0 | M0 |
| X-003 | Freeze merge/squash policy | P0 | M0 |
| X-004 | Define branch protection and required checks | P1 | M3 |
| X-005 | Build end-to-end core + extension smoke test | P0 | M6 |
| X-006 | Create migration rollout and rollback plan | P0 | M8 |

---

## 16. Dependency-optimized execution order

### First 10 issues to open

1. CORE-002 — Define projection schema v1
2. CORE-003 — Define lifecycle evidence policy v1
3. CORE-001 — Decide COMPLETE semantics
4. X-001 — Freeze projection schema and provider metadata protocol
5. CORE-005 — Implement deterministic `project(store)`
6. CORE-006 — Implement `hydrate(projection)`
7. CORE-010 — Add `store_base_commit` metadata
8. CORE-011 — Implement explicit overlay event log
9. CORE-013 — Implement `atdd state reconcile`
10. CORE-015 — Build A/B collaboration test

This sequence maximizes learning and de-risks the core model before extension work expands the surface area.

### Parallelization lanes

| Lane | Owner | Can start after | Work |
|---|---|---|---|
| Projection lane | Core | M0 schema | `project`, `hydrate`, digest, canonical CI. |
| Reconcile lane | Core | Hydrate + store metadata | overlay log, dirty gate, reconcile, hooks. |
| Authority lane | Core | lifecycle policy | legal-transition validator, trailers, CI. |
| Merge safety lane | Core | schema + lifecycle policy | field ownership, writer validator, merge driver. |
| Provider seam lane | Core + Extension | ExternalRefUpdate protocol | `SyncProvider`, import checks, provider digest. |
| Mirror lane | Extension | provider seam + projection schema | GitHub rendering, mirror, drift alarm. |
| Migration lane | Core | projection spine stable | migration tool, shadow CI, manifest decommission. |

### What not to build first

Do not start with the GitHub mirror, drift alarm, or merge driver before the projection and reconcile spine exist. Those pieces depend on the shared state model and will churn if built too early.

Do not implement stored `COMPLETE` through a post-merge bot push in v1. It creates branch-protection and race semantics before the core flow is stable.

---

## 17. MVP definition

The smallest valuable deliverable is not the GitHub mirror. The MVP is:

```text
Core can author, project, commit, push, pull/rebase, reconcile, and validate lifecycle state through Git only, with no GitHub API and no committed SQLite store.
```

MVP acceptance:

1. Projection is deterministic.
2. CI validates `project(hydrate(projection)) == projection`.
3. Dev A / Dev B collaboration works through Git projection.
4. Dirty local overlay survives pull/rebase.
5. Illegal lifecycle jumps fail CI.
6. GitHub is not read in the hot path.
7. Core suite passes with a bare git remote.

Only after this should the GitHub mirror be promoted beyond a thin optional provider.

---

## 18. Final decision summary

1. Use **derived COMPLETE** for v1 unless a strong requirement forces stored COMPLETE.
2. Implement **explicit overlay events** rather than relying on DB diff inference.
3. Treat **projection as shared source of truth** and local store as private authoring workspace.
4. Make **CI legal-transition validation** the authority, not canonical formatting alone.
5. Keep **GitHub out of core** and quarantine provider write-back to bot-namespaced `external_refs`.
6. Build in this order: projection spine, reconcile spine, CI authority, merge safety, provider seam, mirror, migration.
