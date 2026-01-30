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
    command: "cd python && python3 game.py"
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
  purpose: "Meta-tests that validate ATDD artifacts against conventions"

  commands:
    inventory: "atdd --inventory"
    status: "atdd --status"
    quick_check: "atdd --quick"
    validate_all: "atdd --test all"
    validate_planner: "atdd --test planner"
    validate_tester: "atdd --test tester"
    validate_coder: "atdd --test coder"
    with_coverage: "atdd --test all --coverage"
    with_html: "atdd --test all --html"

  workflow:
    before_init: "Run planner audits to validate plan structure"
    after_init: "Validate wagon URNs, cross-refs, uniqueness"
    before_planned: "Run tester audits to validate test prerequisites"
    after_planned: "Validate test naming, contracts, coverage"
    before_red: "Validate layer structure expectations"
    after_red: "Validate tests are RED and properly structured"
    before_green: "Run coder audits for architecture readiness"
    after_green: "Validate layer dependencies, boundaries"
    after_refactor: "Validate architecture compliance, quality metrics"
    continuous: "CI runs 'atdd --test all' on every commit"

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

  workflow:
    branch_strategy: "feature branches from main/mechanic"
    phase_commits:
      - "PLANNED: commit wagon + acceptance criteria"
      - "RED: commit failing tests"
      - "GREEN: commit passing implementation"
      - "REFACTOR: commit clean architecture"

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

# Session Planning (Design before implementation)
# Note: atdd-sessions/ is created in the consuming repo via `atdd init`
sessions:
  # Consumer repo paths (created via `atdd init`)
  directory: "atdd-sessions/"
  archive: "atdd-sessions/archive/"
  config_dir: ".atdd/"
  manifest: ".atdd/manifest.yaml"
  # Package resources
  template: "src/atdd/coach/templates/SESSION-TEMPLATE.md"
  convention: "src/atdd/coach/conventions/session.convention.yaml"

  commands:
    init: "atdd init                    # Initialize atdd-sessions/ and .atdd/"
    new: "atdd session new my-feature   # Create SESSION-NN-my-feature.md"
    list: "atdd session list            # List all sessions from manifest"
    archive: "atdd session archive 01   # Move session to archive/"

  workflow:
    init: "Run 'atdd init' to create atdd-sessions/ directory structure"
    create: "Run 'atdd session new <slug>' to create new session from template"
    fill: "Fill ALL sections - write 'N/A' if not applicable, never omit"
    track: "Update Progress Tracker and Session Log after each work item"
    validate: "python3 -m pytest src/atdd/coach/validators/test_session_*.py -v"

  archetypes:
    db: "Supabase PostgreSQL + JSONB"
    be: "Python FastAPI 4-layer"
    fe: "TypeScript/Preact 4-layer"
    contracts: "JSON Schema contracts"
    wmbt: "What Must Be True criteria"
    wagon: "Bounded context module"
    train: "Release orchestration"
    telemetry: "Observability artifacts"
    migrations: "Database schema evolution"

  atdd_phases:
    RED: "Write failing tests from acceptances"
    GREEN: "Implement minimal code to pass tests"
    REFACTOR: "Clean architecture, 4-layer compliance"

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
    - "session.convention.yaml: Session planning structure & archetypes"
---
