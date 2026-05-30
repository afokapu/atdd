#!/usr/bin/env python3
"""Regenerate all 11 issue bodies from the canonical doc.
Keeps issue bodies in sync with docs/coach-decomposition.md as the source of truth.
"""
import json, re, subprocess
from pathlib import Path
from textwrap import indent

# Portable path resolution: this script lives at tools/decomposition/<name>.py
# So the repo root is two parents up from this file.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DOC = REPO_ROOT / "docs" / "coach-decomposition.md"

# Issue # → (slug, doc section, wave, depends_on, blocks_short, closes_short, parent_id)
CHILDREN = {
    888: dict(slug="freeze-coach-core-typed-api-and-phase-machine",
              section="13.1", wave="A",
              depends_on=[], blocks="every other child (#889–#897)",
              closes="none yet (sets up the rest)"),
    889: dict(slug="add-lifecycle-parity-and-import-discipline-tests",
              section="13.2", wave="B",
              depends_on=[888],
              blocks="#891–#897 (parity + import-discipline required-CI from here onward)",
              closes="none yet (gate for the rest)"),
    890: dict(slug="define-validator-report-and-persistence-materialization-contract",
              section="13.3", wave="B",
              depends_on=[888], blocks="#894, #895",
              closes="none yet (contract for downstream)"),
    891: dict(slug="extract-github-integrations-and-ship-projects-v2-sync",
              section="13.4", wave="C",
              depends_on=[888, 889], blocks="#894",
              closes="**#882** (Project v2 board status-field sync gap)"),
    892: dict(slug="extract-runtime-worktree-preserving-incident-defenses",
              section="13.5", wave="C",
              depends_on=[888, 889], blocks="#894",
              closes="none yet (cleans up the surface)"),
    893: dict(slug="extract-runtime-agent-control-and-close-spawn-cluster",
              section="13.6", wave="C",
              depends_on=[888, 889], blocks="#895, #897",
              closes="**#871** (stdin gap), **#872** (submit gap), **#840** (structurally — cli-return is the default control plane; TUI scrape deprecated)"),
    894: dict(slug="extract-workflow-persistence-and-events-schema",
              section="13.7", wave="D",
              depends_on=[888, 889, 890, 891, 892], blocks="#895",
              closes="none yet",
              slug_note=True),
    895: dict(slug="extract-workflow-issue-runner-and-workflow-runner-protocol",
              section="13.8", wave="E",
              depends_on=[888, 889, 890, 893, 894], blocks="#896, #897",
              closes="none yet",
              slug_note=True),
    896: dict(slug="extract-workflow-wave-runner-and-atdd-resume-cli",
              section="13.9", wave="F",
              depends_on=[888, 889, 895], blocks="none (parallel with #897 in Wave F)",
              closes="none yet",
              slug_note=True),
    897: dict(slug="split-spawn-and-final-purity-sweep",
              section="13.10", wave="F",
              depends_on=[888, 889, 893, 895], blocks="none (closes the migration)",
              closes="**The migration.** This is the final child; when merged, all done-criteria in umbrella #887 should hold. The operator manually closes the umbrella (no GitHub auto-close from this child — by intent, since a child should not close its own parent)."),
}

DOC_URL = "https://github.com/afokapu/atdd/blob/feat/decompose-coach-into-policy-workflow-runtime-integrations-validators/docs/coach-decomposition.md"

def extract_doc_section(num):
    """Extract a §13.N child's body (Scope/Out of scope/Acceptance/Closes) from the doc."""
    text = DOC.read_text()
    # match ### 13.N <anything> on the heading line, up to next ### or --- terminator
    pattern = re.compile(
        rf"^### {re.escape(num)} [^\n]*\n(.*?)(?=^### \d+\.\d+|^---\s*$)",
        re.MULTILINE | re.DOTALL
    )
    m = pattern.search(text)
    if not m:
        raise RuntimeError(f"§{num} not found in doc")
    body = m.group(1).strip()
    # Strip the metadata header (Slug, Type, Train, Depends on, Blocks lines — we add our own)
    lines = body.splitlines()
    keep = []
    skip_metadata = True
    for line in lines:
        s = line.strip()
        if skip_metadata:
            if s.startswith("**Slug:**") or s.startswith("**Type:**") or s.startswith("**Train:**") or \
               s.startswith("**Depends on:**") or s.startswith("**Blocks:**") or \
               s.startswith("**Wave:**") or s.startswith("**RISK:**") or s == "":
                continue
            else:
                skip_metadata = False
        keep.append(line)
    return "\n".join(keep).strip()

