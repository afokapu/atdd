# Extension-first architecture

ATDD is migrating from a Python-centric validation toolkit into an extensible
agent-delivery protocol: a small, protected **core** plus self-contained
**extension** packages, one per use case, language, or workspace.

```text
ATDD core      the protocol engine (schemas, lifecycle, gates)
extension      a self-contained use-case package (conventions, scopes, gate
               fragments, validators, tests, fixtures, runtime/workspace)
workspace      a runtime/build/test environment an extension uses
```

The guiding rule: **a use case never scatters files across core.** It is
packaged as one extension owning its substrate behind a manifest boundary, so
it can be installed, indexed, and removed as a unit.

## Naming

Packages use `<publisher>.<scope>.<artifact-name>`, where scope is
`core` or `extension`. `atdd.*` is the reserved publisher for official packages.

```text
atdd.core.*                 official core/protocol artifacts
atdd.extension.*            official ATDD extensions
<publisher>.extension.*     external/project/team extensions
```

## Where things live

```text
src/atdd/                      ATDD core protocol
extensions/<extension-id>/     source extensions (this repo)
.atdd/extensions/<id>/<ver>/   installed extensions (consumer repo)
```

## Authoring substrate — `atdd author`

`atdd author` creates schema-valid artifacts **by construction**: the malformed
case is impossible because every command validates role/id/path on a shared
spine, and the artifact against its frozen schema, before any write.

**Extension-first by default.** It writes into a self-contained extension
package; `--core` is required, and protected, to touch the core protocol.

```bash
# extension-first (default) — writes into extensions/<publisher>.extension.<name>/
atdd author convention-node --extension acme.extension.component-header \
  --rule-id coder.source.header-required --statement "..." --term "marker=..."
atdd author relationship --extension acme.extension.component-header \
  --source coder.source.a --type enables --target coder.source.b
atdd author scope --extension acme.extension.component-header \
  --scope-id scope.source.python --artifact-kind source_file \
  --selector-id selector.source.python.glob --selector-type path_glob \
  --include "src/**/*.py" --exclude ".venv/**"
atdd author gate --extension acme.extension.component-header \
  --gate-id gate.pre_push.x --trigger-type git_hook --trigger-name pre-push \
  --selection blast_radius --action block

# core protocol (explicit, protected)
atdd author convention-node --core --role coach \
  --rule-id coach.extension.manifest-has-owner-boundary --statement "..."
```

`atdd author` also authors plan-layer artifacts — `wagon`, `feature`, `wmbt`,
`train`, `interlocking`, `contract`, `acceptance` — and `issue`, `extension`,
`workspace`, and `implementation`.

### Artifact kinds and homes

| Kind | Extension home | Core home |
|---|---|---|
| convention-node | `conventions/<rule_id>.convention.yaml` (per-file) | `src/atdd/<role>/conventions/nodes/` |
| scope (+ embedded selectors) | `scopes/<scope_id>.scope.yaml` (per-file) | `src/atdd/coach/selectors/scopes/` |
| relationship fragment | `relationships.yaml` | `src/atdd/coach/graph/relationships.yaml` |
| gate fragment | `gates/<trigger>.fragment.yaml` | `src/atdd/coach/gates/<trigger>.yaml` |

Registry-class kinds (relationship, scope, gate) use deterministic
sorted-insert. Concurrent inserts into the same registry resolve through a
`.gitattributes`-registered re-sort/dedup git **merge driver**, so parallel
authoring never produces hand-merge conflicts.

## Managing the substrate — `atdd substrate`

`atdd substrate` operates on the local install ledger
(`.atdd/substrate.lock.yaml` + `.atdd/binding.lock.yaml`), covering both
`atdd.extension.*` and `atdd.workspace.*` packages:

```text
atdd substrate add <ref|--path>    admit an extension/workspace into the local substrate
atdd substrate remove <id>         withdraw an admitted artifact (refuses dependents unless --force)
atdd substrate bind [--check]      compose the runtime binding plan from the locked substrate
atdd substrate capabilities        show conventions gated by bound implementations vs legacy-fallback
atdd substrate list                list the installed substrate from the lockfile
```

The flat `atdd add` / `remove` / `bind` / `capabilities` verbs, and
`atdd list --substrate`, remain as deprecated-but-working aliases that print a
notice pointing at the grouped form. Their removal is the breaking `4.0.0` step
tracked in #1207. `atdd enforce` and `atdd validate` stay top-level: they are
the CI/operator hot path, not substrate administration.

## Boundary recap

```text
atdd author     creates compliant substrate artifacts (extension by default; --core protected)
atdd substrate  admits / binds / inspects the local substrate
atdd validate   verifies substrate artifacts
atdd enforce    enforces the binding plan over consumer code
atdd gate       decides whether a validation failure blocks
```

## Migration phases

| Phase | Scope | Status |
|---|---|---|
| 1 | substrate schemas + extension-first `atdd author` (with `--core` protection); first Python workspace extension | shipped |
| 2 | wrap existing validators in extension/implementation manifests; keep legacy paths working | next |
| 3 | new validators only via extension bundles; move mature validators into extension packages | planned |
| 4 | consumer repos install only the extensions/workspaces they need | planned |

`atdd author` is the **authoring** half. The **packaging** half — extension,
workspace, and implementation manifests, install/remove, validation-flow wiring
— is built as a separate wagon that consumes `atdd author` inside a train to
assemble an extension.
