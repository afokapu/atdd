# atdd.workspace.python-pytest

Official ATDD **workspace provider** — a reusable, domain-agnostic Python/pytest
runtime that validator implementations run inside.

This is a *provider*, not a use-case extension. It owns runtime machinery only
(language, runner, package manager, command, discovery + run contract). It does
**not** own conventions, scopes, gates, or any backend/frontend/domain semantics
— those live in the extensions that depend on it.

## Contract

- **id:** `atdd.workspace.python-pytest` (scope segment `workspace`)
- **contract_version:** `1.0.0` — the discovery + run contract implementations
  must satisfy. The resolver checks an implementation's `contract_version`
  against this with SemVer (`^1.0.0`) and refuses on mismatch.

## How extensions use it

An extension declares the dependency in its `atdd.extension.yaml`:

```yaml
depends_on:
  workspaces:
    - id: atdd.workspace.python-pytest
      contract: "^1.0.0"
```

Each `atdd.implementation.yaml` the extension ships declares
`targets_workspace: atdd.workspace.python-pytest` and the `contract_version` it
satisfies. At resolve time the provider is materialized into a **workspace
instance** under `.atdd/resolved-workspaces/atdd.workspace.python-pytest/<version>/`
and the implementations are run there. Instances are generated, cacheable, and
never committed.

## Layout

```text
atdd.workspace.python-pytest/
  atdd.workspace.yaml      # provider manifest (id, contract_version, runtime, discovers)
  runtime/                 # shared runtime files materialized into each instance
  adapter/                 # discover.py + run.py — the contract implementation
  cli/                     # scan.py — the CW-Phase 0 subprocess CLI boundary
  conformance/             # proves this provider satisfies contract_version 1.0.0
```

## Provider CLI (`cli/scan.py`) — the subprocess boundary

`cli/scan.py` is the provider-agnostic entrypoint an external consumer (ATDD
core) shells out to. It resolves a discovered detector implementation, runs it
over caller-supplied scan roots, and prints the **RAW v1.1 violation list** on
stdout. The provider applies **zero disposition** — pass/fail is the consumer's
job. See the CW-Phase 0 proof (`CW-PHASE0-PROOF.md` in the core repo).

```text
INVOKE   python3 cli/scan.py [--impl <implementation_id>] [<scan_root> ...]

IN       env ATDD_SCAN_ROOTS     JSON array of paths (consumer code-under-inspection;
                                 absolute = verbatim, relative = vs the impl dir).
                                 Positional argv roots override it.
         env ATDD_SCAN_EXCLUDES  JSON array of globs (optional).
         env ATDD_IMPL_ID        implementation_id (default coder.logging.print);
                                 --impl overrides.

OUT      stdout  JSON array of {rule_id, file, line, col, evidence, source_line}
         stderr  one `provider-cli: ...` run-health line

EXIT     0  ran + emitted report (run-health, NOT a verdict)
         2  resolution/usage error (no roots; impl not discoverable)
```

The CLI imports only the provider's own `adapter/`; it never imports ATDD core,
and core never imports it. The JSON on stdout is the only thing that crosses.
