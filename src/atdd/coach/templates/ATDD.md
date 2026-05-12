---
missions:
  orchestrate_atdd: "ATDD lifecycle (planner → tester RED → coder GREEN → tester SMOKE → coder REFACTOR)"
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
  - toolkit: "src/atdd"           # toolkit-self root, opt-in per repo (see code-roots.convention.yaml)

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
    with_coverage: "atdd validate --coverage"
    with_html: "atdd validate --html"
    inventory: "atdd inventory"
    status: "atdd status"

  workflow:
    after_planner: "atdd validate planner   # Before transitioning to RED"
    after_tester: "atdd validate tester     # Before transitioning to GREEN"
    after_coder: "atdd validate coder       # Before transitioning to SMOKE"
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

  # Repo diagnostic commands (local, no network — run before committing)
  repo_diagnostics:
    validate: "atdd repo validate          # URN traceability (0 errors = clean)"
    broken: "atdd repo broken             # grammar violations in plan/ URNs"
    orphans: "atdd repo orphans            # declared URNs with no parent refs"
    resolve: "atdd repo resolve <urn>      # trace a single URN to its artifact"
    rules: "atdd repo rules              # repo rules derived from WMBT accs"
    wmbt_rules: "atdd repo wmbt-rules <urn>  # rules for a specific WMBT"
    rule_show: "atdd rules show <rule-id>  # resolve a rule-ID via bind_rule()"
    rule_grep: "atdd rules grep <pattern>  # search rule descriptions and aliases"
  repo_diagnostics_note: >
    Call these any time you author or edit plan/ YAML files (wagons, WMBTs,
    acceptances). They run locally with no network and catch URN grammar drift
    and broken references before the validator suite sees them.

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
      agent: tester
      task: "Verify against real infrastructure (SMOKE tests)"
      conventions: "src/atdd/tester/conventions/smoke.convention.yaml"
      audits: "src/atdd/tester/validators/test_smoke_*.py"
      deliverables: ["smoke_test_paths"]
      transitions: "GREEN → SMOKE"

    - name: SMOKE
      agent: coder
      task: "REFACTOR to 4-layer architecture"
      conventions: "src/atdd/coder/conventions/refactor.convention.yaml"
      audits: "src/atdd/coder/validators/test_architecture_*.py"
      deliverables: ["refactor_paths"]
      transitions: "SMOKE → REFACTOR"

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
    - "Test first (RED → GREEN → SMOKE → REFACTOR)"
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

  # ─── MICRO-COMMIT DISCIPLINE (MANDATORY FOR ALL AGENTS) ───────────────
  # Agents MUST commit frequently to avoid losing work.
  # Large uncommitted deltas are the #1 cause of lost agent work
  # (incident: 64 files edited on main, all lost when pre-commit hook blocked).
  #
  # Rules:
  #   1. Commit after EVERY completed sub-task (file created, test written, bug fixed).
  #   2. Never accumulate more than 5 modified files without committing.
  #   3. If you realize you are on main: STOP editing immediately.
  #      Recovery: git stash → atdd branch <N> → cd worktree → git stash pop
  #   4. Prefer many small commits over one large commit — they are easier to
  #      review, revert, and bisect.
  #   5. A commit message can be short ("add CameoRepository") — frequency
  #      matters more than message polish during active development.
  #
  # Anti-patterns (NEVER do these):
  #   - Edit 10+ files then commit once at the end
  #   - Defer commits until "everything works"
  #   - Batch unrelated changes in one commit
  # ───────────────────────────────────────────────────────────────────────
  commit_discipline:
    rule: "Commit after every completed sub-task. Never accumulate >5 modified files."
    frequency: "After each file creation, test addition, or bug fix"
    on_main_detection: "STOP immediately. git stash → atdd branch <N> → cd worktree → git stash pop"
    anti_patterns:
      - "Editing 10+ files before committing"
      - "Deferring commits until everything works"
      - "Batching unrelated changes in one commit"

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

  # ─── PER-WORKTREE GIT CONFIG (PREVENT BLEED-TO-MAIN CONTAMINATION) ─────
  # Inside a git worktree, `git config <key>` (no scope flag) writes to the
  # SHARED `.git/config`, which every worktree reads. Setting certain keys
  # — most dangerously `core.bare` — bleeds to main and other worktrees,
  # causing the Wave 12 contamination class (PRs #625/#627 shipped 220k-
  # line deletions; #629 Layer 1 pre-push hook now blocks the push, but
  # the local mess remains and breaks the worktree's view of files).
  #
  # Repo opt-in is already enabled on main:
  #   extensions.worktreeConfig = true
  #
  # RULE: any time you set a git config inside a worktree for testing or
  # debugging, use the --worktree flag so it stays in that worktree only:
  #
  #   git config --worktree core.bare true     # OK — per-worktree
  #   git config core.bare true                # NEVER — writes to shared
  #
  # Better still: don't set core.bare on real worktrees at all — exercise
  # hook behavior in tmp_path repos. See
  # `src/atdd/coach/templates/hooks/tests/test_C002_unit_pre_push_bare_mode.py`
  # for the correct isolation pattern (every git call uses
  # `git -C str(tmp_path) ...`).
  # ───────────────────────────────────────────────────────────────────────
  worktree_config:
    rule: "Use --worktree flag for per-worktree git config; never run bare git config in a worktree"
    danger_keys: ["core.bare", "core.worktree", "core.hooksPath"]
    repo_extension: "extensions.worktreeConfig = true (already set on this repo's .git/config)"
    test_pattern: "src/atdd/coach/templates/hooks/tests/test_C002_unit_pre_push_bare_mode.py uses git -C str(tmp_path) — never touches the worktree's .git"
    recovery: "If core.bare=true leaks to main: `git -C <main-worktree> config --unset core.bare` then verify with `git status` that the worktree sees its full file set again"
    incident_2026_05_12: "An agent debugging the #583 prepush-validator hook ran `git config core.bare true` directly inside its worktree; that wrote to the SHARED .git/config and contaminated main + sibling worktrees. The #629 Layer 1 hook caught the push (Wave 12 PRs #625/#627 also stopped at push), but the local mess cycled for hours before the root cause (worktrees share .git/config by default) was understood. extensions.worktreeConfig was enabled afterwards."

  # ─── PARALLEL WORK VIA WORKTREE + CMUX ────────────────────────────────
  # Machine-readable rules for parallel agent sessions (waves, babysitter,
  # prompt approval policy, violation patterns, merge cascade, telemetry)
  # live in the orchestration convention file. A human-facing overview of
  # when/why to parallelize is retained under git.branching above.
  # ───────────────────────────────────────────────────────────────────────
  parallelization:
    see: "src/atdd/coach/conventions/orchestration.convention.yaml"
    cli:
      - "atdd orchestrate <issue-numbers...>"
      - "atdd babysit [--interval 60]"
      - "atdd merge-cascade <pr-numbers...>"
      - "atdd session-template <issue-number>"

  workflow:
    branch_strategy: "worktree per branch from main"
    phase_commits:
      - "PLANNED: commit wagon + acceptance criteria"
      - "RED: commit failing tests"
      - "GREEN: commit passing implementation"
      - "REFACTOR: commit clean architecture"

  micro_commit_hooks:
    purpose: "Advisory warnings to encourage smaller commits (all exit 0, never block)"
    pre_push: "Warns when >10 uncommitted/untracked files (override: ATDD_MAX_UNCOMMITTED)"
    pre_commit: "Warns when >20 staged files (override: ATDD_MAX_STAGED)"
    claude_code:
      template: "src/atdd/coach/templates/hooks/claude-pre-tool-use.sh"
      install: "cp src/atdd/coach/templates/hooks/claude-pre-tool-use.sh .claude/hooks/pre_tool_use.sh"
      behavior: "Reminds agent to commit when >5 files modified since last commit"

  # Post-commit hook — blast-radius local validation (#611).
  # After every commit, derives which files were touched via `git show --name-only HEAD`,
  # maps them to validator phases, and runs ONLY those phases in parallel.
  # Always exits 0 (info-only; cannot undo a commit). No-op when CI=true.
  # Override: ATDD_SKIP_POSTCOMMIT=1 git commit ...
  post_commit_hook:
    purpose: "Real-time self-healing — surface validator failures within seconds of introduction"
    template: "src/atdd/coach/templates/hooks/post-commit"
    behavior: "Runs only validators in the commit's blast radius, in parallel, never blocks"
    path_to_phase_mapping:
      "plan/**":             "atdd repo validate"
      "contracts/**":        "atdd repo validate + atdd validate tester --local --skip-api"
      "src/atdd/planner/**": "atdd validate planner --local --skip-api"
      "src/atdd/tester/**":  "atdd validate tester --local --skip-api"
      "src/atdd/coder/**":   "atdd validate coder --local --skip-api"
      "src/atdd/coach/**":   "atdd validate coach --local --skip-api"
      ".atdd/manifest.yaml": "atdd validate coach --local --skip-api"
    overrides:
      ci: "CI=true → exits 0 immediately (CI runs full validate)"
      skip: "ATDD_SKIP_POSTCOMMIT=1 → exits 0 immediately"
    first_commit_safe: "Uses `git show --name-only HEAD` (works on first-ever commit, unlike `git diff HEAD~1..HEAD`)"

