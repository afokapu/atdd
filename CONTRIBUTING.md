# Contributing to ATDD

Thanks for working on ATDD. This file documents toolkit-specific workflows
that consumers don't need to know about.

For day-to-day usage, see [README.md](README.md).

## Dogfooding the substrate

The ATDD repo-substrate (spec v12) is a pytest plugin that anchors test
failures to acceptance rules in `plan/**/features/*.yaml`. It is registered
via a `pytest11` entry-point on the toolkit's `pyproject.toml` and is
auto-loaded in any environment where `atdd` is installed. The plugin is
gated at runtime on `.atdd/config.yaml::repo.substrate.enabled` — it is a
no-op for any consumer that hasn't opted in.

`atdd init` decides whether to opt in by heuristic (spec v12 §9.3):

| Layout | `plan/` | `src/atdd/` | Default mode |
|---|---|---|---|
| Greenfield consumer repo | absent | absent | `toolkit` (substrate inactive) |
| Working consumer repo | present | absent | `consumer-repo` |
| The toolkit's own checkout | present | present | `toolkit` |

The third row is what makes dogfooding interesting: the toolkit's own
checkout has both signals, so a bare `atdd init` correctly classifies it
as toolkit mode and the substrate stays inert. To dogfood the substrate
against the toolkit's own `plan/govern_lifecycle/`, run:

```sh
atdd init --consumer-repo
```

This writes the `repo:` block to `.atdd/config.yaml`:

```yaml
repo:
  test_root: tests/
  plan_root: plan/
  substrate:
    enabled: true
    plugin: atdd.tester.substrate.plugin
    mode: consumer-repo
```

…and on the next `pytest` run, the substrate plugin walks `tests/` for
`# Acceptance: <urn>` headers and routes assertion failures through the
disposition gate. To revert, run:

```sh
atdd init --toolkit
```

This removes the `repo:` block and the plugin returns to no-op mode.

### Mode persistence

A subsequent bare `atdd init --force` reads the existing
`repo.substrate.mode` and stays in mode — overriding requires explicit
`--consumer-repo` / `--toolkit`. Two consecutive
`atdd init --consumer-repo --force` runs are idempotent; same for
`--toolkit --force`. Mixing flags (`--consumer-repo --toolkit`) is
rejected with a non-zero exit code.

## Releasing

Every PR ends with a version bump in `pyproject.toml` and a
`v{version}` tag on the merge commit. See `CLAUDE.md::release` for the
end-to-end protocol.
