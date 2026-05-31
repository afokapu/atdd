# Operator guide — `PROJECT_TOKEN` for Projects v2 status sync

> Closes the #882 class of "the issue label flipped but the Projects v2 board
> Status field didn't." Companion to `docs/coach-decomposition.md` §4.10.

## Why this token exists

ATDD keeps two views of an issue's phase in lock-step:

1. the `atdd:<PHASE>` **label** on the GitHub issue, and
2. the **`ATDD Status`** single-select field on the GitHub **Projects v2** board.

GitHub's default `GITHUB_TOKEN` (the token GitHub Actions injects automatically)
**cannot write Projects v2** — org policy scopes it out (issue #404). So in CI the
label swap succeeded while the board write was silently denied, and the board
drifted (issue #882).

The fix routes every board write through a dedicated, separately-authenticated
call — `atdd.integrations.github.projects_v2.sync_status_field()` — which
**requires** a fine-grained Personal Access Token in the `PROJECT_TOKEN`
environment variable. With the PAT present the board write actually lands; without
it the system degrades to **label-only** sync and logs a loud warning (it never
crashes the transition).

## Create the PAT

1. Go to <https://github.com/settings/tokens?type=beta> (fine-grained tokens).
2. **Resource owner:** the org/user that owns the project board.
3. **Repository access:** the repos whose issues feed the board.
4. **Permissions:**
   - Repository → **Issues**: Read and write
   - Organization → **Projects** (or Repository → Projects): **Read and write**
5. Generate, copy the `github_pat_…` value (shown once).

## Wire it up

### Local / interactive use

```bash
export PROJECT_TOKEN=github_pat_xxxxxxxxxxxxxxxx
atdd issue 891 --status COMPLETE   # label AND board both update
```

Without `PROJECT_TOKEN` set, the same command still swaps the label and prints a
warning that the board was not synced — no error.

### CI (GitHub Actions)

Store the PAT as the repo/org secret **`PROJECT_TOKEN`** and pass it as
`GH_TOKEN` with a fallback to the default token:

```yaml
env:
  GH_TOKEN: ${{ secrets.PROJECT_TOKEN || secrets.GITHUB_TOKEN }}
```

The `|| secrets.GITHUB_TOKEN` fallback keeps forks and token-less environments
working (label-only sync). This pattern is asserted by
`src/atdd/coach/validators/test_auto_phase_workflow_exists.py` (#404).

## Verify

```bash
# With PROJECT_TOKEN exported:
atdd issue <N> --status GREEN
gh project item-list <project-number> --owner <owner> --format json \
  | jq '.items[] | select(.content.number==<N>) | .status'
# → "GREEN"
```

## Behaviour matrix

| `PROJECT_TOKEN` | Label swap | Projects v2 `ATDD Status` | Outcome |
|---|---|---|---|
| set, valid | ✅ | ✅ via `sync_status_field` (PAT) | board in lock-step (#882 closed) |
| set, denied | ✅ | ⚠️ skipped + warning | label-only; check PAT scopes |
| unset | ✅ | ⚠️ skipped + warning | label-only (local-dev default) |

## Security notes

- Scope the PAT to the **minimum** repos/permissions above; never grant `repo`
  classic scope.
- Rotate on the org's secret-rotation cadence; the token only needs Issues +
  Projects R/W.
- The token is read from the environment per-invocation and injected as
  `GH_TOKEN` for that one `gh` subprocess only — it is never written to disk by
  ATDD.
