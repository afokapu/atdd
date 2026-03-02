## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `{today}` |
| Status | `INIT` |
| Type | `{issue_type}` |
| Branch | TBD <!-- fmt: {prefix}/{slug} e.g. feat/my-feature --> |
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
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
{gate_tests_rows}| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
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
- Issue created via `atdd new {slug}`

**Next:**
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

## Release Gate

- [ ] Determine change class: PATCH / MINOR / MAJOR
- [ ] Bump version in version file
- [ ] Commit: "Bump version to {{version}}" (last commit in PR branch)
- [ ] Merge PR (version bump included in the PR)
- [ ] After merge: `git tag v{{version}}` on merge commit, then `git push origin --tags`
- [ ] Record tag in Activity Log: "Released: v{{version}}"

---

## Notes

(Additional context, learnings, or decisions that don't fit elsewhere.)
