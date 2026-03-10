## Issue Metadata

| Field | Value |
|-------|-------|
| Date | `2026-03-10` |
| Status | `INIT` |
| Type | `implementation` |
| Branch | TBD <!-- fmt: feat/duplication-detector --> |
| Archetypes | be, fe, wmbt |
| Train | TBD |
| Feature | TBD |

---

## Scope

### In Scope

- AST-based similarity detection for code blocks within the same layer
- Configurable similarity threshold (e.g., ≥80% AST similarity)
- Detection scoped per wagon per layer (not cross-wagon, which is allowed duplication)
- Integration into `atdd validate coder` pipeline

### Out of Scope

- Cross-wagon duplication (wagons are intentionally isolated)
- Test file duplication (test fixtures may legitimately repeat)
- Configuration/boilerplate duplication (composition roots, __init__.py)

### Dependencies

- AST parsing for both Python and TypeScript

---

## Context

### Problem Statement

| Aspect | Current | Target | Issue |
|--------|---------|--------|-------|
| Code duplication | Spotted by reviewers inconsistently | AST similarity detection within layers | Copy-paste code accumulates within wagons |
| Refactor signals | Subjective reviewer judgment | Quantified similarity score | Reviewers disagree on when duplication is "too much" |

### User Impact

Duplicated code within a layer means bugs must be fixed in multiple places. Reviewers catch obvious copy-paste but miss structural duplication where variable names differ.

### Root Cause

ATDD checks boundaries between layers and wagons but not redundancy within them. AST similarity is a structural comparison that ignores variable names — catching duplication that textual diff misses.

---

## Architecture

### Existing Patterns

| Pattern | Example File | Convention |
|---------|--------------|------------|
| Architecture validator | `src/atdd/coder/validators/test_python_architecture.py` | `coder/conventions/backend.convention.yaml` |

### Conceptual Model

| Term | Definition | Example |
|------|------------|---------|
| AST similarity | Structural comparison of syntax trees ignoring identifiers | Two functions with same control flow but different var names |
| Similarity threshold | Minimum % similarity to flag | 80% = likely copy-paste |
| Scope boundary | Unit within which duplication is checked | Same wagon + same layer |

### Before State

```
Validators check: architecture layers, import boundaries
No check: redundancy within a layer
```

### After State

```
Validators check: architecture layers, import boundaries, intra-layer duplication
Flagged: "domain/calculate_total.py:15-30 is 85% similar to domain/compute_sum.py:10-25"
```

---

## Phases

### Phase 1: Python Duplication Detector

**Deliverables:**
- `src/atdd/coder/validators/test_duplication_python.py` - AST-based duplication detector

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_duplication_python.py` | New validator: AST similarity within wagon layers |

### Phase 2: TypeScript Duplication Detector

**Deliverables:**
- `src/atdd/coder/validators/test_duplication_typescript.py` - TypeScript duplication detector

**Files:**

| File | Change |
|------|--------|
| `src/atdd/coder/validators/test_duplication_typescript.py` | New validator: AST similarity for TS files |

---

## Validation

### Gate Tests

| ID | Phase | Command | Expected | ATDD Validator | Status |
|----|-------|---------|----------|----------------|--------|
| GT-001 | design | `atdd validate coach` | PASS | `src/atdd/coach/validators/test_issue_validation.py` | TODO |
| GT-002 | design | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-100 | implementation | `pytest src/atdd/coder/validators/test_duplication_python.py -v` | FAIL | feature-specific | TODO |
| GT-200 | implementation | `pytest src/atdd/coder/validators/test_duplication_python.py -v` | PASS | feature-specific | TODO |
| GT-300 | implementation | `atdd validate coder` | PASS | `src/atdd/coder/validators/` | TODO |
| GT-800 | completion | `atdd urn validate` | PASS | `src/atdd/coach/validators/test_urn_traceability.py` | TODO |
| GT-850 | completion | `atdd registry update --check` | PASS | `src/atdd/coach/commands/registry.py` | TODO |
| GT-900 | completion | `atdd validate` | PASS | `src/atdd/` | TODO |

### Success Criteria

- [ ] AST-based similarity detection works for Python function bodies
- [ ] Similarity threshold configurable (default 80%)
- [ ] Only flags within same wagon + same layer
- [ ] Reports file paths, line ranges, and similarity percentage

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | AST vs text similarity? | AST | Catches structural duplication even when variable names differ |
| 2 | Cross-wagon duplication? | Out of scope | Wagon isolation is a design principle — duplication across wagons is acceptable |

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

Origin: Gap analysis comparing ATDD automated validators vs manual code review. Duplication detection was identified as a structural analysis that reviewers perform subjectively — AST similarity makes it objective.
