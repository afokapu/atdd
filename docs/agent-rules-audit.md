# Agent Rules Audit

**Purpose**: Classify every `~/.claude/projects/.../memory/` entry as `enforceable / partial / soft-only`
and record the in-repo enforcement site when applicable.

**Source of truth after this audit**: `.atdd/agent-rules.yaml` (portable, version-controlled).

**Generated**: 2026-05-19 as part of issue #657 — Agent Behavior Rules Need Repo Enforcement.

---

## Classification Key

| Label | Meaning |
|-------|---------|
| `enforceable` | Mechanically checked by a validator, hook, or CLI guard. Violation = automated failure. |
| `partial` | Checked at canonical CLI entry point but cannot cover all surfaces (e.g. scripts that call gh directly). |
| `soft-only` | Requires human judgment; no automated check is possible. Stays in memory. |

---

## Audit Results

| Memory Entry | Classification | Enforcement Site | Repo Artifact |
|---|---|---|---|
| Never pass `--dangerously-skip-permissions` | **enforceable** | `SpawnPermissionViolation` raised in `cmd_spawn()` before multiplexer dispatch | `src/atdd/coach/commands/spawn.py` (E014) |
| Search before filing issues (`atdd issue <slug>`) | **enforceable** | `dup_check_before_file()` called in `IssueManager.new()`; abort on matches unless `--no-dup-check` | `src/atdd/coach/commands/issue.py` (E013) |
| Commit after every sub-task; never accumulate >5 modified files | **partial** | Advisory warning in claude-pre-tool-use.sh hook when >5 files modified since last commit | `.claude/hooks/pre_tool_use.sh` (template: `src/atdd/coach/templates/hooks/claude-pre-tool-use.sh`) |
| Use `--worktree` flag for per-worktree git config; never `git config` bare keys in a worktree | **enforceable** | pre-push hook Layer 1 guard detects `core.bare` contamination (Y002/Y003) | `src/atdd/coach/templates/hooks/pre-push` |
| All issue and PR operations via `atdd` CLI, not direct `gh` commands | **partial** | Forbidden-commands classifier catches `gh issue create` and `gh pr create` via pre-tool-use hook | `src/atdd/coach/validators/test_forbidden_commands.py` (E006) |
| Do NOT commit anything under `.atdd/runtime/` | **enforceable** | `coach.pr.runtime-artifacts-blocked` validator in `atdd validate coach`; `.atdd/runtime/` fully gitignored | `src/atdd/coach/validators/` (E009) |
| Do NOT add `Co-Authored-By: Claude <noreply@anthropic.com>` to commits | **soft-only** | Documented in CLAUDE.md `git.commits.co_authored=false`; no automated check | CLAUDE.md |
| Run `atdd gate` before starting work; confirm loaded files and hash | **soft-only** | Protocol documented in CLAUDE.md ATDD Bootstrap Protocol; gate output is informational | CLAUDE.md |
| Prefer terse responses; no trailing summaries | **soft-only** | User tone preference; no automated check possible | User memory only |
| Y002: always use `ATDD_SKIP_POSTCOMMIT=1` when committing; coach validators create commits in active worktree | **partial** | ATDD post-commit hook exits early when `ATDD_SKIP_POSTCOMMIT=1`; requires operator discipline | `src/atdd/coach/templates/hooks/post-commit` |
| Validate-coach `--skip-api` skips the repo-wide pre-smoke-close PR gate | **partial** | Known gap; check CI `validate-coach`; documented in memory | Coach validator gap — see issue backlog |

---

## Ruleset Promoted to `.atdd/agent-rules.yaml`

The following rules have been lifted into `.atdd/agent-rules.yaml` (the portable enforcement subset):

- AR-001: Never pass `--dangerously-skip-permissions` (enforceable — E014)
- AR-002: Search before filing issues (enforceable — E013)
- AR-003: Micro-commit discipline (partial — advisory hook)
- AR-004: `--worktree` git config guard (enforceable — Y002/Y003)
- AR-005: Use `atdd` CLI, not direct `gh` commands (partial — E006)
- AR-006: Do not commit `.atdd/runtime/` (enforceable — E009)
- AR-007: No `Co-Authored-By: Claude` (soft-only — documented)
- AR-008: Run `atdd gate` before starting (soft-only — documented)

---

## Rules Kept in Memory Only

The following rules are `soft-only` and **not** lifted to the repo because no automated check is possible:

- User tone preferences (terse responses, no trailing summaries)
- Session-level collaboration preferences
- LLM-specific formatting guidelines

---

## Validation

The in-repo ruleset is validated by:

```
atdd validate coach   # confirms E013/E014/E015 test coverage
atdd gate             # outputs Agent Behavioral Rules section from .atdd/agent-rules.yaml
```
