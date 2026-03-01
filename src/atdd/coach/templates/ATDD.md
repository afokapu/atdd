---
missions:
  orchestrate_atdd: "ATDD lifecycle (planner → tester RED → coder GREEN → coder REFACTOR)"
  validate_phase_transitions: "Phase transitions and quality gates per conventions and schemas"
  required: true

# =============================================================================
# ATDD AGENT BOOTSTRAP PROTOCOL (REQUIRED)
# =============================================================================
#
# Problem: Agents often skip instruction files and work without ATDD context.
# Solution: Coercive context - inject rules via mandatory tool output.
#
# PROTOCOL:
# ---------
# 0. TOOL GATE (MANDATORY)
#    If your agent supports plan mode (Claude Code, etc.), enable it NOW.
#    This is a tool capability gate, NOT the ATDD Planner phase.
#    If unavailable, state: "Plan mode unavailable" and proceed.
#
# 1. Run this command FIRST:
#
#    atdd gate
#
# 2. Paste the output and confirm:
#    - Which file(s) were loaded
#    - The reported hash
#    - The key ATDD constraints
#
# 3. If output shows missing/unsynced files, run:
#
#    atdd sync
#
#    Then re-run: atdd gate
#
# WHY THIS WORKS:
# - Gate output is mandatory tool output - agent can't ignore it
# - Proves which ATDD files were actually loaded
# - Forces consistency across all agents
#
# FAILURE MODE:
# - If agent skips the gate: STOP and run atdd gate again
# - Don't proceed until gate confirmation is posted
#
# RULE: If ATDD rules matter, start with `atdd gate`. No gate = no guarantees.
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

code:
  - frontend: "web/src"
  - supabase: "supabase/functions"
  - python: "python"
  - packages: "packages"
  - migrations: "supabase/migrations"

# Dev Servers
dev_servers:
  backend:
    command: "cd python && python3 app.py"
    url: "http://127.0.0.1:8000"
    swagger: "http://127.0.0.1:8000/docs"
  frontend:
    command: "cd web && npm run dev"
    url: "http://localhost:5173"
  supabase:
    mode: "remote only"
    cli: "supabase CLI for migrations, db commands (never run `supabase start`)"
    note: "All Supabase services accessed via remote project, not local Docker"

# Audits & Validation (Give context, pinpoint issues, validate compliance)
audits:
  cli: "atdd"
  purpose: "Validators that check ATDD artifacts against conventions"

  commands:
    validate_all: "atdd validate"
    validate_planner: "atdd validate planner"
    validate_tester: "atdd validate tester"
    validate_coder: "atdd validate coder"
    validate_coach: "atdd validate coach"
    quick_check: "atdd validate --quick"
    with_coverage: "atdd validate --coverage"
    with_html: "atdd validate --html"
    inventory: "atdd inventory"
    status: "atdd status"

  workflow:
    after_planner: "atdd validate planner   # Before transitioning to RED"
    after_tester: "atdd validate tester     # Before transitioning to GREEN"
    after_coder: "atdd validate coder       # Before transitioning to REFACTOR"
    after_coach: "atdd validate coach       # Train + body section enforcement"
    full_suite: "atdd validate              # All phases (CI runs this)"

  audit_scope:
    planner: "src/atdd/planner/validators/*.py (wagons, trains, URNs, cross-refs, WMBT)"
    tester: "src/atdd/tester/validators/*.py (test naming, contracts, telemetry, coverage)"
    coder: "src/atdd/coder/validators/*.py (architecture, boundaries, layers, quality)"
    coach: "src/atdd/coach/validators/*.py (registry, traceability, contract consumers)"

  usage:
    pinpoint_issues: "Audits fail with detailed error messages showing violations"
    give_context: "Error messages reference specific conventions and schemas"
    validate_compliance: "All audits must pass before phase transition"

# ATDD Lifecycle (Detailed steps in agent conventions)
atdd_cycle:
  phases:
    - name: INIT
      agent: planner
      conventions: "src/atdd/planner/conventions/*.yaml"
      audits: "src/atdd/planner/validators/*.py"
      deliverables: ["train_path", "wagon_path", "wmbt_path", "feature_path"]
      transitions: "INIT → PLANNED"

    - name: PLANNED
      agent: tester
      conventions: "src/atdd/tester/conventions/*.yaml"
      audits: "src/atdd/tester/validators/*.py"
      deliverables: ["test_paths", "contract_paths", "telemetry_paths"]
      transitions: "PLANNED → RED"

    - name: RED
      agent: coder
      task: "Make tests GREEN"
      conventions: "src/atdd/coder/conventions/green.convention.yaml"
      audits: "src/atdd/coder/validators/test_green_*.py"
      deliverables: ["code_paths", "tests_passing"]
      transitions: "RED → GREEN"

    - name: GREEN
      agent: coder
      task: "REFACTOR to 4-layer architecture"
      conventions: "src/atdd/coder/conventions/refactor.convention.yaml"
      audits: "src/atdd/coder/validators/test_architecture_*.py"
      deliverables: ["refactor_paths"]
      transitions: "GREEN → REFACTOR"

    - name: REFACTOR
      status: complete
      audits: "src/atdd/coder/validators/test_quality_metrics.py"

  execution:
    assess_first: "MUST assess current state before any action"
    phase_transitions: "Explicit transitions with quality gates"
    agent_handoff: "Dynamic handoff based on phase"
    audit_enforcement: "All phase audits MUST pass before transition"

