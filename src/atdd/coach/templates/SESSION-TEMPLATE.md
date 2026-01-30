<!--
# =============================================================================
# TOOL GATE (MANDATORY BEFORE FILLING THIS FILE)
# =============================================================================
# If your agent supports plan mode (Claude Code, etc.), enable it NOW.
# This is a tool capability gate, NOT the ATDD Planner phase.
# If unavailable, state: "Plan mode unavailable" and proceed.
# =============================================================================
-->
---
# SESSION METADATA (YAML frontmatter - machine-parseable)
#
# FIRST: Rename this conversation with /rename SESSION-{NN}-{slug}
#
session: "{NN}"
title: "{Title}"
date: "{YYYY-MM-DD}"
status: "INIT"  # INIT | PLANNED | ACTIVE | BLOCKED | COMPLETE | OBSOLETE
branch: "{branch-name}"
type: "{type}"  # implementation | migration | refactor | analysis | planning | cleanup | tracking
complexity: 3  # 1=Trivial, 2=Low, 3=Medium, 4=High, 5=Very High
archetypes:
  - "{archetype}"  # db | be | fe | contracts | wmbt | wagon | train | telemetry | migrations

# Scope definition
scope:
  in:
    - "{specific-deliverable-1}"
    - "{specific-deliverable-2}"
  out:
    - "{explicitly-excluded-1}"
  dependencies:
    - "{SESSION-XX or external requirement}"

# ATDD Workflow Phase Tracking (MANDATORY)
# Sequence: Planner → Tester → Coder (see session.convention.yaml:workflow)
workflow_phases:
  planner:
    status: "TODO"  # TODO | IN_PROGRESS | DONE | SKIPPED | N/A
    artifacts:
      train: false      # plan/_trains.yaml updated
      wagon: false      # plan/{wagon}/_{wagon}.yaml exists
      feature: false    # plan/{wagon}/features/{feature}.yaml exists
      wmbt: false       # WMBTs defined in feature YAML
    gate: "python3 -m pytest src/src/atdd/planner/validators/ -v"
    gate_status: "TODO"

  tester:
    status: "TODO"
    depends_on: "planner"
    artifacts:
      contracts: false  # contracts/{domain}/{resource}.schema.json exists
      red_tests: false  # Failing tests exist for all WMBTs
    gate: "python3 -m pytest src/src/atdd/tester/validators/ -v"
    gate_status: "TODO"
    red_gate: "pytest {test_path} -v (expect FAIL)"
    red_gate_status: "TODO"

  coder:
    status: "TODO"
    depends_on: "tester"
    artifacts:
      implementation: false  # Code exists in {runtime}/{wagon}/{feature}/src/
    gate: "python3 -m pytest src/atdd/coder/validators/ -v"
    gate_status: "TODO"
    green_gate: "pytest {test_path} -v (expect PASS)"
    green_gate_status: "TODO"
    refactor_gate: "python3 -m pytest src/atdd/coder/validators/ -v"
    refactor_gate_status: "TODO"

# Progress tracking (machine-readable)
progress:
  phases:
    - id: "P1"
      name: "{Phase-1-Name}"
      status: "TODO"  # TODO | IN_PROGRESS | DONE | BLOCKED | SKIPPED
      gate: "{validation-command}"
    - id: "P2"
      name: "{Phase-2-Name}"
      status: "TODO"
      gate: "{validation-command}"

  # WMBT tracking (for implementation sessions)
  wmbt:
    - id: "D001"
      description: "{description}"
      red: "TODO"
      green: "TODO"
      refactor: "TODO"
    - id: "L001"
      description: "{description}"
      red: "TODO"
      green: "TODO"
      refactor: "TODO"

  # ATDD phase summary
  atdd:
    red:
      status: "TODO"
      gate: "pytest {test-path} -v (expect FAIL)"
    green:
      status: "TODO"
      gate: "pytest {test-path} -v (expect PASS)"
    refactor:
      status: "TODO"
      gate: "pytest src/atdd/coder/validators/ -v"

# Gate Tests - Required validation gates with ATDD validators
# See: src/atdd/coach/conventions/session.convention.yaml for required gates per archetype
gate_tests:
  # Universal gates (required for all sessions)
  - id: "GT-001"
    phase: "design"
    archetype: "all"
    command: "python3 -m pytest src/atdd/coach/validators/test_session_validation.py -v"
    expected: "PASS"
    atdd_validator: "src/atdd/coach/validators/test_session_validation.py"
    status: "TODO"

  # Archetype-specific gates (add based on declared archetypes)
  # Example for 'be' archetype:
  # - id: "GT-010"
  #   phase: "implementation"
  #   archetype: "be"
  #   command: "python3 -m pytest src/atdd/coder/validators/test_python_architecture.py -v"
  #   expected: "PASS"
  #   atdd_validator: "src/atdd/coder/validators/test_python_architecture.py"
  #   status: "TODO"

  # Example for 'fe' archetype:
  # - id: "GT-020"
  #   phase: "implementation"
  #   archetype: "fe"
  #   command: "python3 -m pytest src/atdd/coder/validators/test_typescript_architecture.py -v"
  #   expected: "PASS"
  #   atdd_validator: "src/atdd/coder/validators/test_typescript_architecture.py"
  #   status: "TODO"

  # Completion gate (required for all sessions)
  - id: "GT-900"
    phase: "completion"
    archetype: "all"
    command: "python3 -m pytest src/atdd/ -v --tb=short"
    expected: "PASS"
    atdd_validator: "src/atdd/"
    status: "TODO"

