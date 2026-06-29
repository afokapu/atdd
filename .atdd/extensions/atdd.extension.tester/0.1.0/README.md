# atdd.extension.tester

Official ATDD **tester-role extension**. It owns every tester convention node
classified `extension` in the coder/tester decomposition — the stack-bound tester
rules that name or are inseparable from a specific runtime, test framework, or
persistence engine (test filename mechanics, Postgres/Supabase migration naming,
runtime-path routing, preact-DOM presentation smoke, the contract persistence +
api_structure bindings).

> **Boundary in one line:** *Core owns the stack-neutral tester principles. This
> extension owns how those principles are realized on a concrete stack.* It never
> redeclares a core tester node — it references the one each convention realizes.

## Identity

```text
publisher : atdd
kind      : extension
name      : tester
id        : atdd.extension.tester
manifest  : atdd.extension.yaml
```

## Status — skeleton

This slice ships the **structural skeleton only**: the manifest, an empty
extension-local `relationships.yaml` graph, and empty `conventions/` +
`implementations/` directories. Convention node bodies are **authored later** and
reference the deduped core tester node ids (which must land first — see
`docs/coder-tester-extension-decomposition/DESIGN.md` §5 Open Decision 6). No
convention or implementation is authored here yet.

## Layout

```text
atdd.extension.tester/
  atdd.extension.yaml      # manifest: id, role: tester, owns, depends_on.workspaces
  conventions/             # tester.<area>.<slug> nodes — authored in the build slice
  relationships.yaml       # extension-internal edges only (empty skeleton)
  implementations/         # detector dirs — authored in the build slice
  README.md
```

## Targets these runtimes

Tester detectors fan out across four workspace providers, declared in
`atdd.extension.yaml::depends_on.workspaces`:
`atdd.workspace.{python-pytest, typescript, supabase, fastapi}`.
