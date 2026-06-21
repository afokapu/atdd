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
  # INTERIM (see #1172): bump the version manually for now. The bump-on-merge
  # automation (post-merge-lifecycle.yml) is currently NON-OPERATIONAL — its
  # direct push to main is rejected by branch protection (GH006), so it has
  # never successfully bumped. Until version handling moves to the State Store
  # (#1168 / #1172), manual bumping is the working mechanism.
  change_class:
    PATCH: "bug fixes, docs, refactors, internal changes"
    MINOR: "new feature, new validator, new command, new convention (non-breaking)"
    MAJOR: "breaking API/CLI/schema/convention change or behavior removal"
  workflow:
    - "Bump version in pyproject.toml based on branch prefix + change class"
    - "Commit: 'Bump version to {version}'"
    - "Merge PR; publish.yml tags + publishes from the version on main"
  note: "Durable fix tracked in #1172 (State Store owns version source-of-truth); do not re-adopt the auto-bump until it is operational."

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
