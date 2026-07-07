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
  # #1172 (SHIPPED, source-of-truth + build projection): the release version
  # lives in the State Store (singleton `release` object, migration v2) and is
  # projected at build time by the in-tree backend — `pyproject.toml` is
  # `dynamic = ["version"]` with NO `version =` line to hand-edit or conflict on.
  # The GH006 direct-push auto-bump (post-merge-lifecycle.yml) is RETIRED.
  # FOLLOW-UP (#1172 step 5): the version *decision* is made in core — a bump
  # emits a PROVIDER-NEUTRAL `version_decided` outbox message ({version,
  # change_class}); core names no tag/publish/PyPI. The GitHub release-worker
  # that drains that neutral outbox to tag + publish does not exist
  # yet, so the on-merge publish is operator-coordinated for now (publish.yml
  # skips the `0.0.0+local` fallback rather than publishing a bogus version).
  # Do NOT re-introduce the GH006 direct-push bump or a hand-edited version line.
  change_class:
    PATCH: "bug fixes, docs, refactors, internal changes"
    MINOR: "new feature, new validator, new command, new convention (non-breaking)"
    MAJOR: "breaking API/CLI/schema/convention change or behavior removal"
  workflow:
    - "Bump the State Store version by change class: `atdd state version bump --class PATCH|MINOR|MAJOR`"
    - "The build backend projects that version automatically — no pyproject edit, no version-bump commit"
    - "Merge PR; publication (git tag + PyPI) is handled by the release extension draining core's neutral version_decided outbox (interim: operator-coordinated)"
  note: "Version source-of-truth + build projection shipped in #1172; CI publish automation (release-worker outbox drain) is the remaining follow-up. Do not re-adopt the GH006 auto-bump or hand-edited pyproject version."

# Issue Tracking (operator-facing CLI + the prohibition list — gh issue create /
# gh pr create are forbidden because they bypass `atdd-issue` label-scoped
# validators; see #919 review note)
issues:
  source_of_truth: "GitHub Issues (atdd:<phase> labels) + local .atdd/manifest.yaml"
  convention: "src/atdd/coach/conventions/issue.convention.yaml"
  commands:
    new: "atdd author issue --title <title> --slug <slug>"   # store-first canonical create (#1272)
    enter: "atdd issue <N>"
    update: "atdd issue <N> --status <STATUS>"
    pr: "atdd pr <N>"
  deprecated_commands:
    # #1349: the create-by-slug alias still works but warns on stderr and
    # points to the canonical `atdd author issue` (store-first, fail-loud).
    - "atdd issue <slug>  → use: atdd author issue --title <title> --slug <slug>"
    - "atdd new <slug>    → use: atdd author issue --title <title> --slug <slug>"
  prohibited_commands:
    - "gh issue create    → use: atdd author issue --title <title> --slug <slug>"
    - "gh pr create       → use: atdd pr <N>"
---
