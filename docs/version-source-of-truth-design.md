# State Store Owns the Release Version — Design & Decomposition (#1172)

**Status:** design + core implementation (planning issue #1172; core shipped in PR #1269)
**Depends on:** #1168 (State Store), #1203 (authoritative lifecycle, Phase 1+2 merged)
**Relates to:** #945, #1169, #1170/#1173 (interim manual-bump revert), #1051, #1171 (local-first identity)
**Scope:** dependent of / extension to #1168 — folds in or sequences after that lane.

This document is grounded in the **shipped** `src/atdd/state/` APIs (store.py / db.py /
migrations.py / paths.py / projections.py / cli.py), not hypothetical ones. Every signature
referenced below was verified against the merged code.

> **Implementation status (PR #1269 — this branch).** The provider-neutral core (§7 S1–S4) is
> **built and green**: migration v2 seeds the singleton `release` object at `3.149.0`
> (`RELEASE_SEED_VERSION`); `state/version.py` exposes `current`/`emit`/`next_from_change_class`/`bump`;
> `release_projection`/`ReleaseRow` are in `projections.py`; the `atdd state version show|emit|bump`
> CLI and the in-tree `build_meta_shim` projection (`dynamic = ["version"]`, `0.0.0+local` fallback)
> are wired. **`bump` itself emits the neutral `version_decided` outbox signal** (`{version,
> change_class}`) — there is no separate `publish`/`tag_and_publish` step in core, and core writes no
> git-tag `external_ref` (that writeback is the extension's inbox job). The outbox `provider` is a
> configured keyword arg (default `"github"`, mirroring `hub.promote_trace`). The remaining work (§7
> S5–S6) — the release-extension that drains `version_decided` to tag + publish, and the docs cutover
> — is the follow-up; the manual interim per #1173 stands until S5–S6 land.

---

## 1. Problem (the two concrete failures)

1. **Manual `pyproject.toml::version` bump → merge-conflict churn.** Every parallel PR edits the
   same `version = "X.Y.Z"` line (`pyproject.toml:7`), so concurrent PRs *always* conflict there.
   We burned 3.143→3.149 of rebase churn landing the substrate trilogy.
2. **The bump-on-merge automation is dead.** `post-merge-lifecycle.yml`'s "Bump version on main"
   step computes the next version, commits `chore(release): bump version to X [auto]`, and pushes
   directly to protected `main` → **GH006: protected branch hook declined** (a direct, un-CI'd push
   can't satisfy the required `validate-gate` check). `git log` shows **zero `[auto]` commits in
   main's history** — it has never once worked. The retry logic misdiagnoses GH006 as a
   fast-forward race and burns 3 attempts.

Today's version handling is therefore: a conflict-prone hand-edited file **plus** a
protection-blocked automation. Neither is correct.

---

## 2. Decision (LOCKED) — three layers

The release version has three facets; they belong in three different layers. This placement was
accepted by the State Store (#1168) session and is **not re-litigated here**; this doc specs it.

> **Core contract (universal) vs atdd-repo's release-extension wiring.** Read the table below
> through this split, or PyPI looks mandatory when it is not:
> - **Core contract (universal):** the store owns the *number*; core exposes `current` / `bump` /
>   `emit`; and on a bump core enqueues a **provider-neutral** outbox message `version_decided`
>   carrying `{version, change_class}`. **Core never names PyPI, never says "tag/publish", never
>   writes a git/github ref.** Any consumer, in any stack, gets exactly: "the store holds the
>   version and can emit it," plus a neutral signal that it changed.
> - **atdd-repo's release-extension wiring (one instance, not the contract):** *this* repo
>   configures its release extension to mirror the store version and, as its side-effect, create a
>   git tag + publish to **PyPI**. PyPI is *the atdd-toolkit repo's configured target* — another
>   repo's extension might publish to npm, push nowhere, or do something else. The git-tag
>   `external_ref` and the publish action live **entirely in the extension**, not in core.
> - The **build-time projection** is likewise per-ecosystem: the universal guarantee is "store holds
>   & can `emit` the version"; the `pyproject dynamic` + setuptools backend below is *this repo's*
>   Python/setuptools-specific projection. A consumer in another stack supplies its own (generated
>   file, language-native equivalent).

| Facet | Layer | Mechanism (real API) |
|-------|-------|----------------------|
| Version number + bump **decision** (current value, next-by-change-class, audit) | **State Store (core, universal)** — `objects` + `events` | `ObjectStore.upsert(uid="release", kind=KIND_RELEASE, data={"version": …})`; `EventStore.append("version_bumped", object_uid="release", payload={from,to,change_class,pr})` |
| **Decision signal** to whatever publishes (provider-neutral) | **State Store (core, universal)** — `outbox` | `SyncStore.enqueue_outbox(<configured-provider>, "version_decided", {"version": …, "change_class": …})` — **operation + payload are neutral; core does not name PyPI/tag/publish** |
| Version at **build / package time** | **deterministic projection (per-ecosystem)** | *this repo:* `pyproject` `dynamic = ["version"]` + an in-tree build backend reading the store **local-first** with a **`0.0.0+local` fallback**; runtime reads via `importlib.metadata.version("atdd")`. Other stacks supply their own projection over the same `emit`. |
| **Publication** (git tag + PyPI) | **atdd-repo's GitHub/release EXTENSION** (one configured instance) | extension drains the `version_decided` outbox → creates tag + publishes to PyPI → writes the tag back via `ExternalRefStore.link("release","github","tag","vX.Y.Z")` (inbox). **None of this is in core.** |

### 2.1 Build-time projection (the hard part) — `dynamic` build hook, local-first

> **Scope:** this section is *this repo's* Python/setuptools projection — one instance of the
> universal "store can `emit` the version" guarantee, not the core contract. Another ecosystem
> swaps this mechanism for its own.

**Chosen:** make `pyproject` `dynamic = ["version"]` and supply an **in-tree PEP 517 build backend**
that wraps `setuptools.build_meta` and injects the version it resolves from the store.

Resolution order inside the hook (deterministic, no network, no runtime SQLite at *runtime* — only
at *build*):

1. **Explicit override** — `ATDD_VERSION` env var, if set and PEP 440-valid. (Lets CI/release pin a
   version without a store; also the escape hatch for reproducible source builds.)
2. **Store read** — resolve the control root via `state.paths.resolve_control_root(cwd)` →
   `resolution.control_root / STATE_STORE_RELATIVE` (`.atdd/state/state.sqlite`). If the file
   exists (`resolution.state_store_exists`), `connect()` it **read-only**, read the `release`
   object's `data["version"]` via `ObjectStore.get("release")`, return it. Close the connection.
3. **Fallback — `0.0.0+local`** — when no store exists (fresh `git clone` + `pip install -e .`
   before `atdd state init`, or a pure-local user who never cut a release). This is the **one
   genuinely novel piece** and must be explicit: the build must **succeed**, producing a PEP
   440-valid local version (`0.0.0+local`), never raise. A consumer who needs the real version runs
   `atdd state init` (or sets `ATDD_VERSION`) first.

The hook must be **import-light and dependency-free** beyond `atdd.state` + stdlib, because it runs
inside the isolated build environment. It imports `atdd.state.paths` / `atdd.state.db` /
`atdd.state.store` only — these are already stdlib-only (`sqlite3`, `pathlib`, `json`).

**Why not the alternatives** (kept for the record):
- *Committed/generated `src/atdd/_version.py`* — reintroduces a build artifact in the tree, which is
  itself a merge-conflict surface and a thing to keep in sync. The whole point is to delete the
  conflict surface, not relocate it.
- *setuptools-scm / git-tag-derived* — **git- and GitHub-coupled**: requires a tagged git history,
  which a pure-local ATDD user (GitHub-as-extension model) does not have. It also re-entangles
  publication with versioning. Explicitly rejected by the issue.

### 2.2 The win

Moving the number into the store **dissolves both failures at once**:
- There is no `version =` line in `pyproject.toml` for parallel PRs to conflict on (it becomes
  `dynamic`).
- Nothing pushes a bump commit to protected `main` → **no direct push → no GH006**. The bump is a
  store write on the PR branch (or a post-merge outbox drain), never a protected-branch push.

---

## 3. How version maps onto the shipped store model

No schema change is strictly required — `objects.kind` is free-text (migrations.py:27 comment lists
`work_item | run | evidence | hub_session | ...`). But for parity with the existing `KIND_*`
discipline and to give the migration a recorded provenance row, we add **migration v2** that is a
**no-op DDL marker** registering the `release` kind by convention (and an index if useful). Current
`latest_version() == 1` (single `core_tables` migration). Migrations are append-only; v2 is the next
number.

| Concern | Real API call |
|---------|---------------|
| Current value (authoritative) | `store.objects.upsert("release", KIND_RELEASE, data={"version": "3.150.0"})` |
| Read current | `store.objects.get("release")` → `Object.data["version"]` |
| Bump audit log | `store.events.append("version_bumped", object_uid="release", payload={"from": "3.149.0", "to": "3.150.0", "change_class": "minor", "pr": 1281})` |
| Read view (projection) | new `release_projection(conn) -> List[ReleaseRow]` in `projections.py`, mirroring `work_item_projection` (instantiate stores on a raw `sqlite3.Connection`, bulk-read, return frozen rows) |
| Decision signal (core, **neutral**) | `store.sync.enqueue_outbox(<configured-provider>, "version_decided", {"version":"3.150.0","change_class":"minor"})` — core stops here |
| Publication side-effect (**extension only**, not core) | extension drains `version_decided` → tag + PyPI → writes back `store.external_refs.link("release","github","tag","v3.150.0")` via inbox. **Core never makes these calls.** |

> ⚠️ **API gotcha for implementers:** `SyncStore.enqueue_outbox(provider, operation, payload)` takes
> `payload` **positionally/required** (store.py:271) — unlike `ObjectStore.upsert`/`EventStore.append`
> where `data`/`payload` are keyword-only. Don't call it with `payload=`.

### 3.1 Change-class semantics (unchanged — out of scope to alter)

Carried verbatim from the dead `post-merge-lifecycle.yml` bump step, now computed in core:

- `feat/` branch prefix → **MINOR**
- `fix/ | chore/ | docs/ | refactor/ | devops/` (and any other prefix) → **PATCH**
- PR title contains `BREAKING CHANGE` or matches `^<type>(scope)?!:` → **MAJOR**

`next_from_change_class(current, change_class)` is pure semver arithmetic. The change-class is an
**input** to core; the branch-prefix→class mapping is a thin policy layer the CLI/extension supplies.

---

## 4. New / changed code surface (API-grounded)

### 4.1 `src/atdd/state/version.py` (new)
Pure-ish module; all I/O via the passed `StateStore`.
```python
RELEASE_UID = "release"           # the single release object's uid
KIND_RELEASE = "release"          # objects.kind value
DEFAULT_LOCAL_VERSION = "0.0.0+local"

def current(store: StateStore) -> Optional[str]: ...
    # store.objects.get(RELEASE_UID) -> data["version"], else None

def next_from_change_class(current_version: str, change_class: str) -> str: ...
    # pure semver: major|minor|patch

def bump(store: StateStore, change_class: str, *, pr: Optional[int] = None,
         branch: Optional[str] = None) -> str: ...
    # cur = current(store) or "0.0.0"
    # nv  = next_from_change_class(cur, change_class)
    # store.objects.upsert(RELEASE_UID, KIND_RELEASE, data={"version": nv})
    # store.events.append("version_bumped", object_uid=RELEASE_UID,
    #                     payload={"from": cur, "to": nv, "change_class": change_class, "pr": pr})
    # # neutral decision signal — core stops here; never names PyPI/tag/publish:
    # store.sync.enqueue_outbox(provider, "version_decided", {"version": nv, "change_class": change_class})
    # return nv     # provider is config-supplied; default may be None/"local" for a pure-local user

def set_version(store: StateStore, version: str) -> None: ...   # explicit set (migration/import)
def change_class_for_branch(branch: str, pr_title: str = "") -> str: ...  # policy: prefix -> class
```

### 4.2 `release_projection` in `src/atdd/state/projections.py` (new)
```python
KIND_RELEASE = "release"

@dataclass(frozen=True)
class ReleaseRow:
    uid: str
    version: Optional[str]
    external: Dict[str, str] = field(default_factory=dict)   # provider -> ref_value (e.g. github tag)
    last_bumped_to: Optional[str] = None                     # from latest version_bumped event

def release_projection(conn: sqlite3.Connection) -> List[ReleaseRow]: ...
    # mirror work_item_projection: ObjectStore + ExternalRefStore + EventStore on raw conn
```
Add `ReleaseRow`, `release_projection`, `version` module exports to `state/__init__.py::__all__`.

### 4.3 Migration v2 in `src/atdd/state/migrations.py`
Append `Migration(version=2, name="release_kind", sql=_RELEASE_MARKER_SQL)`. SQL is a provenance
no-op (e.g. a comment + optional `CREATE INDEX IF NOT EXISTS idx_objects_kind ON objects(kind)` if
not already present) — **no destructive change**, append-only per the migrations.py rule.

### 4.4 `atdd state version` CLI (`src/atdd/state/cli.py`)
Add a `version` subparser (mirror the nested-subparser `trace` pattern, cli.py:57) with actions:
- `show` — print `current(store)` (or `0.0.0+local` if none).
- `bump --class {major|minor|patch}` (or `--branch <ref> [--title <t>]` to derive the class) — calls
  `version.bump(...)`, prints the new version.
- `emit` — print exactly the version string the build hook would resolve (store → fallback). Used by
  CI/tooling that wants the resolved value without driving a build.

Wire via `_open_store(root)` (cli.py:190) → `StateStore(conn)` and `conn.close()` in `finally`
(same shape as `_cmd_trace`). Register the dispatch branch in `run()` (cli.py:253).

### 4.5 Build backend — `build_backend/atdd_version_backend.py` (new, in-tree)
A thin PEP 517 backend:
```python
from setuptools import build_meta as _orig
# re-export all required hooks (build_wheel, build_sdist, get_requires_for_*, prepare_metadata_*)
def _resolve_version() -> str:
    # 1. os.environ.get("ATDD_VERSION") if PEP440-valid
    # 2. read store local-first via atdd.state (read-only); ObjectStore.get("release")
    # 3. DEFAULT_LOCAL_VERSION = "0.0.0+local"
# inject into the dist by setting the dynamic version (via a setuptools dynamic provider, see below)
```
`pyproject.toml` changes:
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "atdd_version_backend"
backend-path = ["build_backend"]

[project]
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "..."}   # or resolved by the backend's prepare_metadata hook
```
> The cleanest setuptools-native expression is a small `setup.py`-free **dynamic version via a
> backend wrapper** that sets `version` during `prepare_metadata_for_build_wheel`. The RED/GREEN
> sub-issue pins the exact hook; the contract is: `python -m build` and `pip install -e .` both
> succeed with no store (→ `0.0.0+local`) and with a store (→ stored value), with no network and no
> runtime sqlite import.

---

## 5. atdd-repo's release-extension wiring (one configured instance — NOT the core contract)

Everything here is *this repo's* configured side-effect set (tag + PyPI). Core's job ended at the
neutral `version_decided` outbox message (§2, §3). Another repo would wire its extension differently
or not at all.

- **`publish.yml`** currently reads the version from `config.release.version_file` (→ pyproject) via
  a regex. Rewire it to read the resolved version from the package metadata of the just-built dist
  (or `atdd state version emit`), and tag `${tag_prefix}${version}`. PyPI Trusted Publishing and the
  `workflow_run`-after-Validate trigger are **this repo's** publication choices, not the contract.
- **`post-merge-lifecycle.yml`** — delete the entire "Bump version on main" cluster (the GH006
  source: "Detect legacy version-bump", "Verify PROJECT_TOKEN", "Checkout main for bump-on-merge",
  "Bump version on main"). Replace the bump with: on merge, the **store write + neutral
  `version_decided` outbox message** already done on the branch is what carries forward; *this
  repo's* release extension drains it to tag + publish to PyPI, then records the tag back as an
  `external_ref`. The label-swap / sub-issue-close steps of this workflow are unrelated and stay.
- **`config.yaml`** — `release.version_file` becomes vestigial; either drop it or repoint tooling to
  `atdd state version emit`. `tag_prefix: v` stays (consumed by *this repo's* extension at
  publication, not by core).

**Core stays provider-agnostic:** it writes only the `release` object, the `version_bumped` event,
and the **neutral `version_decided`** outbox message. The git tag `external_ref`, the PyPI publish,
and any `"github"`-specific naming live **in the extension** — core never names them.

---

## 6. Migration & cutover

1. **Seed the store** from today's `pyproject.toml::version` (`3.149.0`) via
   `version.set_version(store, "3.149.0")` (one-shot, idempotent — part of the migration/CLI sub-issue).
2. **Flip `pyproject` to `dynamic`** + land the build backend (with fallback). At this point local
   builds resolve from the store; conflict surface gone.
3. **Rewire publish + retire the dead bump** (Section 5).
4. **Docs cutover — LAST.** Undo the #1173 interim ("bump manually"); flip the managed CLAUDE.md /
   release-convention text back to "automated, store-sourced." **Only after** end-to-end (local
   build → store bump → publish drain) is proven. Do **not** re-enable the old GH006 auto-bump.

Until all of the above ships, the **manual `pyproject` bump remains the working interim** (per
#1173). This is the documented, intended state during rollout.

---

## 7. Decomposition (sub-issues)

`atdd plan` flow is heavy for a fresh PLANNED lane (acceptances can't pass binding/measurability
gates without RED tests), so this section is the **authoritative sub-issue list**. Each is a normal
ATDD work item bound to convention nodes (not legacy `*.convention.yaml`), under the
`author-substrate` wagon as a dependent of #1168.

| # | Sub-issue | Archetype | Deps | Acceptance (WMBT sketch) |
|---|-----------|-----------|------|--------------------------|
| **S1** | **(core, universal)** Migration v2 (`release` kind) + `state/version.py` (`current`/`next_from_change_class`/`bump`/`set_version`/`change_class_for_branch`); `bump` enqueues neutral `version_decided` outbox msg | coder | — | `bump()` writes `release` object + `version_bumped` event + neutral `version_decided` outbox (no PyPI/tag naming); `next_from_change_class` covers major/minor/patch; semver arithmetic table-tested |
| **S2** | **(core, universal)** `release_projection` + `ReleaseRow` + `__all__` exports | coder | S1 | projection returns stored version + last bump event (+ any extension-written external ref); mirrors `work_item_projection` shape |
| **S3** | **(core, universal)** `atdd state version` CLI (`show`/`bump`/`emit`) | coder | S1,S2 | `emit` prints store value when present, `0.0.0+local` when absent; `bump --class` mutates store; exit codes match existing `_open_store` pattern |
| **S4** | **(this-repo projection, Python/setuptools)** Build backend: `pyproject dynamic=["version"]` + in-tree backend + **no-store fallback** (the hard one) | coder | S1 | `python -m build` **and** `pip install -e .` succeed with no store (→`0.0.0+local`) and with a store (→stored value); no network; no runtime sqlite import; `ATDD_VERSION` override honored |
| **S5** | **(this-repo extension wiring)** `publish.yml` reads resolved version (not pyproject regex); **retire** `post-merge-lifecycle.yml` bump cluster; *this repo's* release extension drains the neutral `version_decided` outbox → tag + PyPI → writes tag `external_ref` back | coach/devops | S3,S4 | tag derives from store-resolved version; no direct push to `main`; GH006 path deleted; extension (not core) does the publish; core emits only the neutral signal |
| **S6** | Docs cutover: undo #1173 interim, flip release text to "automated/store-sourced", drop/retarget `config.release.version_file` | coach | S5 | managed docs no longer instruct manual bump; happens **only after** S1–S5 green |

**Sequencing:** S1 → (S2, S4 parallel) → S3 → S5 → S6. S4 is the critical-path risk (build-hook +
fallback); prototype it early against a throwaway store.

**Out of scope** (carried from the issue): implementing the store itself (#1168); multi-user/remote
version coordination; changing change-class semantics.

---

## 8. Open questions resolved

1. *Projection mechanism?* → **dynamic build hook reading the store, local-first** (§2.1). Not a
   committed `_version.py`.
2. *Local-only user, when does the version bump?* → core `bump()` is callable any time, but the
   **decision** is cut at release time (`atdd state version bump`), not on every local event. A
   pure-local user who never releases simply stays at `0.0.0+local` until they bump.
3. *Does the bump decision move entirely into core?* → **Yes.** Core decides (store write); the
   GitHub extension only **publishes** (outbox drain). This is the provider-neutral/provider-specific
   split the whole design rests on.
4. *Cutover timing?* → manual `pyproject` bump stays the interim until S1–S5 are green; docs flip
   (S6) is the last step. Never re-enable the GH006 auto-bump.