def extract_doc_title(section):
    """Extract the heading for a section like '13.1'."""
    text = DOC.read_text()
    pattern = re.compile(rf"^### {re.escape(section)} (.+)$", re.MULTILINE)
    m = pattern.search(text)
    return m.group(1).strip() if m else f"Child {section}"

def build_child_body(num, cfg):
    section = cfg["section"]
    title = extract_doc_title(section)
    doc_content = extract_doc_section(section)
    deps_str = ", ".join(f"#{d}" for d in cfg["depends_on"]) if cfg["depends_on"] else "none"
    slug_note = ""
    if cfg.get("slug_note"):
        slug_note = (
            "\n> ⚠ **Slug-vs-module divergence:** this issue's slug includes `workflow` "
            "(historical), but the destination modules are `atdd.train.*` per "
            f"[doc §3.1.1]({DOC_URL}#311-atdd-native-naming-correction) and the Scope below. "
            "Follow the scope, not the slug.\n"
        )

    body = f"""## Issue Metadata

| Field | Value |
|-------|-------|
| Issue | #{num} |
| Parent | #887 (umbrella) |
| Type | implementation |
| Slug | {cfg['slug']} |
| Train | 0001-self-compliance-validate |
| Wave | {cfg['wave']} |
| Branch | feat/{cfg['slug']} |
| Doc section | [§{section} — {title}]({DOC_URL}#{section.replace('.', '')}-{title.lower().replace(' ', '-').replace('—', '').replace('+', '').replace('`', '').replace('(', '').replace(')', '').replace('/', '').replace('.', '').replace('--', '-').strip('-')}) |
{slug_note}
## Source of truth

[`docs/coach-decomposition.md`]({DOC_URL}) is the source of truth. Read it end-to-end before starting. Any contract change MUST update the doc in this PR.

This issue implements **§{section}** of the doc. The content below is extracted verbatim from that section. If the doc and this body diverge, **the doc wins** — open a PR to update one or the other (never both at once).

## Dependencies

**Depends on:** {deps_str}
**Blocks:** {cfg['blocks']}

{doc_content}

## Per-PR requirements (apply to every child of #887)

1. Keep `tests/lifecycle/test_full_issue_parity.py` green (after #889 lands).
2. Keep `tests/architecture/test_layer_imports.py` green (after #889 lands).
3. PR description enumerates which incident defenses (I-1 to I-13 in doc §9) it preserves and references the test(s).
4. NO new I/O imports under `atdd.coach.core` (the import-discipline test confirms).
5. Compatibility shim for any moved public/semi-public symbol, marked `@deprecated(removal="3.87.0")`.
6. Update `docs/coach-decomposition.md` if any contract changes.
7. Diff scope matches this issue's Scope — no scope creep into another child's territory.

### Graph Context

```
docs/coach-decomposition.md::§{section}    → spec for this child
docs/coach-decomposition.md::§3.1.1         → Train vs TrainRunner naming
docs/coach-decomposition.md::§3.3           → dependency rules (enforced by tests/architecture/)
docs/coach-decomposition.md::§9             → incident defenses (must-preserve)
docs/coach-decomposition.md::§10            → required-CI test gates
#887                                         → umbrella; wave plan; gradual benefit map
```

---

**Worker note:** Read [`docs/coach-decomposition.md`]({DOC_URL}) end-to-end before starting. The contracts there are frozen; any change MUST come back to the umbrella for revision. The current document version is `1.2-train-amended-swept` (status: RATIFIED).
"""
    return body