# Infrastructure
infrastructure:
  contract_driven: true  # All interfaces defined via JSON Schema contracts
  persistence:
    default: "Supabase JSONB"  # Schema evolution without migrations
    exceptions: "Relational for complex queries, indexes"
  conventions:
    contracts: "src/atdd/tester/conventions/contract.convention.yaml"
    technology: "src/atdd/coder/conventions/technology.convention.yaml"

# Architecture (Detailed rules in conventions)
architecture:
  conventions:
    layers: "src/atdd/coder/conventions/backend.convention.yaml"
    boundaries: "src/atdd/coder/conventions/boundaries.convention.yaml"
    composition: "src/atdd/coder/conventions/green.convention.yaml"
    design_system: "src/atdd/coder/conventions/design.convention.yaml"

  principles:
    - "Domain layer NEVER imports from other layers"
    - "Dependencies point inward only (integration → application → domain)"
    - "Test first (RED → GREEN → REFACTOR)"
    - "Wagons communicate via contracts only"
    - "composition.py/wagon.py are composition roots (survive refactoring)"

# Testing (Detailed rules in conventions)
testing:
  conventions:
    red: "src/atdd/tester/conventions/red.convention.yaml"
    filename: "src/atdd/tester/conventions/filename.convention.yaml"
    contract: "src/atdd/tester/conventions/contract.convention.yaml"
    artifact: "src/atdd/tester/conventions/artifact.convention.yaml"

  principles:
    - "No ad-hoc tests - follow conventions"
    - "Code must be inherently auditable with verbose logs"
    - "State-of-the-art testing strategies only"
    - "Test path determines implementation runtime"
    - "Tests co-located with src (python/*/tests/, supabase/*/tests/)"

# Git Practices
git:
  commits:
    co_authored: false  # DO NOT add "Co-Authored-By: Claude <noreply@anthropic.com>"
    format: "conventional commits (feat:, fix:, docs:, refactor:, test:)"
    atomic: "One commit per phase transition when meaningful"

  branching:
    rule: "Every new branch MUST be created as a git worktree (flat sibling of main)"
    layout: |
      project/
      ├── main/                      # primary checkout
      ├── feat-traceability-gates/   # branch: feat/traceability-gates
      ├── fix-typo/                  # branch: fix/typo
      └── ...
    procedure:
      - "Pick prefix from allowed list"
      - "New branch: git worktree add ../<prefix>-<slug> -b <prefix>/<slug>"
      - "Existing remote: git worktree add ../<prefix>-<slug> origin/<prefix>/<slug>"
      - "Work inside the worktree directory"
      - "Clean up after merge: git worktree remove ../<prefix>-<slug>"
    prefixes: ["feat/", "fix/", "refactor/", "chore/", "docs/", "devops/"]
    example: "git worktree add ../feat-traceability-gates -b feat/traceability-gates"

  workflow:
    branch_strategy: "worktree per branch from main"
    phase_commits:
      - "PLANNED: commit wagon + acceptance criteria"
      - "RED: commit failing tests"
      - "GREEN: commit passing implementation"
      - "REFACTOR: commit clean architecture"

# Release Gate (MANDATORY - session completion)
# Every session MUST end with version bump + tag
release:
  mandatory: true

  rules:
    - "Version file is required (configured in .atdd/config.yaml)"
    - "Tag must match version exactly: v{version}"
    - "Tag must be on HEAD"
    - "No tag without version bump"
    - "No version bump without tag"
    - "Every repo MUST have versioning"

  change_class:
    PATCH: "bug fixes, docs, refactors, internal changes"
    MINOR: "new feature, new validator, new command, new convention (non-breaking)"
    MAJOR: "breaking API/CLI/schema/convention change or behavior removal"

  workflow:
    - "Determine change class"
    - "Bump version in version file"
    - "Commit: 'Bump version to {version}'"
    - "Create tag: git tag v{version}"
    - "Push with tags: git push origin {branch} --tags"
    - "Record in Session Log: 'Released: v{version}'"

  # Config (required in .atdd/config.yaml):
  # release:
  #   version_file: "pyproject.toml"  # or package.json, VERSION, etc.
  #   tag_prefix: "v"
  # Validator: atdd validate coach enforces version file + tag on HEAD