# Escalation channel — `atdd coach --escalation-channel <X>` value format (#615).
# Validated at CLI parse time; malformed values are rejected before coach runs.
coach_escalation_channel:
  purpose: "Where atdd coach routes human-escalation events (spec §9)"
  forms:
    file: "file:<path>            (e.g. file:./.atdd/escalations.log)"
    bare_path: "<path>                  (bare relative or absolute path, shortcut for file:)"
    slack_webhook: "slack-webhook:<https-url>     (e.g. slack-webhook:https://hooks.slack.com/services/X/Y/Z)"
    gh_issue_full: "gh-issue:owner/repo#N         (e.g. gh-issue:afokapu/atdd#999)"
    gh_issue_short: "gh-issue:#N                  (e.g. gh-issue:#999 — uses current repo)"
  validator: "src/atdd/coach/utils/escalation_channel.py::parse_escalation_channel"
  invalid_values_rejected_at: "argparse parse time (loud error with valid-forms list)"

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
    - "Commit: 'Bump version to {version}' (last commit in PR branch)"
    - "Push branch and merge PR (version bump is part of the PR)"
    - "After merge: git tag v{version} on the merge commit, then git push origin --tags"
    - "Record in Activity Log: 'Released: v{version}'"

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
    role: "Implement GREEN code, then REFACTOR to clean architecture (SMOKE between GREEN and REFACTOR)"
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
    new: "atdd issue <slug>                        # Create parent issue + WMBT sub-issues"
    new_with_opts: "atdd issue <slug> --archetypes be,contracts --train <id>"
    enter: "atdd issue <N>                         # Enter issue (state-driven context)"
    list: "atdd issue open                         # List open issues"
    list_all: "atdd list                           # List all issues (from GitHub)"
    update: "atdd issue <N> --status <STATUS>      # Transition status + swap labels"
    close_wmbt: "atdd issue <N> --close-wmbt <ID>  # Close a WMBT sub-issue"
    validate: "atdd validate coach                 # Validate Project fields + sub-issue state"

  # MANDATORY: All issue and PR operations MUST go through the atdd CLI.
  # NEVER use `gh issue create`, `gh pr create`, or the GitHub web UI directly.
  # Reason: Direct creation bypasses manifest registration, WMBT sub-issue
  # generation, Project v2 field setup, and worktree metadata.
  # The coach validator (`atdd validate coach`) will flag issues that exist
  # on GitHub but are missing from .atdd/manifest.yaml.
  #
  # PR creation specifically: the canonical site is `atdd pr <N>`, which
  # validates `--base` against the repo's default branch (#477). Direct
  # `gh pr create` invocations bypass that guard. The lived incident:
  # PR #475 (the v3.11.0 #473-Phase-2+3 work) was opened with
  # `gh pr create` and inherited a sibling-PR's branch as its base; when
  # the sibling merged + auto-deleted that branch, #475's squash-merge
  # commit landed on a phantom ref invisible to `git log main`. The
  # v3.11.0 deliverable was orphaned — Closes #473 fired without the work
  # actually shipping. Recovery cost: PR #476, manual conflict resolution,
  # ~15 min. The Phase-2 coach validator
  # (`coach.pr.base-must-be-default-branch`) now flags any open PR with a
  # non-default base on every `atdd validate coach` run. Use `atdd pr <N>`
  # for ALL PR creation.
  prohibited_commands:
    - "gh issue create    → use: atdd issue <slug>"
    - "gh pr create       → use: atdd pr <N>  (validates --base against the repo default branch; #477 / #475 orphan-merge incident)"

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
    coach: "ATDD orchestration, conventions, hooks, validators, CLI"

  atdd_phases:
    RED: "Write failing tests from acceptances"
    GREEN: "Implement minimal code to pass tests"
    SMOKE: "Verify against real infrastructure (HTTP, DB, auth)"
    REFACTOR: "Clean architecture, 4-layer compliance"

