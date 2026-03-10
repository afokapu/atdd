## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/error-message-convention --> |
| Archetypes | be, contracts, wmbt |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- Convention defining error response contract schema (code, message, detail, correlation_id)
- Validator that checks presentation layer error responses match the contract
- Validator that flags raw exception propagation to API responses
- JSON Schema contract for standardized error responses

### Out of Scope

- Error message content/wording (human judgment)
- Internal logging format (covered by logging convention)
- Client-side error display (frontend concern)

### Dependencies

- Existing contract infrastructure in `contracts/`
- Existing tester convention for contract validation

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Error responses | No standard format | Contract-enforced error schema | Users see raw stack traces or inconsistent error shapes |
| Exception propagation | No detection | Validator flags raw exceptions in responses | Internal errors leak implementation details |
| Correlation IDs | Optional/inconsistent | Required in error contract | Cannot trace errors across services |

### User Impact

Users receive inconsistent error responses — sometimes a JSON object with `message`, sometimes a raw string, sometimes a stack trace. Frontend code must handle multiple formats. Debugging requires guessing which service failed.

### Root Cause

No contract exists for error responses. Each wagon and endpoint defines its own error format. Code reviewers catch egregious cases but the inconsistency is systemic.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Contract schema | `contracts/` | `tester/conventions/contract.convention.yaml` |
| Contract validation | `src/atdd/tester/validators/test_contract_schema_compliance.py` | `tester/conventions/contract.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| Error contract | JSON Schema defining error response shape | `{ code: "NOT_FOUND", message: "...", correlation_id: "..." }` |
| Raw exception | Unhandled exception reaching the API response | `500: Internal Server Error: KeyError: 'user_id'` |
| Correlation ID | Unique identifier linking request → logs → error | `req-abc123-def456` |

### Before State

```
Endpoint errors → ad-hoc format per endpoint
No contract for error shape
Raw exceptions reach users
```

### After State

```
Endpoint errors → standardized error contract
Validator ensures presentation layer uses error contract
Raw exceptions flagged by validator
```

---

## Phases

### Phase 1: Error Response Contract

**Deliverables:**
- `contracts/common/error.schema.json` - Standard error response schema

**Files:**

| File | Change |
|------|--------|
| `contracts/common/error.schema.json` | New contract: error response schema |

### Phase 2: Error Response Validator

**Deliverables:**
- `src/atdd/coder/validators/test_error_response_compliance.py` - Error format validator

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_error_response_compliance.py` | New validator: check presentation layer error handling |
| `src/atdd/coder/conventions/error.convention.yaml` | New convention: error handling rules |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_error_response_compliance.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_error_response_compliance.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] Error response JSON Schema contract defined
- [ ] Presentation layer error handlers validated against contract
- [ ] Raw exception propagation to API responses flagged
- [ ] Correlation ID required in all error responses

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Error code format? | String enum (e.g., `NOT_FOUND`) | More readable than numeric codes, self-documenting |
| 2 | Include stack trace in dev? | Optional `debug` field, stripped in production | Helps development without leaking in production |

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

Origin: Gap analysis comparing ATDD automated validators vs manual code review. Error message quality was identified as a contract-enforceable concern — the shape is a rule, the wording is judgment.
