## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/dead-code-validator --> |
| Archetypes | be, fe, wmbt |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- Validator that cross-references exports/imports to find unreachable code
- Detection of unused functions, classes, and variables in Python code
- Detection of unused exports in TypeScript code
- Integration into `atdd validate coder` pipeline

### Out of Scope

- Dynamic imports (runtime-resolved, cannot be statically analyzed)
- Template-referenced code (e.g., Jinja2 templates calling functions)
- Entry points and CLI commands (explicitly marked as roots)

### Dependencies

- AST parsing infrastructure (Python `ast` module, TypeScript parser)

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Dead code | Found during code review or never | AST-based unreachable code detection | Dead code accumulates, increases maintenance burden |
| Unused exports | No detection | Import/export cross-reference analysis | Reviewers manually trace usage |

### User Impact

Dead code confuses developers, increases cognitive load, and makes refactoring harder. Code reviewers occasionally spot it but miss most cases.

### Root Cause

ATDD validates that required code exists (architecture layers, boundaries) but doesn't validate that existing code is actually used. Reachability analysis is deterministic and automatable.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Import boundary check | `src/atdd/coder/validators/test_import_boundaries.py` | `coder/conventions/boundaries.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| Dead code | Defined but never referenced from any reachable path | `def old_handler(): ...` with no callers |
| Root | Entry point that is always considered reachable | `app.py`, CLI commands, test files |
| Export graph | Map of all module exports and their consumers | `module.func` → imported by `[a.py, b.py]` |

### Before State

```
Validators check: structure, boundaries, architecture
No check: is this code actually used?
```

### After State

```
Validators check: structure, boundaries, architecture, reachability
Dead code flagged with: file, line, symbol name, zero references
```

---

## Phases

### Phase 1: Python Dead Code Validator

**Deliverables:**
- `src/atdd/coder/validators/test_dead_code_python.py` - Python unreachable code detector

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_dead_code_python.py` | New validator: AST import/def cross-reference |

### Phase 2: TypeScript Dead Code Validator

**Deliverables:**
- `src/atdd/coder/validators/test_dead_code_typescript.py` - TypeScript unreachable export detector

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_dead_code_typescript.py` | New validator: export/import cross-reference |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_dead_code_python.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_dead_code_python.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] Unused Python functions/classes detected via AST analysis
- [ ] Unused TypeScript exports detected via import cross-reference
- [ ] Root entry points configurable (not flagged as dead)
- [ ] Zero false positives on composition roots (`composition.py`, `wagon.py`)

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | How to handle dynamic imports? | Exclude from analysis | Cannot statically resolve, would cause false positives |
| 2 | How to handle composition roots? | Explicit allowlist | `composition.py` and `wagon.py` are entry points by convention |

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

Origin: Gap analysis comparing ATDD automated validators vs manual code review. Dead code detection was identified as a deterministic analysis that reviewers perform inconsistently.