def build_umbrella_body():
    return f"""## Issue Metadata

| Field | Value |
|-------|-------|
| Issue | #887 |
| Type | implementation |
| Slug | decompose-coach-into-policy-workflow-runtime-integrations-validators |
| Train | 0001-self-compliance-validate |
| Role | UMBRELLA — coordinates 10 child issues #888–#897 |
| Branch | feat/decompose-coach-into-policy-workflow-runtime-integrations-validators |
| Doc version | 1.2-train-amended-swept |
| Doc status | RATIFIED |

## Source of truth

**[`docs/coach-decomposition.md`]({DOC_URL})** is the canonical specification (~95 KB). Every child issue body, every PR description, every architectural validator MUST refer to this document and MUST NOT contradict it.

## Goal

Decompose `atdd.coach.commands.coach` into **ATDD-native train layers** with strict, validator-enforced dependency rules. **Coach-core becomes pure policy** (no I/O, no subprocess, no `gh`, no cmux, no threading). The CLI surface is unchanged.

A `TrainRunner` protocol is defined; the **JSONL-backed train runner ships as the first and only implementation**. Temporal and LangGraph are reserved as future backends behind the same seam — not built until a concrete operational need surfaces.

See **[doc §3.1.1 — Train vs TrainRunner]({DOC_URL}#311-atdd-native-naming-correction)** for the canonical naming.

## Done criteria

The migration is complete when all of:

1. `from atdd.coach.core import next_transition, evaluate_evidence, review_phase_output, merge_readiness, escalation_for` succeeds without importing any I/O module (enforced by `tests/architecture/test_layer_imports.py`).
2. `tests/lifecycle/test_full_issue_parity.py` passes in CI on every PR.
3. `tests/architecture/test_layer_imports.py` passes in CI on every PR.
4. `tests/train/test_jsonl_crash_recovery.py` passes (added at Child 9).
5. `atdd coach <N>` end-to-end uses `TrainRunner` → `coach.core` → `runtime` → `integrations` with no direct `coach.commands.coach.*` private calls.
6. Issues #840, #871, #872, #882 all closed by the migration.
7. All 13 incident defenses (I-1 through I-13 in doc §9) have explicit tests in `tests/incident_defenses/`.
8. CLAUDE.md no longer contains a duplicate phase machine.
9. Observer is a read-only consumer with no orchestration side effects.
10. The reserved `--runner temporal` and `--runner langgraph` CLI flags exist but only `--runner jsonl` is implemented.

## Wave plan

| Wave | Children | Concurrent agents | Realistic wall-clock |
|---|---|---|---|
| A | #888 | 1 | 1 day |
| B | #889, #890 | 2 | 1 day |
| C | #891, #892, #893 | **3** | 2–3 days |
| D | #894 | 1 | 1 day |
| E | #895 | 1 | 1 day |
| F | #896, #897 | 2 | 1–1.5 days |

Total: **~7–9 working days; ~2 weeks calendar**. Max parallelism: **3 agents** (Wave C). See doc §12.2 for the dependency rationale.

## Child index

| # | Wave | Child | Closes |
|---|---|---|---|
| #888 | A | Freeze Coach-core typed API + phase machine YAML | — |
| #889 | B | Lifecycle parity + import-discipline tests (required CI) | — |
| #890 | B | ValidatorReport + persistence materialization contract | — |
| #891 | C | Extract GitHub integrations + ship Projects v2 sync | **#882** |
| #892 | C | Extract `runtime.worktree` preserving incident defenses | — |
| #893 | C | Extract `runtime.agent_control` + close spawn cluster | **#871, #872, #840** (structurally) |
| #894 | D | Extract `train.persistence` + events schema | — |
| #895 | E | Extract `train.issue_runner` + TrainRunner protocol | — |
| #896 | F | Extract `train.wave_runner` + `atdd resume` CLI | — |
| #897 | F | Spawn split + final purity sweep | the migration |

> ⚠ **Slug note:** issues #894, #895, #896 carry historical slugs that include `workflow` (e.g. `extract-workflow-persistence-and-events-schema`). The destination modules are `atdd.train.*` per doc §3.1.1; the slugs are stable identifiers, not destination paths. See [doc §13 slug-vs-module divergence]({DOC_URL}#slug-vs-module-name-divergence-intentional).

## Per-PR requirements (apply to every child)

1. Keep `tests/lifecycle/test_full_issue_parity.py` green (after #889).
2. Keep `tests/architecture/test_layer_imports.py` green (after #889).
3. PR description enumerates which incident defenses (I-1 to I-13) it preserves and references the test.
4. NO new I/O imports under `atdd.coach.core`.
5. Either add a new module under the right layer OR move an existing private function — never both in the same PR.
6. Compatibility shim for any moved public/semi-public symbol, marked `@deprecated(removal="3.87.0")`.
7. Update `docs/coach-decomposition.md` if any contract changes.

## Gradual benefit

| After wave | Operator-visible benefit |
|---|---|
| A (#888) | Coach decision logic table-testable in 30ms; phase machine is data |
| B (#889, #890) | Required-CI parity + import gates protect every subsequent PR |
| **C (#891–#893)** | **`atdd coach` becomes reliable**: cli-return is default, paste-landed is gone, Project v2 board syncs. **#840 / #871 / #872 / #882 all close.** |
| D (#894) | `JsonlPersistenceStore` ships; replay determinism test passes |
| E (#895) | `TrainRunner` seam exists; coach.py visibly smaller |
| F (#896, #897) | `atdd resume <run_id>` ships; final architecture realized; observer first-class |

Highest-leverage waves: **B** (safety net) and **C** (system stops fighting itself).

## Coach operating + handoff protocols

For operator (acting as coach) and any new session inheriting the coach role, see **doc §19 (Coach operating manual)** and **doc §20 (Session handoff protocol)**.

## Rollback procedure

See doc §12.4. Per-child kill switch: #893 ships with `ATDD_USE_LEGACY_SPAWN=1` flag for one minor version.

## Stop conditions / escalation triggers

- Lifecycle parity test breaks for >24h with no forward-fix in sight → halt next-wave starts, surface to operator.
- Production dispatch broken for multiple users → revert latest merged child via `git revert`.
- A child reveals an unanticipated contract change → update `docs/coach-decomposition.md` first (separate PR), then revise the child.

### Graph Context

```
docs/coach-decomposition.md                         → SOURCE OF TRUTH (this PR introduces)
src/atdd/coach/commands/coach.py                    → 4000+ LOC monolith being decomposed
src/atdd/coach/core/                                → NEW pure-policy layer (#888)
src/atdd/train/                                     → NEW stateful runner layer (#894-#896)
src/atdd/runtime/{{worktree,multiplexer,agent_control}}/ → NEW execution layer (#892, #893, #897)
src/atdd/integrations/github/                       → NEW external adapter layer (#891)
src/atdd/validators/                                → existing; gains ValidatorReport emission (#890)
src/atdd/observer/                                  → existing; promoted to first-class read-only (#897)
tests/lifecycle/test_full_issue_parity.py           → NEW required-CI gate (#889)
tests/architecture/test_layer_imports.py            → NEW required-CI gate (#889)
.atdd/runtime/runs/<run_id>/                        → NEW per-run persistence dir (#894)
```

## Acceptance

This umbrella is COMPLETE when all 10 child issues are CLOSED via merged PRs, all done-criteria above are satisfied, and `git log` shows `docs/coach-decomposition.md` exists on main.

---

**For workers:** read [`docs/coach-decomposition.md`]({DOC_URL}) END-TO-END before picking up any child. The contracts there are frozen; any change MUST come back to this umbrella for revision.

**For operator (coach):** this issue is the orchestration hub. Children advance the standard ATDD lifecycle. Operator gates wave starts and merges per doc §19.
"""

# Build everything
out_dir = Path("/tmp/issue_bodies_v2")
out_dir.mkdir(exist_ok=True)

# Umbrella
(out_dir / "887.md").write_text(build_umbrella_body())
print(f"  ✓ wrote 887.md ({(out_dir/'887.md').stat().st_size} bytes)")

# Children
for num, cfg in CHILDREN.items():
    body = build_child_body(num, cfg)
    (out_dir / f"{num}.md").write_text(body)
    print(f"  ✓ wrote {num}.md ({(out_dir/f'{num}.md').stat().st_size} bytes)")

print("\nNow applying via gh issue edit...")
for num in [887] + list(CHILDREN.keys()):
    path = out_dir / f"{num}.md"
    r = subprocess.run(
        ["gh", "issue", "edit", str(num), "--body-file", str(path)],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print(f"  ✓ #{num} updated")
    else:
        print(f"  ✗ #{num} failed: {r.stderr[:200]}")
