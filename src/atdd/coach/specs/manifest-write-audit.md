# Manifest-Write Audit

Issue: #344
Convention: `src/atdd/coach/conventions/issue.convention.yaml` → `manifest_write_discipline`
Helper: `src/atdd/coach/utils/git.py` → `git_commit_manifest_update`
Validator: `src/atdd/coach/validators/test_manifest_write_discipline.py`

## Purpose

Track every CLI verb that mutates `.atdd/manifest.yaml` and the call site
that funnels its write through `git_commit_manifest_update`. The
discipline closes the worktree-visibility gap reproduced in issue #344:
a manifest write on main that is never committed is invisible to any
worktree branched from main HEAD.

## Audited verbs

| Verb                          | Method (issue.py)         | Save call site         | Commit call site         | Commit message                                                          |
|-------------------------------|---------------------------|------------------------|--------------------------|-------------------------------------------------------------------------|
| `atdd issue <slug>`           | `_new_github_issue`       | `self._save_manifest`  | `self._commit_manifest_change` | `chore(coach): register issue #{N} in manifest`                       |
| `atdd update --status <S>`    | `_update_manifest_status` | `self._save_manifest`  | `self._commit_manifest_change` | `chore(coach): mirror issue #{N} status → {S} in manifest`            |
| `atdd archive <N>`            | `_archive_github`         | `self._save_manifest`  | `self._commit_manifest_change` | `chore(coach): archive issue #{N} in manifest`                        |

## Verbs deliberately excluded

| Verb                  | Reason                                                                                                  |
|-----------------------|---------------------------------------------------------------------------------------------------------|
| `atdd close-wmbt`     | Closes a GitHub sub-issue; does not touch `.atdd/manifest.yaml`.                                        |
| `atdd list` / `atdd issue open` | Read-only — must not mutate the manifest.                                                     |
| `atdd issue <N>`      | Reads manifest to enter context; does not write.                                                        |
| `atdd issue <N> --check` | Reads issue body; does not write.                                                                   |
| `atdd branch <N>`     | Creates a worktree; does not write `.atdd/manifest.yaml`. Workspace file is regenerated separately.     |
| `atdd init`           | Bootstraps `.atdd/`; the initial manifest commit is part of `atdd init`'s normal initialization flow.   |

## How the validator stays honest

`test_manifest_write_discipline.py::test_every_save_manifest_call_site_has_commit_followup`
walks the AST of `issue.py`, collects every `self._save_manifest(...)`
call (skipping the method definition itself), and asserts each
enclosing method also contains at least one
`self._commit_manifest_change(...)` call. A new manifest-mutating verb
that forgets the follow-up will fail the validator in CI.

## Out of scope

- Auto-pushing the commit to origin (Decision #1 in #344).
- `atdd sync` writing to `CLAUDE.md` (Decision #4 — file a separate
  parent issue if the same pattern emerges for other tracked files).
- `.atdd/config.yaml` writes — covered by the CLI-config-mutation issue,
  whose remit is to *prevent* such writes, not commit them.
