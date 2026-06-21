# --- ATDD:BEGIN (managed by atdd, do not edit) ---

---
missions:
  orchestrate_atdd: "ATDD lifecycle: INIT → PLANNED → RED → GREEN → SMOKE → REFACTOR → COMPLETE (escapes: BLOCKED, OBSOLETE; per-phase agent ownership: src/atdd/coach/conventions/phase_machine.convention.yaml)"
  validate_phase_transitions: "Phase transitions and quality gates per conventions and schemas"
  required: true

# =============================================================================
# ATDD AGENT BOOTSTRAP (REQUIRED)
# =============================================================================
# 0. Enable plan mode if your agent supports it.
# 1. Run: atdd gate   (paste output; confirms loaded files + hash + constraints)
# 2. If files missing/unsynced: atdd sync → re-run atdd gate
# RULE: No gate = no guarantees.
# =============================================================================

# Canonical source pointers — agents read these directly, do not duplicate
# their contents back into this template. Enforced by validator
# `coach.template.no-duplicated-convention` (see #919 / Section C).
#
#   Audit surface       → `atdd validate --help`, `atdd repo --help`
#   Phase machine       → src/atdd/coach/conventions/phase_machine.convention.yaml
#                         (§4.5 of docs/coach-decomposition.md; INIT.pre_commit_gate
#                          carries the validate-planner command, replacing the prior
#                          `atdd_cycle.phases` block — see #888 / #925)
#   Archetype roles     → src/atdd/{planner,tester,coder,coach}/conventions/*.yaml
#   Manifest globs      → `atdd gate` (or filesystem listing under plan/, contracts/, telemetry/)
#   Test layout         → pytest collection (filesystem discovery)
#   Conventions registry→ `ls src/atdd/*/conventions/`
#   Infrastructure      → src/atdd/tester/conventions/contract.convention.yaml,
#                         src/atdd/coder/conventions/technology.convention.yaml
#   Architecture        → src/atdd/coder/conventions/backend.convention.yaml,
#                         src/atdd/coder/conventions/boundaries.convention.yaml

# Git Practices (operator-facing; not derivable from a convention YAML)
git:
  commits:
    co_authored: false
    format: "conventional commits (feat:, fix:, docs:, refactor:, test:)"
  commit_discipline:
    rule: "Commit after every completed sub-task. Never accumulate >5 modified files."
    on_main_detection: "STOP immediately. git stash → atdd branch <N> → cd worktree → git stash pop"
  branching:
    rule: "Every new branch MUST be created as a git worktree (flat sibling of main)"
    procedure:
      - "New branch: git worktree add ../<prefix>-<slug> -b <prefix>/<slug>"
      - "Work inside the worktree directory"
    prefixes: ["feat/", "fix/", "refactor/", "chore/", "docs/", "devops/"]
  worktree_config:
    rule: "Use --worktree flag for per-worktree git config; never run bare git config in a worktree"
    danger_keys: ["core.bare", "core.worktree", "core.hooksPath"]
  parallelization:
    see: "src/atdd/coach/conventions/coach.convention.yaml"
  post_commit_hook:
    purpose: "Blast-radius local validation after every commit"
    behavior: "Runs only validators in the commit's blast radius; never blocks; no-op when CI=true"
    emergency: "atdd emergency --reason '<reason>' → creates .atdd/EMERGENCY_BYPASS (5 min TTL)"
    operator_doc: "docs/operator-emergency-bypass.md"

# Release Gate (MANDATORY) — to move to release.convention.yaml per #916
release:
  mandatory: true
  # Version + tag + publish are FULLY AUTOMATED on merge. Do NOT bump the
  # version or create tags by hand — CI does it.
  change_class:
    PATCH: "bug fixes, docs, refactors, internal changes"
    MINOR: "new feature, new validator, new command, new convention (non-breaking)"
    MAJOR: "breaking API/CLI/schema/convention change or behavior removal"
  automation:
    bump_on_merge: "post-merge-lifecycle.yml bumps pyproject version on main from the branch prefix (feat/→MINOR, fix|chore|docs|refactor|devops/→PATCH, 'BREAKING CHANGE' or '<type>!:'→MAJOR), atomically with retries."
    tag_and_publish: "publish.yml tags the new version and publishes to PyPI once the bump lands on main."
  do_not:
    - "Do NOT edit pyproject.toml::version — a manual bump SKIPS the auto-bump (legacy path) and causes version-line merge conflicts with parallel PRs."
    - "Do NOT create or push git tags — CI tags on publish."

# Issue Tracking (operator-facing CLI + the prohibition list — gh issue create /
# gh pr create are forbidden because they bypass `atdd-issue` label-scoped
# validators; see #919 review note)
issues:
  source_of_truth: "GitHub Issues (atdd:<phase> labels) + local .atdd/manifest.yaml"
  convention: "src/atdd/coach/conventions/issue.convention.yaml"
  commands:
    new: "atdd issue <slug>"
    enter: "atdd issue <N>"
    update: "atdd issue <N> --status <STATUS>"
    pr: "atdd pr <N>"
  prohibited_commands:
    - "gh issue create    → use: atdd issue <slug>"
    - "gh pr create       → use: atdd pr <N>"
---

# Per-LLM convention context: Claude Code

## Rule-ID grammar

Canonical rule IDs use `<archetype>.<convention_short_name>.<rule_name>`.

Example: `coder.dead-code.reachability`.

## bind_rule contract

validators MUST call `bind_rule` at module-import time:

```python
_RULE = bind_rule("<canonical_id>")
```

The named rule MUST exist in a convention's `rules:` block. This is the bidirectional binding contract anchored by `SPEC-COACH-RULEID-0007`.

# Agent-specific: claude
# Claude-specific additions
# This content is appended to the base CONDUCTOR.md when syncing to CLAUDE.md

# --- ATDD:END ---
