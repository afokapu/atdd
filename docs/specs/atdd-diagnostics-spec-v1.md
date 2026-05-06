# ATDD Validation Diagnostics — Spec v1

**Status**: Frozen as `schema_version: 1` (issue #449)
**Owner**: ATDD coach
**Consumers**: AI coding agents, CI dashboards, auto-fix tooling, PR comment bots, local human triage

This document freezes the on-disk schema and stdout format for the
validation diagnostics artifact. It is the contract that downstream
consumers (CI, agents, auto-fix codemods) read against. Behavioral
changes to the schema follow the [Schema versioning](#schema-versioning)
policy below.

---

## Overview

`atdd validate` runs pytest against the toolkit's validators and emits
two parallel artifacts on every run:

| Artifact                                              | Purpose                                       | Written when            |
|-------------------------------------------------------|-----------------------------------------------|-------------------------|
| `.atdd/baselines/validation/<phase>.yaml`             | Pass-proof for `--verify-baseline` (<10s CI)  | Only on pass            |
| `.atdd/diagnostics/validation/<phase>.yaml` (**new**) | Machine-readable failure record               | Every run (pass or fail) |

Diagnostics complement baselines — they are not a replacement.

---

## Schema (frozen for `schema_version: 1`)

```yaml
schema_version: 1
run:
  phase: coder                          # planner | tester | coder | coach | all
  ran_at: "2026-05-06T13:45:00Z"        # ISO-8601 UTC, second precision
  duration_seconds: 4.83
  atdd_version: "3.7.0"
  invocation: "atdd validate --local"
  outcome:
    passed: 426
    failed: 27
    skipped: 99
    deselected: 0
findings:
  - validator_id: test_python_test_classes_named_correctly
    validator_path: tester/validators/test_python_test_naming.py
    category: naming                     # closed enum (see below)
    severity: error                      # error | warning
    convention_ref:
      file: tester/conventions/filename.convention.yaml
      anchor: test_class_pascalcase
    summary: "5 test classes do not use PascalCase after 'Test'"
    items:
      - file: python/analyze_ledger/tests/test_navigate_domains.py
        line: 42
        column: null
        symbol: TestL001_LoadYamlFiles
        expected: TestL001LoadYamlFiles
        found: TestL001_LoadYamlFiles
        fix: "Rename TestL001_LoadYamlFiles to TestL001LoadYamlFiles"
        extra: {}
    raw_message: |                       # ALWAYS populated, verbatim from pytest.fail
      Found 5 class naming violations:
      ...
toolkit_packaging_issues:
  - resource: tester/validators/fixtures/train_renders_content/fail_stub/harness_output.json
    referenced_by: [test_analyzer_fail_stub_fixture_emits_render_002]
```

### Field semantics

#### `run`

| Field                | Type    | Notes                                                                |
|----------------------|---------|----------------------------------------------------------------------|
| `phase`              | string  | One of `planner`, `tester`, `coder`, `coach`, `all`.                 |
| `ran_at`             | string  | ISO-8601 UTC, second precision (e.g. `"2026-05-06T13:45:00Z"`).      |
| `duration_seconds`   | number  | Wall-clock seconds, rounded to 2dp.                                  |
| `atdd_version`       | string  | `atdd.__version__` at run time.                                      |
| `invocation`         | string  | Best-effort recovery of `argv` ("atdd validate --local").            |
| `outcome`            | object  | Aggregate counts. Keys: `passed`, `failed`, `skipped`, `deselected`. |

#### `findings[]`

One entry per failing validator. Migrated validators emit fully
populated `items[]`; non-migrated validators emit `items: []` and
populate `raw_message` only.

| Field             | Type        | Notes                                                                 |
|-------------------|-------------|-----------------------------------------------------------------------|
| `validator_id`    | string      | Test function name (e.g. `test_python_test_classes_named_correctly`). |
| `validator_path`  | string\|null| Repository-relative validator path.                                   |
| `category`        | string      | Closed enum (see below).                                              |
| `severity`        | string      | `error` or `warning`.                                                 |
| `convention_ref`  | object\|absent | Pointer to backing convention rule. Absent when not provided.      |
| `summary`         | string      | Short one-line summary. Default: first non-empty line of message.     |
| `items[]`         | array       | Per-violation rows. May be empty (structural failure / unmigrated).   |
| `raw_message`     | string      | **Always populated** — verbatim text passed to `pytest.fail`.         |

#### `findings[].category` (closed enum)

```
naming        missing-file   contract       boundary
hygiene       quality        train          workflow
convention    unmigrated
```

`unmigrated` is the auto-assigned bucket when a validator failed without
calling `fail_with_diagnostic()`. Its presence and growth/shrink rate
should drive the next round of validator migrations.

#### `findings[].items[]`

| Field      | Type            | Notes                                                                       |
|------------|-----------------|-----------------------------------------------------------------------------|
| `file`     | string\|null    | Repo-relative file path of the offending site.                              |
| `line`     | int\|null       | 1-based line number. Only populated for migrated validators.                |
| `column`   | int\|null       | 1-based column. Rarely populated.                                           |
| `symbol`   | string\|null    | The offending identifier (class, function, file path).                      |
| `expected` | string\|null    | What the convention requires (e.g. `TestFooBar`).                           |
| `found`    | string\|null    | What was actually found (e.g. `TestFoo_Bar`).                               |
| `fix`      | string\|null    | One-line actionable fix (suitable for codemod prompts).                     |
| `extra`    | object          | Free-form per-category bag (e.g. `{"reason": "too-short"}`).                |

#### `toolkit_packaging_issues[]`

Populated when a validator hits `FileNotFoundError` whose path resolves
to a file under the installed `atdd/` package directory (Decision #5,
issue #449). Detection uses `Path.resolve()` + `Path.is_relative_to()`
— substring matching is forbidden because consumer tmp paths can
contain the substring `atdd`.

| Field           | Type     | Notes                                            |
|-----------------|----------|--------------------------------------------------|
| `resource`      | string   | Absolute path to the missing toolkit resource.   |
| `referenced_by` | string[] | nodeids of every validator that hit the missing path. |

---

## Stdout summary (printed only when `failed > 0`)

```
=== DIAGNOSTICS (27 findings, 5 categories) ===
[naming        ]  1 finding,  5 items
[hygiene       ]  3 findings, 13 items
[missing-file  ]  6 findings,  6 items
[contract      ]  2 findings,  2 items
[train         ] 15 findings, 15 items

Top fixes (sorted by category, capped at 10):
  python/analyze_ledger/tests/test_navigate_domains.py:42
    Rename TestL001_LoadYamlFiles to TestL001LoadYamlFiles
  python/analyze_ledger/tests/test_basic.py:10
    Remove sys.path manipulation — pytest pythonpath handles this
  ...

Full diagnostics: .atdd/diagnostics/validation/coder.yaml (27 findings)
Toolkit packaging issues: 5 (see file)
```

The format is intentionally **not** a frozen string snapshot — tests assert
*structure* (header line, one `[<category>]` per category, `Top fixes`
header, capped at 10 entries, footer with artifact path). See the issue
body for rationale.

---

## Plugin behavior

### Loading

The plugin is loaded **only** by `atdd validate` via argv injection:

```python
cmd.extend(["-p", "atdd.coach.plugins.diagnostics"])
```

It MUST NOT be added to any `conftest.py` or `pytest_plugins` list — that
would auto-load it in consumer test suites outside `atdd validate`,
violating the v1 scope.

### Hooks

| Hook                         | Behavior                                                       |
|------------------------------|----------------------------------------------------------------|
| `pytest_sessionstart`        | Reset state, clear pending findings.                           |
| `pytest_runtest_setup`       | Record active nodeid (for `fail_with_diagnostic`).             |
| `pytest_runtest_logreport`   | Capture failures into findings + toolkit-packaging-issue scan. |
| `pytest_runtest_teardown`    | Clear active nodeid.                                           |
| `pytest_deselected`          | Tally deselected count.                                        |
| `pytest_sessionfinish`       | Write artifact (master only) + print summary if any failures.  |

### Disable conditions

The plugin short-circuits (no artifact write, no stdout summary) when:

1. The `ATDD_DIAGNOSTICS_DISABLED=1` env var is set. The runner sets
   this on `atdd validate --verify-baseline` (GT-140 regression).
2. Running on a pytest-xdist worker (`session.config.workerinput`
   truthy). Only the master writes.
3. The user passes `--no-diagnostics` to `atdd validate` — the runner
   omits the `-p atdd.coach.plugins.diagnostics` argv injection
   entirely.

---

## CLI

```
atdd validate [phase] [--no-diagnostics] [--diagnostics-only] [--verify-baseline]
```

| Flag                  | Behavior                                                                 |
|-----------------------|--------------------------------------------------------------------------|
| (default)             | Diagnostics enabled — artifact written every run.                        |
| `--no-diagnostics`    | Suppresses artifact + stdout summary. Plugin not loaded.                 |
| `--diagnostics-only`  | Reads + prints latest artifact in <100 ms. No pytest invocation.         |
| `--verify-baseline`   | Existing baseline-freshness check. Diagnostics plugin is a no-op (GT-140). |

---

## Schema versioning

The schema is frozen as `schema_version: 1`. Future evolution follows
the policy below.

### Breaking-change policy

Any of the following changes bump the schema version to v2:

* Removing or renaming a top-level field (`schema_version`, `run`, `findings`, `toolkit_packaging_issues`).
* Removing or renaming a field within `run`, `findings[]`, `findings[].items[]`, or `toolkit_packaging_issues[]`.
* Changing the type of any existing field.
* Changing the semantics of an existing field (e.g. flipping `outcome.failed` from a count to a boolean).
* Removing a value from the `findings[].category` enum.

Additive changes (new optional fields, new categories, new severity
values) are **minor** and do NOT bump the schema version. Consumers
MUST tolerate unknown fields gracefully.

### Emission policy

The plugin writes whatever `schema_version` is baked into its own code.
There is no config switch — to opt out of v1 emission, downstream
consumers stop reading the artifact (or use `--no-diagnostics`). When
the toolkit ships v2, every `atdd validate` invocation begins emitting
v2 artifacts; consumers must check `schema_version` before parsing.

### Consumer guidance

Consumers MUST:

1. Check `schema_version` before parsing.
2. Degrade gracefully on unrecognized values — log and skip the
   artifact, do not crash.
3. Tolerate additional unknown fields (forward-compatibility).

Consumers SHOULD:

1. Pin against a specific schema version range in their own
   documentation.
2. Track the toolkit `Changelog` for schema bumps.

---

## References

* Issue #449 — implementation tracker
* `.atdd/baselines/validation/` — parallel pass-proof artifact
* `src/atdd/coach/utils/disposition_gate.py` — issue #395
  (read-only consumer for migrated quality validators)
