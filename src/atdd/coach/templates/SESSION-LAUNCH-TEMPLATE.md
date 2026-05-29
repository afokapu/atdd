# ATDD Session Launch — Issue #{{issue_number}}

You are implementing **atdd issue #{{issue_number}}** ({{title}}) in the
worktree at `{{worktree_path}}` on branch `{{branch}}`.

## Pre-flight

1. Read CLAUDE.md in the worktree root.
2. Run `atdd gate` to confirm ATDD rules are loaded (output includes available diagnostic commands).
3. Run `atdd repo validate` to check URN traceability — fix any errors before writing code.
4. Run `gh issue view {{issue_number}} --json body --jq '.body'` to see the full issue body.
5. Run `atdd repo graph --wagon {{wagon}} --format launch-prompt` to see the wagon architecture (re-run before committing PLANNED to catch architectural drift).

## Wagon Architecture

{{wagon_graph_section}}

## Issue context

- **Number:** {{issue_number}}
- **Branch:** {{branch}}
- **Train:** {{train}}
- **Feature:** {{feature}}
- **Canonical session name:** `{{canonical_session_name}}` (per orchestration.convention.yaml::session_naming — issue #470). The cmux tab and Claude session header should both match this; if they don't, run `/rename {{canonical_session_name}}` and the babysitter will reconcile the cmux side on the next tick.

## Dependencies

{{dependencies}}

{{merge_wait_section}}

## Grep gates (WMBT acceptance criteria)

These must all return a positive count before the session can report GREEN:

{{grep_gates}}

## Stop condition

{{stop_condition}}

## Planner pre-commit gate (INIT → PLANNED)

If this session is the PLANNER phase (issue is in INIT state), you MUST run
this gate **before** committing PLANNED:

```
atdd validate planner --local --skip-api
```

**Rule enforced:** `planner.wmbt.must-have-smoke-acceptance` (sev 3, suppress-and-clean)

Every WMBT you author MUST declare at least one acceptance URN matching:
`acc:<wagon>:<wmbt_id>-SMOKE-NNN[-<slug>]` with `phase: SMOKE`

Zero violations required before committing. If the validator reports a
`planner.wmbt.must-have-smoke-acceptance` violation, add the missing SMOKE
acceptance to the offending WMBT YAML and re-run until clean. Only then commit
PLANNED. Docs-only WMBTs with no real infrastructure to verify can suppress
inline: `# atdd:suppress(planner.wmbt.must-have-smoke-acceptance) UNTIL=YYYY-MM-DD`

## Workflow

Follow the ATDD lifecycle strictly:

1. **RED** — write failing tests from the WMBTs
2. **GREEN** — make the tests pass with minimal code
3. **SMOKE** — verify against real infrastructure
4. **REFACTOR** — clean architecture (stop here for user review unless `--autonomous`)

Commit after every completed sub-task (micro-commit discipline). Never
accumulate more than 5 modified files without committing.

## Escalation

If any of the following occur, stop and report rather than pushing through:

- Architectural decision missing from issue body
- Phase requires data not in scope
- A test fails and the fix is not obvious
- REFACTOR phase completes (stop for user review)
