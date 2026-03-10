## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/n-plus-one-detector --> |
| Archetypes | be, wmbt |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- Validator that instruments test execution to count DB calls per test
- Threshold-based flagging (e.g., >N DB calls per test = warning)
- Integration into `atdd validate coder` pipeline
- Report output showing which tests trigger excessive queries

### Out of Scope

- Query optimization (validator detects, human fixes)
- Production monitoring (this is test-time detection only)
- ORM-specific analysis (framework-agnostic DB call counting)

### Dependencies

- Test infrastructure must use a DB client that can be instrumented/counted

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| N+1 queries | Found only in code review or production profiling | Detected at test time via DB call counting | Performance issues reach production undetected |
| Query count | No visibility | Per-test DB call count reported | Reviewers manually trace query paths |

### User Impact

N+1 queries cause latency spikes in production. They pass all functional tests because they produce correct results — just slowly. Code reviewers catch them inconsistently.

### Root Cause

ATDD validates structure and behavior but not performance characteristics. DB call counting during tests is a deterministic, automatable check.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Coder validator | `src/atdd/coder/validators/test_python_architecture.py` | `coder/conventions/backend.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| N+1 query | One query to fetch parents + N queries to fetch each child | `for user in users: db.get_orders(user.id)` |
| DB call count | Number of database round-trips during a single test | Threshold: ≤5 per test default |

### Before State

```
Test execution → pass/fail only
No visibility into query count
```

### After State

```
Test execution → pass/fail + query count per test
Validator flags tests exceeding threshold
```

---

## Phases

### Phase 1: DB Call Counter

**Deliverables:**
- `src/atdd/coder/validators/test_query_count.py` - DB call counting validator

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_query_count.py` | New validator: count DB calls per test, flag threshold violations |
| `src/atdd/coder/conventions/performance.convention.yaml` | New convention defining query count thresholds |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_query_count.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_query_count.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] DB call count tracked per test execution
- [ ] Tests exceeding threshold flagged with specific count
- [ ] Threshold configurable per wagon/feature
- [ ] Integrated into `atdd validate coder`

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | How to count DB calls? | Instrument DB client with call counter | Framework-agnostic, works with any DB |
| 2 | Default threshold? | 5 DB calls per test | Catches obvious N+1, low false-positive rate |

---

## Activity Log

### Entry 1 (2026-03-10)

**Completed:**
- Issue created from ATDD-vs-code-review gap analysis

**Next:**
- Create branch
- Define WMBT acceptance criteria
- Write RED tests

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

Before merge: rebase on main, bump version based on branch prefix, commit, push.
After merge: CI tags and publishes to PyPI automatically.

- [ ] Rebase on main: `git pull origin main --rebase`
- [ ] Bump version (feat/ → MINOR, fix/ → PATCH): edit version file, commit "Bump version to X.Y.Z"
- [ ] Merge PR → CI creates tag + publishes

---

## Notes

Origin: Gap analysis comparing ATDD automated validators vs manual code review. N+1 query detection was identified as a deterministic check that code reviewers perform inconsistently.
