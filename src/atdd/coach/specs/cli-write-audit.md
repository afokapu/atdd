# CLI write-call audit

Issue: #342 — atdd CLI mutates config on read.
Captured: 2026-05-01.

## Audit method

Walked every disk-write reachable from `atdd.cli.cli()` (the entry point invoked
by `python -m atdd` and the `atdd` console script). Wrote-classifying each
call by whether it is bug, must-stay, or must-move-behind-explicit-verb.

## Call sites

| # | Caller | Write target | Trigger | Classification |
|---|--------|--------------|---------|----------------|
| 1 | `version_check.print_upgrade_sync_notice()` → `AgentConfigSync().sync()` (line 137 of `cli.py:cli()`) | `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` / `QWEN.md` | Every CLI invocation when installed version > `toolkit.last_version` | **Bug** — must move behind `atdd sync` only |
| 2 | `version_check.print_upgrade_sync_notice()` → `update_toolkit_version()` | `.atdd/config.yaml` (`toolkit.last_version`) | Every CLI invocation when version drift detected | **Bug** — must move behind `atdd sync` only |
| 3 | ~~`version_check.print_upgrade_sync_notice()` → `AgentConfigSync.sync()` → `ProjectInitializer._write_workspace()`~~ | ~~`<repo-parent>/<workspace-name>.code-workspace`~~ | — | **Resolved by removal (#1646)** — the VS Code `.code-workspace` generator is decommissioned; no call site writes this file any more |
| 4 | `version_check._save_cache()` (called by `print_update_notice`) | `~/.atdd/version_cache.json` | Daily PyPI freshness check | **Must-stay** — outside repo, user-scoped |
| 5 | `coach.commands.validation_baseline.write_validation_baseline()` | `.atdd/baselines/validators.yaml` | Only when `atdd validate` exits 0 | **Must-stay** — explicit `atdd validate` verb already opted in |
| 6 | `ProjectInitializer.init()` (writes `.atdd/config.yaml`, `.atdd/manifest.yaml`, agent files, workspace) | repo files | Only when `atdd init` runs | **Must-stay** — explicit `atdd init` verb |
| 7 | `AgentConfigSync.sync()` direct invocation (when user runs `atdd sync`) | agent config files + `.atdd/config.yaml` | Only when `atdd sync` runs | **Must-stay** — explicit `atdd sync` verb |

## Fix summary

Calls (1)–(3) all flow from the same line in `cli.py`:

```python
def cli() -> int:
    if not (len(sys.argv) > 1 and sys.argv[1] == "upgrade"):
        print_upgrade_sync_notice()
    ...
```

`print_upgrade_sync_notice` does three things today: prints the warning, runs
`AgentConfigSync().sync()`, and calls `update_toolkit_version()`. The first is
useful and should stay; the latter two are the bug.

Fix: split the function. `print_upgrade_sync_notice` becomes warn-only — it
prints the upgrade banner to stderr and returns. The auto-sync + version-stamp
pair is moved into `AgentConfigSync.sync()` (which already writes
`toolkit.last_version` at the end of its run, so a user invoking `atdd sync`
clears the drift). Call site 3 needed no such split: #1646 decommissioned the
VS Code `.code-workspace` generator outright, so the write it describes has no
producer left.

Net: read-only commands (`--help`, `status`, `inventory`, `list`, `validate`,
`gate`, `version`, `urn families`, `issue --help`) leave the working tree
clean; explicit verbs (`init`, `sync`, `upgrade`) remain the only paths that
write `.atdd/config.yaml`. Nothing writes outside the repo root any more.
