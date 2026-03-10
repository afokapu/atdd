## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/structured-logging-convention --> |
| Archetypes | be, wmbt, telemetry |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- Convention requiring structured logging (JSON format) with mandatory fields
- Required fields: `correlation_id`, `severity`, `wagon`, `layer`, `message`
- Validator that checks log calls include required structured fields
- Validator that flags bare `print()` statements in non-test code
- Integration into `atdd validate coder` pipeline

### Out of Scope

- Log aggregation infrastructure (ELK, Datadog, etc.)
- Log rotation and retention policies
- Frontend logging (different runtime)

### Dependencies

- Existing telemetry convention in `telemetry/`

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Log format | Mix of print(), logger.info(string), structured | All structured JSON with required fields | Logs are unsearchable, uncorrelatable |
| Print statements | No detection | Validator flags `print()` in non-test code | Debug prints reach production |
| Correlation | Optional/missing | Required `correlation_id` in all log entries | Cannot trace requests across components |
| Log context | Ad-hoc | Wagon + layer context required | Cannot filter logs by architectural boundary |

### User Impact

When debugging production issues, developers cannot correlate logs across wagons, filter by architectural layer, or trace a single request end-to-end. Code reviewers catch obvious `print()` statements but miss inconsistent logger usage.

### Root Cause

No convention enforces structured logging. Each developer uses their preferred format. The telemetry convention defines metrics but not log structure.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Telemetry structure | `telemetry/_telemetry.yaml` | `tester/conventions/artifact.convention.yaml` |
| Architecture validator | `src/atdd/coder/validators/test_python_architecture.py` | `coder/conventions/backend.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| Structured log | JSON-formatted log entry with required fields | `{"severity": "INFO", "wagon": "auth", "layer": "application", "message": "..."}` |
| Correlation ID | Request-scoped unique identifier | `req-abc123` propagated through all log entries |
| Bare print | `print()` call in production code | `print(f"user: {user_id}")` — no structure, no severity |

### Before State

```
Code uses: print(), logger.info("string"), logger.info({"key": "val"})
No standard, no required fields
Cannot search/filter/correlate
```

### After State

```
Code uses: logger.info(message, extra={structured_fields})
Required fields enforced by validator
print() flagged in non-test code
```

---

## Phases

### Phase 1: Structured Logging Convention

**Deliverables:**
- `src/atdd/coder/conventions/logging.convention.yaml` - Logging rules

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/conventions/logging.convention.yaml` | New convention: structured logging requirements |

### Phase 2: Logging Validator

**Deliverables:**
- `src/atdd/coder/validators/test_logging_compliance.py` - Log format validator

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_logging_compliance.py` | New validator: structured logging + no bare print() |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_logging_compliance.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_logging_compliance.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] Logging convention defines required fields for structured logs
- [ ] Bare `print()` in non-test Python code flagged
- [ ] Logger calls without required structured fields flagged
- [ ] Correlation ID enforcement validated

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Log library? | Python stdlib `logging` with JSON formatter | No extra dependency, works with any aggregator |
| 2 | Allow print() in tests? | Yes | Test output is ephemeral, structured logging adds noise |

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

Origin: Gap analysis comparing ATDD automated validators vs manual code review. Logging quality was identified as a convention-enforceable concern — the structure is a rule, the message content is judgment.
