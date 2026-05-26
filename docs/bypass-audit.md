# Bypass Flag Audit — E026 + E030

**Issue:** #851 — Audit And Retire Bypass Flag Proliferation  
**E026 audit date:** 2026-05-24 (partial retirement: 3 flags, 5 kept with ATDD_BYPASS_REASON)  
**E030 full retirement date:** 2026-05-26 (all remaining flags retired unconditionally)  
**WMBT:** wmbt:govern-lifecycle:E026, wmbt:govern-lifecycle:E030  
**Baseline after E030:** 0 ATDD_SKIP_* flags in hooks (meta-guard enforces zero)

---

## Problem Summary

As of v3.82.1, every gate ATDD adds had its own `ATDD_SKIP_*` escape hatch.
E026 (2026-05-24) retired 3 flags and locked 5 others behind `ATDD_BYPASS_REASON`
with audit-jsonl logging. E030 (2026-05-26) fully retires the remaining 5 flags
after a lived incident confirmed that audit-logged bypasses are no-different from
un-audited ones in practice: an ATDD861 worker chained `ATDD_SKIP_POSTCOMMIT=1`
and `ATDD_SKIP_PREPUSH_VALIDATE=1` to push, staging ~30 `.atdd/` deletions that
the bypassed gates would have caught. Operator directive (2026-05-26):
"the skip are the issues — they were useful when fixing coach but shouldn't exist at all."

**Emergency bypass (only sanctioned escape):** `atdd emergency --reason "<reason>"`
Creates `.atdd/EMERGENCY_BYPASS` for 5 minutes. Not an env var; not chainable.

---

## Complete Bypass Inventory

Flags audited: all `ATDD_SKIP_*` vars found in
`src/atdd/coach/templates/hooks/` as of the audit date.

Advisory threshold vars (`ATDD_MAX_*`) and CI-only main-branch guards
(`ATDD_ALLOW_MAIN_*`) are **excluded** — they are not enforcement bypasses.

| Flag | Hook file | Gate bypassed | Introduced | E026 decision | E030 decision |
|------|-----------|---------------|------------|---------------|---------------|
| `ATDD_MAX_UNCOMMITTED` | `pre-push` | Advisory threshold (never blocks) | older | **KEEP (advisory)** | **KEEP (advisory)** |
| `ATDD_SKIP_ALL_GATES` | `pre-push` | Meta-bypass for all pre-push flags | #845 | **RETIRE** | — |
| `ATDD_SKIP_BARE_CHECK` | `pre-push` | core.bare contamination guard (Wave 12) | #629 | KEEP (audited) | **RETIRE (E030)** |
| `ATDD_SKIP_MANIFEST_CHECK` | `pre-commit` | Branch-in-manifest registration check | older | KEEP (audited) | **RETIRE (E030)** |
| `ATDD_SKIP_MASSDELETE` | `commit-msg` | Mass-delete guard (>50 files / >10k lines) | #629 | KEEP (audited) | **RETIRE (E030)** |
| `ATDD_SKIP_POSTCOMMIT` | `post-commit` | Blast-radius validator (advisory, never blocks) | #611 | **RETIRE** | — |
| `ATDD_SKIP_PREPUSH_VALIDATE` | `pre-push` | Blast-radius validator sweep | older | KEEP (audited) | **RETIRE (E030)** |
| `ATDD_SKIP_REGISTRY_CHECK` | `pre-push` | Registry mirror drift gate | E021 | **RETIRE** | — |
| `ATDD_SKIP_VERSION_GATE` | `pre-push`, `pre-merge-commit` | Version gate | #776 | KEEP (audited) | **RETIRE (E030)** |

**E026 audit outcome (2026-05-24):** Retired 3 flags; kept 5 with mandatory ATDD_BYPASS_REASON.  
**E030 full retirement (2026-05-26):** Retired all remaining 5 flags. Zero ATDD_SKIP_* in hooks.

---

## Retired Flags (3)

### 1. `ATDD_SKIP_ALL_GATES`

