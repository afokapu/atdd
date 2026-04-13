# ATDD Session Launch — Issue #{{issue_number}}

You are implementing **atdd issue #{{issue_number}}** ({{title}}) in the
worktree at `{{worktree_path}}` on branch `{{branch}}`.

## Pre-flight

1. Read CLAUDE.md in the worktree root.
2. Run `atdd gate` to confirm ATDD rules are loaded.
3. Run `gh issue view {{issue_number}} --json body --jq '.body'` to see the full issue body.

## Issue context

- **Number:** {{issue_number}}
- **Branch:** {{branch}}
- **Train:** {{train}}
- **Feature:** {{feature}}

## Dependencies

{{dependencies}}

Before starting, wait for all dependency PRs to merge. Use this loop:

```bash
while true; do
  if gh pr list --state merged --search "{{dependency_search}}" --json number --jq 'length' | grep -qv '^0$'; then
    echo "Dependencies merged — proceeding"
    break
  fi
  echo "Waiting for dependencies..."
  sleep 60
done
```

## Grep gates (WMBT acceptance criteria)

These must all return a positive count before the session can report GREEN:

{{grep_gates}}

## Stop condition

{{stop_condition}}

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