# Agent Coordination (Detailed in action files)
agents:
  planner:
    role: "Create wagons with acceptance criteria"
    conventions: "src/atdd/planner/conventions/*.yaml"
    schemas: "src/atdd/planner/schemas/*.json"
    audits: "src/atdd/planner/validators/*.py"

  tester:
    role: "Generate RED tests from acceptance criteria"
    conventions: "src/atdd/tester/conventions/*.yaml"
    schemas: "src/atdd/tester/schemas/*.json"
    audits: "src/atdd/tester/validators/*.py"

  coder:
    role: "Implement GREEN code, then REFACTOR to clean architecture"
    conventions: "src/atdd/coder/conventions/*.yaml"
    schemas: "src/atdd/coder/schemas/*.json"
    audits: "src/atdd/coder/validators/*.py"

# Issue Tracking (GitHub Issues + Project v2)
# Source of truth: GitHub Issues with Project v2 custom fields
# Legacy local session files (atdd-sessions/) are historical only
issues:
  source_of_truth: "GitHub Issues + Project v2 custom fields"
  config_dir: ".atdd/"
  manifest: ".atdd/manifest.yaml"
  convention: "src/atdd/coach/conventions/issue.convention.yaml"
  template: "src/atdd/coach/templates/PARENT-ISSUE-TEMPLATE.md"

  commands:
    init: "atdd init                              # Bootstrap .atdd/ + GitHub infrastructure"
    new: "atdd new <slug>                          # Create parent issue + WMBT sub-issues"
    new_with_opts: "atdd new <slug> --archetypes be,contracts --train <id>"
    list: "atdd list                               # List all issues (from GitHub)"
    update: "atdd update <N> --status <STATUS>     # Update Project fields + swap labels"
    close_wmbt: "atdd close-wmbt <N> <WMBT_ID>     # Close a WMBT sub-issue"
    archive: "atdd archive <N>                     # Close parent + all sub-issues"
    validate: "atdd validate coach                 # Validate Project fields + sub-issue state"

  archetypes:
    db: "Supabase PostgreSQL + JSONB"
    be: "Python FastAPI 4-layer"
    fe: "TypeScript/Preact 4-layer"
    contracts: "JSON Schema contracts"
    wmbt: "What Must Be True criteria"
    wagon: "Bounded context module"
    train: "Journey orchestration (linear trains)"
    telemetry: "Observability artifacts"
    migrations: "Database schema evolution"

  atdd_phases:
    RED: "Write failing tests from acceptances"
    GREEN: "Implement minimal code to pass tests"
    REFACTOR: "Clean architecture, 4-layer compliance"

# State Machine (issue lifecycle transitions)
state_machine:
  transitions:
    INIT: [PLANNED, BLOCKED, OBSOLETE]
    PLANNED: [RED, BLOCKED, OBSOLETE]
    RED: [GREEN, BLOCKED, OBSOLETE]
    GREEN: [REFACTOR, BLOCKED, OBSOLETE]
    REFACTOR: [COMPLETE, BLOCKED, OBSOLETE]
    BLOCKED: [INIT, PLANNED, RED, GREEN, REFACTOR, OBSOLETE]
    COMPLETE: []
    OBSOLETE: []
  command: "atdd update <N> --status <STATUS>"
  rules:
    - "Train field required past PLANNED (enforced by CLI + validator)"
    - "Labels swapped automatically (atdd:RED → atdd:GREEN)"

# Quality Gates (Detailed in action files)
validations:
  phase_transitions:
    INIT→PLANNED: "planner delivers wagon with acceptance criteria"
    PLANNED→RED: "tester delivers RED tests"
    RED→GREEN: "coder delivers passing tests"
    GREEN→REFACTOR: "coder delivers clean architecture"

  code_quality:
    - "Domain layer has no external dependencies"
    - "All tests pass before REFACTOR"
    - "Architecture follows 4-layer pattern"
    - "Wagons isolated via qualified imports"
    - "Composition roots stable during refactor"

# Conventions Registry
conventions:
  planner:
    - "wagon.convention.yaml: wagon structure & URN naming"
    - "acceptance.convention.yaml: acceptance criteria & harness types"
    - "wmbt.convention.yaml: WMBT structure"
    - "feature.convention.yaml: feature structure"
    - "artifact.convention.yaml: artifact contracts"

  tester:
    - "red.convention.yaml: RED test generation (neurosymbolic)"
    - "filename.convention.yaml: URN-based test naming"
    - "contract.convention.yaml: schema validation"
    - "artifact.convention.yaml: artifact validation"

  coder:
    - "green.convention.yaml: GREEN phase (make tests pass)"
    - "refactor.convention.yaml: REFACTOR phase (clean architecture)"
    - "boundaries.convention.yaml: wagon isolation & qualified imports"
    - "backend.convention.yaml: 4-layer backend architecture"
    - "frontend.convention.yaml: 4-layer frontend architecture"
    - "design.convention.yaml: design system hierarchy"

  coach:
    - "issue.convention.yaml: Session planning structure & archetypes"
---