# Success criteria (checkboxes tracked here)
success_criteria:
  - text: "{measurable-outcome-1}"
    done: false
  - text: "{measurable-outcome-2}"
    done: false

# Decisions log
decisions:
  - id: "Q1"
    question: "{question-faced}"
    decision: "{choice-made}"
    rationale: "{why-this-choice}"

# Related references
related:
  sessions:
    - "{SESSION-XX}: {relationship-description}"
  wmbt:
    - "wmbt:{wagon}:{ID}"

# Artifacts produced
artifacts:
  created: []
  modified: []
  deleted: []
---

<!--
IMPLEMENTATION RULES:
1. BEFORE creating/updating files: Identify existing patterns in codebase
2. New files MUST follow conventions in atdd/*/conventions/*.yaml
3. New files MUST match patterns of similar existing files
4. When in doubt: find 2-3 similar files and replicate their structure
5. NEVER introduce new patterns without explicit decision documented
6. Validate: python3 -m pytest src/atdd/ -v --tb=short
-->

# SESSION-{NN}: {Title}

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| {aspect-1} | {current-state} | {target-state} | {why-it's-a-problem} |

### User Impact

{How does this problem affect users, developers, or the system? Be specific.}

### Root Cause

{Why does this problem exist? What architectural or design decisions led to it?}

---

## Architecture

### Existing Patterns (MUST identify before implementation)

<!-- Search codebase for similar files and document patterns found -->

| Pattern | Example File | Convention |
|---------|--------------|------------|
| {layer-structure} | `python/{wagon}/src/domain/` | `atdd/coder/conventions/backend.convention.yaml` |
| {naming} | `test_{WMBT}_unit_{NNN}_{desc}.py` | `atdd/tester/conventions/filename.convention.yaml` |
| {imports} | `from .entities import X` | `atdd/coder/conventions/boundaries.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| {term-1} | {what-it-means} | {concrete-example} |

### Before State

```
{ascii-diagram or structure showing current state}
```

### After State

```
{ascii-diagram or structure showing target state}
```

### Data Model

<!-- Include if archetypes includes: db -->

```sql
-- Table/view definitions
CREATE TABLE IF NOT EXISTS public.{table_name} (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  data JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Phases

### Phase 1: {Name}

**Deliverables:**
- {artifact-path-1} - {what-it-does}
- {artifact-path-2} - {what-it-does}

**Files:**

| File | Change |
|------|--------|
| `{path/to/file}` | {description-of-change} |

### Phase 2: {Name}

**Deliverables:**
- {artifact-path-1} - {what-it-does}

**Files:**

| File | Change |
|------|--------|
| `{path/to/file}` | {description-of-change} |

---

## Validation

### Gate Tests (ATDD Validators)

<!--
Gate tests enforce conventions via ATDD validators.
Each declared archetype MUST have corresponding gate tests.
Reference: src/atdd/coach/conventions/session.convention.yaml
-->

| ID | Phase | Archetype | Command | Expected | ATDD Validator | Status |
|----|-------|-----------|---------|----------|----------------|--------|
| GT-001 | design | all | `python3 -m pytest src/atdd/coach/validators/test_session_validation.py -v` | PASS | `src/atdd/coach/validators/test_session_validation.py` | TODO |
| GT-010 | implementation | {archetype} | `{command}` | PASS | `{atdd_validator_path}` | TODO |
| GT-900 | completion | all | `python3 -m pytest src/atdd/ -v --tb=short` | PASS | `src/atdd/` | TODO |

### Phase Gates

#### Gate 1: {Phase-1-Name}

```bash
{validation-command-1}
```

**Expected:** {expected-outcome}
**ATDD Validator:** `{atdd/scope/validators/test_file.py}`

#### Gate 2: {Phase-2-Name}

```bash
{validation-command-2}
```

**Expected:** {expected-outcome}
**ATDD Validator:** `{atdd/scope/validators/test_file.py}`

---

## Session Log

### Session 1 ({YYYY-MM-DD}): {Focus}

**Completed:**
- {work-item-1}
- {work-item-2}

**Blocked:**
- {blocker-if-any}

**Next:**
- {next-action-1}
- {next-action-2}

---

## Release Gate (MANDATORY)

<!--
Every session MUST end with a version bump + matching git tag.

Change Class:
- PATCH: bug fixes, docs, refactors, internal changes
- MINOR: new feature, new validator, new command, new convention (non-breaking)
- MAJOR: breaking API/CLI/schema/convention change or behavior removal

Rules:
- Tag must match version exactly: v{version}
- No tag without version bump
- No version bump without tag
-->

- [ ] Determine change class: PATCH / MINOR / MAJOR
- [ ] Bump version in version file (pyproject.toml, package.json, etc.)
- [ ] Commit: "Bump version to {version}"
- [ ] Create tag: `git tag v{version}`
- [ ] Push with tags: `git push origin {branch} --tags`
- [ ] Record tag in Session Log: "Released: v{version}"

---

## Notes

{Additional context, learnings, or decisions that don't fit elsewhere.}
