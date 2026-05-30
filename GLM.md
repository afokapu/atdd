# --- ATDD:BEGIN (managed by atdd, do not edit) ---

---
missions:
  orchestrate_atdd: "ATDD lifecycle (planner → tester RED → coder GREEN → tester SMOKE → coder REFACTOR)"
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

manifest:
  - trains: "plan/_trains.yaml"
  - wagons: "plan/_wagons.yaml"
  - features: "plan/*/_features.yaml"
  - wmbt: "plan/*/*.yaml"
  - artifacts: "contracts/_artifacts.yaml"
  - contracts: "contracts/_contracts.yaml"
  - telemetry: "telemetry/_telemetry.yaml"
  - taxonomy: "telemetry/_taxonomy.yaml"

tests:
  - frontend: "web/tests"
  - supabase: "supabase/functions/*/*/tests/"
  - python: "python/*/*/tests"
  - packages: "packages/*/tests"
  - e2e: "e2e"

# Audits & Validation
audits:
  cli: "atdd"
  commands:
    validate_all: "atdd validate"
    validate_planner: "atdd validate planner"
    validate_tester: "atdd validate tester"
    validate_coder: "atdd validate coder"
    validate_coach: "atdd validate coach"
    inventory: "atdd inventory"
    status: "atdd status"
  workflow:
    after_planner: "atdd validate planner --local --skip-api  # BEFORE committing PLANNED"
    after_tester: "atdd validate tester"
    after_coder: "atdd validate coder       # Before transitioning to SMOKE"
    full_suite: "atdd validate"
  audit_scope:
    planner: "src/atdd/planner/validators/*.py"
    tester: "src/atdd/tester/validators/*.py"
    coder: "src/atdd/coder/validators/*.py"
    coach: "src/atdd/coach/validators/*.py"
  repo_diagnostics:
    validate: "atdd repo validate"
    broken: "atdd repo broken"
    orphans: "atdd repo orphans"
    resolve: "atdd repo resolve <urn>"
    rules: "atdd repo rules"

# ATDD Lifecycle
atdd_cycle:
  phases:
    - name: INIT
      agent: planner
      conventions: "src/atdd/planner/conventions/*.yaml"
      transitions: "INIT → PLANNED"
      pre_commit_gate: "atdd validate planner --local --skip-api (BEFORE committing PLANNED)"
    - name: PLANNED
      agent: tester
      conventions: "src/atdd/tester/conventions/*.yaml"
      transitions: "PLANNED → RED"
    - name: RED
      agent: coder
      task: "Make tests GREEN"
      conventions: "src/atdd/coder/conventions/green.convention.yaml"
      transitions: "RED → GREEN"
    - name: GREEN
      agent: tester
      task: "Verify against real infrastructure (SMOKE tests)"
      conventions: "src/atdd/tester/conventions/smoke.convention.yaml"
      transitions: "GREEN → SMOKE"
    - name: SMOKE
      agent: coder
      task: "REFACTOR to 4-layer architecture"
      conventions: "src/atdd/coder/conventions/refactor.convention.yaml"
      transitions: "SMOKE → REFACTOR"
    - name: REFACTOR
      status: complete
  execution:
    assess_first: "MUST assess current state before any action"
    audit_enforcement: "All phase audits MUST pass before transition"

# Infrastructure
infrastructure:
  contract_driven: true
  persistence:
    default: "Supabase JSONB"
  conventions:
    contracts: "src/atdd/tester/conventions/contract.convention.yaml"
    technology: "src/atdd/coder/conventions/technology.convention.yaml"

# Architecture
architecture:
  conventions:
    layers: "src/atdd/coder/conventions/backend.convention.yaml"
    boundaries: "src/atdd/coder/conventions/boundaries.convention.yaml"
  principles:
    - "Domain layer NEVER imports from other layers"
    - "Dependencies point inward only (integration → application → domain)"
    - "Test first (RED → GREEN → SMOKE → REFACTOR)"
    - "Wagons communicate via contracts only"

# Testing
testing:
  conventions:
    red: "src/atdd/tester/conventions/red.convention.yaml"
    filename: "src/atdd/tester/conventions/filename.convention.yaml"
    contract: "src/atdd/tester/conventions/contract.convention.yaml"
    smoke: "src/atdd/tester/conventions/smoke.convention.yaml"
  principles:
    - "No ad-hoc tests — follow conventions"
    - "Test path determines implementation runtime"
    - "Tests co-located with src"

# Git Practices
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
    see: "src/atdd/coach/conventions/orchestration.convention.yaml"
  post_commit_hook:
    purpose: "Blast-radius local validation after every commit"
    behavior: "Runs only validators in the commit's blast radius; never blocks; no-op when CI=true"
    emergency: "atdd emergency --reason '<reason>' → creates .atdd/EMERGENCY_BYPASS (5 min TTL)"
    operator_doc: "docs/operator-emergency-bypass.md"

# Release Gate (MANDATORY)
release:
  mandatory: true
  change_class:
    PATCH: "bug fixes, docs, refactors, internal changes"
    MINOR: "new feature, new validator, new command, new convention (non-breaking)"
    MAJOR: "breaking API/CLI/schema/convention change or behavior removal"
  workflow:
    - "Bump version in version file"
    - "Commit: 'Bump version to {version}'"
    - "Merge PR; then: git tag v{version} on merge commit + git push origin --tags"

# Agent Coordination
agents:
  planner:
    role: "Create wagons with acceptance criteria"
    conventions: "src/atdd/planner/conventions/*.yaml"
  tester:
    role: "Generate RED tests from acceptance criteria"
    conventions: "src/atdd/tester/conventions/*.yaml"
  coder:
    role: "Implement GREEN code, then REFACTOR to clean architecture"
    conventions: "src/atdd/coder/conventions/*.yaml"

# Issue Tracking
issues:
  source_of_truth: "GitHub Issues + Project v2 custom fields"
  convention: "src/atdd/coach/conventions/issue.convention.yaml"
  commands:
    new: "atdd issue <slug>"
    enter: "atdd issue <N>"
    update: "atdd issue <N> --status <STATUS>"
    pr: "atdd pr <N>"
  prohibited_commands:
    - "gh issue create    → use: atdd issue <slug>"
    - "gh pr create       → use: atdd pr <N>"

# Phase transitions (state machine) are defined canonically in
# src/atdd/coach/conventions/phase_machine.convention.yaml — the single source of
# truth (docs/coach-decomposition.md §4.5). The duplicate transition table that
# used to live here was removed in #888. To change a phase, edit the convention
# YAML; do not re-add a transition table to this managed block.
# Status command: atdd issue <N> --status <STATUS>

# Conventions Registry
conventions:
  planner:
    - "wagon.convention.yaml"
    - "acceptance.convention.yaml"
    - "wmbt.convention.yaml"
  tester:
    - "red.convention.yaml"
    - "filename.convention.yaml"
    - "contract.convention.yaml"
    - "smoke.convention.yaml"
  coder:
    - "green.convention.yaml"
    - "refactor.convention.yaml"
    - "boundaries.convention.yaml"
    - "backend.convention.yaml"
  coach:
    - "issue.convention.yaml"
---

# Agent-specific: glm
# GLM-specific additions
# This content is appended to the base ATDD.md when syncing to GLM.md

# --- ATDD:END ---