# State Machine (issue lifecycle transitions)
state_machine:
  transitions:
    INIT: [PLANNED, BLOCKED, OBSOLETE]
    PLANNED: [RED, BLOCKED, OBSOLETE]
    RED: [GREEN, BLOCKED, OBSOLETE]
    GREEN: [SMOKE, BLOCKED, OBSOLETE]
    SMOKE: [REFACTOR, BLOCKED, OBSOLETE]
    REFACTOR: [COMPLETE, BLOCKED, OBSOLETE]
    BLOCKED: [INIT, PLANNED, RED, GREEN, SMOKE, REFACTOR, OBSOLETE]
    COMPLETE: []
    OBSOLETE: []
  command: "atdd issue <N> --status <STATUS>"
  rules:
    - "Train field required past PLANNED (enforced by CLI + validator)"
    - "Labels swapped automatically (atdd:RED → atdd:GREEN)"

# Quality Gates (Detailed in action files)
validations:
  phase_transitions:
    INIT→PLANNED: "planner delivers wagon with acceptance criteria"
    PLANNED→RED: "tester delivers RED tests"
    RED→GREEN: "coder delivers passing tests"
    GREEN→SMOKE: "tester delivers smoke tests against real infrastructure"
    SMOKE→REFACTOR: "coder delivers clean architecture"

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
    - "smoke.convention.yaml: SMOKE phase integration tests"

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
