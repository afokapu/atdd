# ext#40 Phase 2 — core provider-registration seam (issue #1364)

**Deliverable A** of atdd-extensions#40 Phase 2 (store↔GitHub sync, provider-agnostic).
This is the CORE half: the contract the GitHub extension (Deliverable B) plugs into.
Core must stay **provider-agnostic — it must never import GitHub.**

## Problem

`src/atdd/integrations/github/state_sync.py::run_sync_cli` hardcodes
`providers = {PROVIDER_NAME: GitHubSyncProvider()}`, and `GitHubSyncProvider` lives
in core. `cli.py` routes `atdd state sync` straight into that GitHub module. There is
**no provider-registration seam** — so core is coupled to GitHub, and swapping in
GitLab/Jira/cmux would mean editing core. `sync_engine.py` already documents the
intended agnostic contract (`push_outbox(store, providers)` takes an arbitrary
`Mapping[str, SyncProvider]`); only the *construction* of that mapping is hardcoded.

## Design decisions

1. **Registry, not entry-points, as the PRIMARY mechanism.** atdd extensions are
   directory-based declarative packages (discovered by `rglob("atdd.implementation.yaml")`),
   **not** pip distributions, and register **no** Python entry points — so
   `importlib.metadata.entry_points()` discovers nothing from them. A lightweight
   in-process `register_provider(name, factory)` registry is therefore the honest
   primary seam. Entry-point discovery (group `atdd.state.sync_providers`) is kept as a
   **secondary** path so a genuinely pip-installed provider package can self-register
   with zero core edits (mirrors the `pytest11` precedent). `discover_providers()`
   merges both.

2. **Agnostic ingest hook lives in core (the contract).** The `SyncProvider` Protocol
   gains an optional `ingest(store) -> None`; `atdd state sync` gains `--ingest`, which
   calls `provider.ingest(store)` on each registered provider (that implements it) to
   fill the inbox, then always runs `apply_inbox`. Core only ever calls a protocol
   method — it never knows what GitHub is. The GitHub-specific `ingest` body is
   Deliverable B. (The brief buckets `--ingest` under B, but provider-agnosticism
   requires the *agnostic flag* to live in the core-contract PR; only the
   provider-specific implementation belongs in the extension.)

3. **Relocate `GitHubSyncProvider` out of core.** The only references to the core
   `state_sync.py` are `cli.py`'s route and the module's own test. So this PR **deletes**
   `src/atdd/integrations/github/state_sync.py` and its test, moves the sync CLI handler
   into `atdd/state/` (agnostic, no GitHub import), and reroutes `cli.py`. The provider
   itself is re-created in the extension (Deliverable B). Between A merging and B landing,
   `atdd state sync --push` simply has zero providers → pure-local, which is a supported
   state.

## Acceptance (RED → GREEN)

- A fake provider registered via `register_provider` drains an outbox item through
  `atdd state sync --push`.
- A fake provider's `ingest()` fills the inbox; `--ingest` + `apply_inbox` set the
  object state; assert `store.objects.get(uid).state`.
- With **no** provider registered, `--push` leaves the outbox pending and `--ingest`
  is a no-op — no error (pure-local).
- **Provider-agnostic invariant:** the core sync module imports nothing under
  `atdd.integrations.github`; a static test asserts no GitHub import on the sync path.

## Out of scope

- The GitHub ingester + provider (Deliverable B, extension repo).
- Deleting the manifest mirror (#1270 Slice G, downstream).
