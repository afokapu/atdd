# ATDD State Store — architecture spec

Umbrella: #1168 · Phase 1 implementation: #1177

The **ATDD State Store** is ATDD's local, SQLite-backed *operational truth* —
the durable, queryable store for work items, phase/status, worktree bindings,
external references, sync inbox/outbox, runtime checkpoints, and (later) Hub
sessions/adapter events. It is a foundational core capability, **independent of
the Hub** (#1096), which consumes it as a domain rather than owning the schema.

This document specifies the layout substrate delivered in **Phase 1** (#1177):
the terminology, the Control Root resolver, and the `atdd state doctor` /
`atdd state layout --check` commands. SQLite migrations, manifest import, and
provider sync are #1168 Phases 2–5.

## Source-of-truth boundary

| Layer | Truth | Examples |
|-------|-------|----------|
| Git-tracked protocol files | **protocol truth** | `plan/`, `plan/_trains.yaml`, conventions, validators, schemas, WMBTs, source, tests |
| State Store (`<control-root>/.atdd/state/state.sqlite`) | **operational truth** | work items, phase/status, branch/worktree bindings, external refs, sync inbox/outbox, runtime checkpoints |
| External providers | **external side-effect truth** | GitHub issues/PRs, Project boards, cmux sessions |

A GitHub issue number is therefore an **external reference / projection**, not
the identity of a work item — the local record is authoritative (cf. #945, and
the `atdd plan` Confirm binding in #1171, which binds to a local slug).

## Terminology

| Term | Definition |
|------|------------|
| **ATDD Control Root** | the local directory that owns `.atdd/` (and thus the State Store) |
| **Git worktree root** | a concrete git checkout/worktree (`repo/`, `project/main/`, …) |
| **State Store** | `<control-root>/.atdd/state/state.sqlite` |
| **workspace provider** / **resolved workspace** | reserved for the extension system — *not* reused for the Control Root |

## Layout modes

### Single-repo mode (today)

```
repo/                     # Control Root == Git worktree root
  .atdd/state/state.sqlite
  plan/  src/  tests/
```

### Sibling-worktree mode (target for parallel worktrees)

```
project/                  # Control Root
  .atdd/state/state.sqlite   # the ONE shared store
  main/                   # Git worktree root
  worktree1/              # Git worktree root
```

All sibling worktrees share the single Control-Root store. A child worktree MUST
NOT carry its own `.atdd/state/state.sqlite`.

### Ambiguous layout → fail loudly

If both a parent `.atdd/` and a child-worktree `.atdd/` exist, ATDD refuses to
guess (a split-brain store is worse than an error):

```
ERROR: Ambiguous ATDD Control Root.
Found both:
  project/.atdd
  project/main/.atdd
Choose one layout or run the migration command.
```

## Control Root resolver

Implemented in `src/atdd/state/paths.py::resolve_control_root`. Order:

1. `ATDD_CONTROL_ROOT` override (if set).
2. Find the enclosing Git worktree root (nearest `.git` walking upward).
3. worktree is a Control Root and parent is not → **single-repo**.
4. parent is a Control Root and current is a child worktree → **sibling-worktree**.
5. both parent and worktree are Control Roots → **fail loudly** (`AmbiguousControlRootError`).
6. otherwise walk upward for a Control Root; if none → `ControlRootNotFoundError`.

Output: `control_root`, `git_worktree_root`, `layout_mode`, `state_store_path`.

### What counts as a Control Root (#1179)

"Control Root" means an **initialized** `.atdd/`, not merely a `.atdd/`
directory. `is_control_root(dir)` is true only when the `.atdd/` carries an
initialized-root signal — a marker file (`control-root.yaml` / `config.yaml` /
`manifest.yaml`) or the `state/` directory. A **scratch-only** `.atdd/` holding
just `cache/` / `runtime/` / `diagnostics/` (`is_scratch_atdd(dir)`) is ignored:
it never shadows a real worktree Control Root and never triggers a false
ambiguity. This is what lets the resolver work correctly in the flat
sibling-worktree dev layout (see below).

## Commands (Phase 1)

- `atdd state doctor [--root DIR]` — prints Control Root, Git worktree root,
  layout mode, and State Store path with a status line. Exit `0` OK, `1` layout
  violation, `2` ambiguous/not-found.
- `atdd state layout --check [--root DIR]` — validates the layout; exit `1` on a
  violation (e.g. a per-worktree State Store), `2` on ambiguous/not-found.

`atdd state init` / `migrate-layout` and the SQLite schema are deferred to
#1168 Phase 2+.

## Field observation + resolution (#1177 → #1179)

The standard ATDD development setup uses **flat sibling worktrees** under a
common parent (`~/Github/atdd/main`, `~/Github/atdd/feat-*`, …). Tools that run
with the parent as cwd leave a **stray parent `.atdd/`** holding only `cache/`,
`diagnostics/`, `runtime/`. Because every git-tracked worktree also ships a full
`.atdd/` (with `manifest.yaml`, `config.yaml`), the original #1177 resolver
reported this parent+child pair as *ambiguous*.

**Resolved in #1179:** the stray parent is scratch (no Control Root marker), so
the resolver now ignores it and resolves each worktree as **single-repo**.
`atdd state doctor` prints a `Note: ignored scratch .atdd at …` diagnostic
rather than failing. The genuine split-brain case (two *initialized* `.atdd/`)
still fails loudly per rule 5.
