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
`v{version}` tag on the merge commit. See `docs/version-source-of-truth-design.md`
for the end-to-end protocol.

## Running tests

```bash
PYTHONPATH=src python3 -m pytest src/atdd/ -v
PYTHONPATH=src python3 -m pytest src/atdd/coder/validators/ -v
PYTHONPATH=src python3 -m pytest --cov=atdd --cov-report=html
```

## Adding a validator

1. Create `src/atdd/<role>/validators/test_<name>.py`.
2. Bind a canonical rule ID at module import. Failing loudly at import is
   deliberate (SPEC-COACH-RULEID-0007) — do not make `bind_rule` lazy.
3. Declare the rule in the matching convention YAML.
4. Emit normalized validator reports.

## Adding a convention

1. Create `src/atdd/<role>/conventions/<name>.convention.yaml`, or a flat node
   under `src/atdd/<role>/conventions/nodes/`.
2. Declare `id`, `severity`, `disposition`, `description`, and optional
   `fix_hint`. See [`docs/validators.md`](docs/validators.md) for dispositions.
3. Reference it from validators and planning briefs.

Prefer `atdd author convention-node`, which produces a schema-valid node by
construction. See [`docs/extensions.md`](docs/extensions.md).

## Adding a lifecycle phase

Edit `src/atdd/coach/conventions/phase_machine.convention.yaml` — the single
source of truth — plus **exactly one** Python line: a member of
`atdd.coach.core.types.Phase`. Everything else is projected from that file.

Forgetting the enum line fails closed and immediately:
`atdd.coach.handlers.state_machine` builds its table at import via
`Phase(name)`, so a phase declared in YAML and missing from the enum raises
`ValueError` and the coach runtime does not load at all. Three tests guard
this, all from #1946:

- `D004-UNIT-005::test_the_core_phase_enum_is_pinned_to_the_convention`
- `D004-UNIT-001::test_adding_a_phase_costs_exactly_one_python_edit`
- `D004-SMOKE-001::test_every_declared_phase_is_nameable_by_the_shipped_runtime`

## Worker model selection

Worker agents can run on any wrapper. Configure defaults in
`.atdd/config.yaml`; override per invocation:

```bash
atdd coach <N> --persona-llm tester=glm-5.1,coder=claude-sonnet-4-6
```

| Class | When to use |
|---|---|
| compliant | lifecycle work with structured prompts and fixed states |
| frontier | ambiguous design, novel planning, hard refactors |

See [`docs/MODELS.md`](docs/MODELS.md).

## Environment variables

| Var | Effect |
|---|---|
| `ATDD_MAX_UNCOMMITTED` | pre-push micro-commit warning threshold |
| `ATDD_MAX_STAGED` | pre-commit micro-commit warning threshold |
| `ATDD_SKIP_PREPUSH_VALIDATE` | bypass pre-push validator hook when needed |
