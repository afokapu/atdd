## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/security-pattern-validator --> |
| Archetypes | be, wmbt |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- AST-based validator that scans Python code for raw SQL string concatenation
- Validator that detects missing auth decorators on FastAPI route handlers
- Validator that flags hardcoded secrets (API keys, passwords, tokens in source)
- Validator that detects `innerHTML` / `dangerouslySetInnerHTML` usage in frontend code
- Integration into `atdd validate coder` pipeline

### Out of Scope

- Runtime security scanning (DAST)
- Dependency vulnerability scanning (handled by Dependabot/Snyk)
- Infrastructure security (IAM, network policies)

### Dependencies

- Existing `atdd validate coder` pipeline for integration point

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Security patterns | Caught only in manual code review | Automated validator in ATDD coder phase | Security issues slip through when reviewers miss them |
| Auth decorators | No enforcement | Every route handler validated | Unauthenticated endpoints deployed accidentally |
| Raw SQL | No detection | AST scan flags concatenation | SQL injection possible in integration layer |
| Hardcoded secrets | No detection | Regex + entropy scan flags secrets | Secrets committed to repo |

### User Impact

Security vulnerabilities reach production when code reviewers miss patterns. Automated detection catches 100% of known-bad patterns, freeing reviewers to focus on logic-level security.

### Root Cause

ATDD validators cover architecture and structure but have no security-focused validators. These are deterministic rules that pretend to be opinions during code review.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Coder validator | `src/atdd/coder/validators/test_python_architecture.py` | `coder/conventions/backend.convention.yaml` |
| Import boundary check | `src/atdd/coder/validators/test_import_boundaries.py` | `coder/conventions/boundaries.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| Security pattern | A code pattern known to introduce vulnerabilities | `f"SELECT * FROM {table}"` |
| Auth decorator | FastAPI dependency that enforces authentication | `@require_auth` |
| Secret pattern | String matching known secret formats | `AKIA...` (AWS key prefix) |

### Before State

```
src/atdd/coder/validators/
├── test_python_architecture.py
├── test_typescript_architecture.py
├── test_import_boundaries.py
└── test_wagon_boundaries.py
```

### After State

```
src/atdd/coder/validators/
├── test_python_architecture.py
├── test_typescript_architecture.py
├── test_import_boundaries.py
├── test_wagon_boundaries.py
├── test_security_patterns.py          # NEW
└── test_frontend_security_patterns.py # NEW
```

---

## Phases

### Phase 1: Security Pattern Validator (Python)

**Deliverables:**
- `src/atdd/coder/validators/test_security_patterns.py` - AST-based Python security scanner

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_security_patterns.py` | New validator: raw SQL, missing auth, hardcoded secrets |
| `src/atdd/coder/conventions/security.convention.yaml` | New convention defining security rules |

### Phase 2: Security Pattern Validator (Frontend)

**Deliverables:**
- `src/atdd/coder/validators/test_frontend_security_patterns.py` - Frontend security scanner

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_frontend_security_patterns.py` | New validator: innerHTML, XSS patterns |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_security_patterns.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_security_patterns.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] Raw SQL concatenation detected in Python files
- [ ] Missing auth decorators flagged on route handlers
- [ ] Hardcoded secret patterns detected
- [ ] innerHTML/dangerouslySetInnerHTML flagged in frontend
- [ ] All validators integrated into `atdd validate coder`

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | AST vs regex for Python? | AST | More accurate, fewer false positives on string concatenation |
| 2 | Separate convention file? | Yes — `security.convention.yaml` | Security rules are cross-cutting, not layer-specific |

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

Origin: Gap analysis comparing ATDD automated validators vs manual code review. Security pattern detection was identified as a "rule pretending to be an opinion" — fully encodable as a validator.
