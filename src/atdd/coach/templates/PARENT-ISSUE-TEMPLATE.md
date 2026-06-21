## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `{today}` |
| Status | `INIT` |
| Type | `{issue_type}` |
| Branch | {branch_display} |
| Archetypes | {archetypes_display} |
| Train | {train_display} |
| Feature | TBD |

---

## Scope

### In Scope

- (define specific deliverables)

### Out of Scope

- (define explicit exclusions)

### Dependencies

- (list session or external dependencies)

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| (aspect) | (current state) | (target state) | (why it's a problem) |

### User Impact

(How does this problem affect users, developers, or the system?)

### Root Cause

(Why does this problem exist? What architectural or design decisions led to it?)

---

## Architecture

### Graph Context

(graph context will be injected at creation by atdd issue <slug>)

### Mirror Across Agents

| Agent | Current state | Target state | Action |
|-------|---------------|--------------|--------|
| planner | (current — observed/missing) | (target — declared rule, validator, etc.) | (action — add/update/none) |
| tester | (current — observed/missing) | (target) | (action) |
| coder | (current — observed/missing) | (target) | (action) |
| coach | (current — observed/missing) | (target) | (action) |

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| (pattern) | `(path)` | `(convention file)` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| (term) | (definition) | (example) |

### Before State

```
(current architecture/structure)
```

### After State

```
(target architecture/structure)
```

{data_model_section}

---

## Rule Wiring

(OPTIONAL — fill in only when this issue introduces new convention rules. Otherwise leave the table empty or remove this section.)

| rule_id | severity | disposition | bind_to | fix_hint_ref |
|---------|----------|-------------|---------|--------------|
| (rule_id) | (1-5) | (strict\|suppress-and-clean\|advisory\|documentation-only) | (validator module::function) | (recipe or convention pointer) |

---

## Phases

### Phase 1: (Name)

**Deliverables:**
- (artifact) - (description)

**Files:**

| File | Change |
|------|--------|
| `(path)` | (description) |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check --scope changed-files` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
{gate_tests_rows}| GT-800 | completion | `atdd repo validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] (measurable outcome 1)
- [ ] (measurable outcome 2)

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | (question) | (decision) | (rationale) |

---

## Activity Log

### Entry 1 ({today})

**Completed:**
- Issue created via `atdd issue {slug}`

**Next:**
- Create branch: `atdd branch <N>` (this issue's number)
- Fill Context, Scope, and Architecture sections
- Define phases and gate tests

---

## Artifacts

### Created

- (none yet)

### Modified

- (none yet)

### Deleted

- (none yet)

---

## Release Gate (AUTOMATED)

Version + tag + publish are fully automated on merge — do NOT bump the version
or tag by hand. CI (`post-merge-lifecycle.yml`) bumps the pyproject version on
main from the branch prefix (feat/→MINOR, fix|chore|docs|refactor|devops/→PATCH,
BREAKING/!:→MAJOR), then `publish.yml` tags the new version and publishes to PyPI.
A manual version edit SKIPS the auto-bump and causes version-line merge conflicts.

- [ ] Do NOT edit pyproject.toml::version — CI bumps it on merge from the branch prefix
- [ ] Do NOT create or push git tags — CI tags + publishes after the bump lands on main
- [ ] Merge PR → confirm the `chore(release): bump version … [auto]` commit appears on main

---

## Notes

(Additional context, learnings, or decisions that don't fit elsewhere.)