**Original justification (#845):** Reduce friction by consolidating 4 flags into 1.

**Why retiring:** The consolidation was additive, not replacement. Individual
flags still work independently; the meta-bypass lowered the cost of bypassing
everything without retiring a single gate. This is the structural pattern the
issue was designed to break. Retiring forces operators to use an explicit flag
name (each documented here) rather than silencing all enforcement in one token.

**File affected:** `src/atdd/coach/templates/hooks/pre-push`

---

### 2. `ATDD_SKIP_POSTCOMMIT`

**Original justification (#611):** Allow skipping advisory post-commit validators
in cases where the hook output was noisy.

**Why retiring:** The post-commit hook is advisory — it **always exits 0**
regardless of validator output. A bypass of a non-blocking hook is meaningless
(it only suppresses informational output). Removing the env-var check does not
add any blocking behavior. Operators who want silence from the hook already get
silence from `ATDD_SKIP_POSTCOMMIT` — after retirement, the hook runs and they
get the same advisory output they would have gotten before CI added the hook.

**File affected:** `src/atdd/coach/templates/hooks/post-commit`

---

### 3. `ATDD_SKIP_REGISTRY_CHECK`

**Original justification (E021):** Allow bypassing the registry drift gate when
mirrors were known to be stale.

**Why retiring:** E023-UNIT-003 (shipped with v3.82.0) implemented auto-heal:
when drift is detected, the pre-push hook now automatically runs
`atdd registry update --yes` and re-stages the mirror files, then continues the
push. The manual bypass is now redundant — the gate handles its own remediation.

**File affected:** `src/atdd/coach/templates/hooks/pre-push`

---

## Kept Flags (5) — Require `ATDD_BYPASS_REASON`

Each of the following flags remains in the codebase but is now **guarded**: when
used without `ATDD_BYPASS_REASON="<reason>"` a warning is printed to stderr.
When used with `ATDD_BYPASS_REASON`, an audit event is appended to
`.atdd/bypass-audit.jsonl`.

### 4. `ATDD_SKIP_BARE_CHECK`

**Justification for keeping:** Safety-critical guard for the Wave 12
contamination class (PRs #625/#627: 220k-line / 1,277-file mass-deletion). A
worktree with `core.bare=true` silently mass-deletes files. The bypass exists so
an operator who genuinely created a bare clone can push without false-positive
blocking — but this is rare enough to warrant a logged reason.

**When legitimate:** Testing bare-clone behavior; recovering from a hook-gone-wrong
state while investigating, not during routine development.

---

### 5. `ATDD_SKIP_MANIFEST_CHECK`

**Justification for keeping:** Bootstrap commits before `atdd init` runs
legitimately cannot have the branch registered in `.atdd/manifest.yaml` (the
manifest doesn't exist yet). E012 added a self-healing exception for the
`atdd init` commit itself; this flag covers other bootstrap scenarios.

**When legitimate:** First commit on a new repo before `atdd init`; emergency
hotfix branches created outside the CLI before retroactive registration.

---

### 6. `ATDD_SKIP_MASSDELETE`

**Justification for keeping:** The mass-delete guard (commit-msg hook) blocks
commits deleting >100 files or >10,000 lines without decommission-prefix or
`[mass-delete-approved]` in the body. Legitimate large-scale removals that don't
fit the title prefixes (e.g. generated-file cleanup with a non-standard message)
need this escape.

**Note:** Two lower-friction escapes already exist without using `ATDD_SKIP_MASSDELETE`:
- Commit title prefix: `chore(decom`, `refactor(remove`, or `chore(archive)`
- Commit body token: `[mass-delete-approved]`

Prefer these over the env-var bypass.

---

### 7. `ATDD_SKIP_PREPUSH_VALIDATE`

**Justification for keeping:** The blast-radius pre-push validator can fail on
stale acceptances in files not touched by the current push (i.e., the failing
acceptance was authored by a previous session and hasn't been updated yet). Until
the underlying validator false-positive rate is reduced, this escape is needed.

**When legitimate:** Pushing to unblock a wave while a separate issue resolves
the stale acceptance; not for silencing real failures.

---

### 8. `ATDD_SKIP_VERSION_GATE`

**Justification for keeping:** E023-UNIT-002 (minimum_version gate refinement)
is not yet fully landed. Until the version gate compares against the repo's
declared `minimum_version` (not PyPI latest), the gate can block operators who
just released a new version but haven't yet installed it locally.

**When legitimate:** During active releases; short-lived until E023-UNIT-002 ships.

---

## Regression Guard

A meta-guard validator (`src/atdd/coach/validators/test_e026_bypass_inventory_guard.py`)
scans all hook source files for `ATDD_SKIP_*` vars and fails if the count exceeds
the **audited baseline of 0** (updated from 5 → 0 by E030). The count excludes
`ATDD_MAX_*` advisory thresholds and `ATDD_ALLOW_MAIN_*` CI-only guards.

**There are no legitimate new bypass flags.** If a gate is too strict, fix the gate
predicate. For genuine one-off emergencies: `atdd emergency --reason "<reason>"`.

---

## Audit Outcome

### E026 (2026-05-24)
- **Flags before audit:** 8 (7 from issue inventory + ATDD_SKIP_MASSDELETE discovered)
- **Flags retired:** 3 (ATDD_SKIP_ALL_GATES, ATDD_SKIP_POSTCOMMIT, ATDD_SKIP_REGISTRY_CHECK)
- **Flags kept with ATDD_BYPASS_REASON:** 5
- **Net reduction:** 37.5% (8 → 5)

### E030 (2026-05-26)
- **Flags before retirement:** 5 (ATDD_SKIP_BARE_CHECK, ATDD_SKIP_MANIFEST_CHECK, ATDD_SKIP_MASSDELETE, ATDD_SKIP_PREPUSH_VALIDATE, ATDD_SKIP_VERSION_GATE)
- **Flags retired:** 5 (all remaining)
- **Bypass mechanism removed:** ATDD_BYPASS_REASON + bypass-audit.jsonl (no longer needed)
- **Emergency path added:** `atdd emergency --reason "<reason>"` (single-use, not an env var)
- **Total reduction (E026+E030):** 100% (8 → 0)
- **Behavioral outcome:** No env-var bypass path exists; every gate is unconditional

---

## Postmortem: The #845 Irony

\#845's stated scope was substrate-friction reduction. It shipped
`ATDD_SKIP_ALL_GATES` — which the session celebrated as "single env var replaces
the 3-cocktail." But that was the structural problem: **bundling bypasses does not
retire them.** The individual flags still existed; the "consolidation" added one
MORE flag on top. Per the audit count, the inventory went from 6 to 7, not from
6 to 1. This is the well-intentioned fix that *looks* like consolidation but is
structurally additive — worth naming as a postmortem datum when designing future
gate-bypass contracts.

The correct fix (this issue): retire individual flags where the underlying gate
has matured, and require documented reasons for those that remain.
