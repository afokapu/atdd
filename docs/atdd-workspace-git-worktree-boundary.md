# `atdd.workspace.git-worktree` — Workspace Provider Boundary Specification

> **Issue #1119 (Slice 3 of #1113).** Backlog materialization. Specifies the
> **workspace-provider** boundary (NOT an extension — no domain conventions). Moves no
> conventions, changes no core, implements no runtime. Source rows from
> `docs/coach-convention-decomposition-plan.md` (PR #1115).

## 1. Identity (workspace-shaped)

```yaml
workspace_id: atdd.workspace.git-worktree
kind: workspace
contract_version: "1.0.0"     # the isolated-execution-context + config-safety contract
runtime:
  vcs: git
  capability: worktree-isolation
```

A workspace **provides runtime**, it does not own behavior. This one provides the
**isolated execution context** (one git worktree per delivery unit) and **git-config
safety**. Manifest is `atdd.workspace.yaml` (mirror `atdd.workspace.python-pytest`), NOT
`atdd.extension.yaml`. No `owns: {conventions}` block — that's extension-shaped.

## 2. What it provides

- The per-unit isolated execution context that `coach.execution.one-agent-per-delivery-unit`
  (core) assumes — realized as a git worktree (flat sibling).
- Git-config danger-key safety (`core.bare`/`core.worktree`/`core.hooksPath` must be
  `--worktree`-scoped) via the `.atdd/bin/git` PATH shim.
- Commit-trailer git mechanics (`git interpret-trailers` parsing for phase/wmbt/agent).

## 3. Source rows → workspace material

| source_file | section | becomes |
|-------------|---------|---------|
| `path_shim_git.convention.yaml` | `patterns` | shim implementation + provider conformance check |
| `forbidden_commands.convention.yaml` | `ATDD-FORBID-GIT-CONFIG-BARE-UNSCOPED` | command-policy pattern |
| `commit-trailers.convention.yaml` | phase/wmbt/agent trailer mechanics | trailer-parse implementation |

## 4. Owns / does not own

**Owns:** the worktree-isolation + git-config-safety runtime contract; the git shim
implementation; a conformance suite proving an alternate VCS provider satisfies the same
isolation contract.

**Does not own:** GitHub issue/PR semantics (→ `atdd.extension.github`); the *requirement*
that one unit = one isolated context (that's core `coach.execution.one-agent-per-delivery-unit`)
— this workspace only *realizes* it.

## 5. Graph Context

No convention nodes, no relationship-graph change. Any provider-local relationships would
live in the package's own graph (`atdd.workspace.git-worktree.relationships`); composition
with the core graph is deferred (#1122). Core node this realizes (references, never
redefines): `coach.execution.one-agent-per-delivery-unit`.

## 6. Acceptance

- [ ] workspace-provider boundary specified (manifest is workspace-shaped)
- [ ] source rows mapped
- [ ] no core files changed; no runtime implemented (stub/deferred)
- [ ] distinction from the extension shape stated (no `owns: conventions`)
