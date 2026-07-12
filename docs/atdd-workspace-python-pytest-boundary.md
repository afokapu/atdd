# `atdd.workspace.python-pytest` — Workspace Provider Boundary Specification (extend existing)

> **Issue #1121 (Slice 3 of #1113).** Backlog materialization. Unlike #1119/#1120, this
> package **already exists** at `atdd-extensions/official/atdd.workspace.python-pytest`.
> This issue specifies what *additional* workspace-classified material it should absorb.
> Moves no conventions, changes no core, implements no runtime. Source rows from
> `docs/coach-convention-decomposition-plan.md` (PR #1115).

## 1. Identity (already shipped, workspace-shaped)

```yaml
workspace_id: atdd.workspace.python-pytest    # EXISTS
kind: workspace
contract_version: "1.0.0"
runtime: {language: python, runner: pytest, package_manager: pip, command: pytest}
```

The provider contract (`discovers.implementations`, `conformance/`) is already in place.
This issue only adds stack-specific *defaults*, not new contract surface.

## 2. What it should additionally provide

- Stack **root defaults/resolvers** (python/web; supabase — see §5) — the *config-driven*
  invariant stays core (`coach.graph.implementation-root-resolution`, shipped Slice 2);
  only the concrete stack defaults + the resolver registry move here.
- The db/be/fe per-archetype gate commands, where still coupled to the resolver surface.

## 3. Source rows → workspace material

| source_file | section | becomes |
|-------------|---------|---------|
| `code-roots.convention.yaml` | `config_surface.defaults` + `toolkit_heuristic` + `_RESOLVERS` + `baseline_policy` | stack resolver defaults + registry |
| `issue.convention.yaml` | `archetypes` (db/be/fe) + `rules.supabase_branching` | per-archetype gate config |

## 4. Owns / does not own

**Owns:** Python execution defaults, pytest execution, stack root resolvers, db/be/fe gate
config (while coupled).

**Does not own:** the config-driven-resolution *invariant* (core
`coach.graph.implementation-root-resolution`); domain rules (a runtime provider, not a
domain package).

## 5. Supabase boundary decision (required by acceptance)

Keep `supabase` defaults **here only while** coupled to the current resolver/gate surface.
If it becomes domain-specific (RLS, migrations semantics), split into its own
extension/workspace follow-up. **Decision to record in this issue:** keep-here vs split-now.

## 6. Graph Context

No convention nodes, no relationship-graph change. The existing package has its own
provider scope; core-graph composition of any provider-local relationships is deferred
(#1122). Core node referenced: `coach.graph.implementation-root-resolution`.

## 7. Acceptance

- [ ] additional workspace material specified against the EXISTING package (not a new one)
- [ ] source rows mapped
- [ ] supabase keep-vs-split decision recorded
- [ ] no core files changed; no runtime implemented (stub/deferred)
