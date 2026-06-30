# atdd.extension.coder

Official ATDD **coder-role extension**. It owns every coder convention node
classified `extension` in the coder/tester decomposition — the stack-bound coder
rules that name or are inseparable from a specific language, framework, or
platform tool (per-language file suffixes, JSX/React no-stub detectors, the
Flutter design-system layer, TS/Python complexity + quality + duplication
metrics, FastAPI route auth, AWS secret scanning, …).

> **Boundary in one line:** *Core owns the stack-neutral coder principles. This
> extension owns how those principles are realized on a concrete stack.* It never
> redeclares a core coder node — it references the one each convention realizes.

## Identity

```text
publisher : atdd
kind      : extension
name      : coder
id        : atdd.extension.coder
manifest  : atdd.extension.yaml
```

## Status — skeleton

This slice ships the **structural skeleton only**: the manifest, an empty
extension-local `relationships.yaml` graph, and empty `conventions/` +
`implementations/` directories. Convention node bodies are **authored later** and
reference the deduped core coder node ids (which must land first — see
`docs/coder-tester-extension-decomposition/DESIGN.md` §5 Open Decision 6). No
convention or implementation is authored here yet.

## Layout

```text
atdd.extension.coder/
  atdd.extension.yaml      # manifest: id, role: coder, owns, depends_on.workspaces
  conventions/             # coder.<area>.<slug> nodes — authored in the build slice
  relationships.yaml       # extension-internal edges only (empty skeleton)
  implementations/         # detector dirs — authored in the build slice
  README.md
```

## Targets these runtimes

Coder detectors fan out across five workspace providers, declared in
`atdd.extension.yaml::depends_on.workspaces`:
`atdd.workspace.{python-pytest, typescript, dart-flutter, supabase, fastapi}`.
