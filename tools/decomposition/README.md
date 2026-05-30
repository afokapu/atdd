# `tools/decomposition/`

Maintenance and verification scripts for the **Coach Decomposition** project (umbrella issue **#887**; see [`docs/coach-decomposition.md`](../../docs/coach-decomposition.md)).

These scripts keep the GitHub issues (#887 + #888–#897) and the source-of-truth doc in lock-step. Any time the doc changes contracts or a child's scope, re-run `regen_issue_bodies.py` followed by the three verifiers — drift between doc and issues is treated as a bug.

All scripts are path-portable: they resolve the doc as `../../docs/coach-decomposition.md` relative to their own location, so they work on any worktree (including a future post-merge `main`).

## Scripts

| Script | Purpose | Frequency |
|---|---|---|
| `regen_issue_bodies.py` | Re-extract all 11 issue bodies (#887 umbrella + #888–#897 children) from the doc and apply via `gh issue edit`. Use after any change to doc §13.X, §12.1, or §12.2. | Whenever doc changes contracts/scopes |
| `verify_issues.py` | Pass 1 — structural verification. Checks: Branch fields clean (no backticks), Train + Type fields set, Graph Context present, parent #887 referenced, dep graph DAG consistent (forward `Depends on` matches inverse `Blocks`), all `Closes` targets are real existing issues. Exits with a finding list. | Before/after every doc or issue change |
| `pass2_review.py` | Pass 2 — content review. Heuristic checks on each child's Scope and Acceptance: vague terms (`clean`, `proper`, etc.), missing binary signals, missing bulleted criteria. Exits with a finding list. | Before/after every doc or issue change |
| `bidirectional_check.py` | Phase 5 — bidirectional doc ↔ issue consistency. Verifies each child's body matches its doc §13.X verbatim (line-by-line), umbrella's wave plan matches doc §12.2, umbrella's done-criteria matches doc §12.1, child index covers all 10 children. | After every issue regeneration |
| `fix_doc_workflow_refs.py` | Historical record of the post-team-amendment sweep (2026-05-30) that replaced 23 leftover `workflow.*` references with `train.*`. Kept for audit trail; **do not re-run** on the current doc. | Never (historical) |
| `fix_issues.py` | Historical record of a small fix that added transitive deps (#888, #889) to #894–#897 and rephrased #897's Closes section to avoid auto-closing umbrella #887. Superseded by `regen_issue_bodies.py`. | Never (historical) |

## Typical workflow

After editing the doc (e.g., tightening an acceptance criterion in §13.X):

```bash
cd /path/to/<umbrella-worktree-or-main>

# 1. Re-flow the doc into all issue bodies
python3 tools/decomposition/regen_issue_bodies.py

# 2. Run all three verifiers
python3 tools/decomposition/verify_issues.py        # structural
python3 tools/decomposition/pass2_review.py          # content
python3 tools/decomposition/bidirectional_check.py   # doc ↔ issues

# 3. If any verifier reports findings, fix the doc (source of truth),
#    re-run step 1, then re-verify.
```

Each script prints a `SUMMARY: N finding(s)` line. Clean state is **0 findings across all three**.

## Authoring rules

If you add a new child issue or change wave structure:

1. Update the doc first (§12.2 wave plan + a new §13.X child section).
2. Add an entry to `CHILDREN` in `regen_issue_bodies.py`.
3. Add the corresponding expected-dep/expected-blocks entry to `EXPECTED` in `verify_issues.py`.
4. Add the issue number to `CHILDREN` in `bidirectional_check.py`.
5. Run the typical workflow above.

## Dependencies

- Python 3.10+
- `gh` CLI authenticated to the repo
- The doc at `../../docs/coach-decomposition.md` (script auto-resolves)

## Related

- **Doc:** [`docs/coach-decomposition.md`](../../docs/coach-decomposition.md)
- **Umbrella issue:** [afokapu/atdd#887](https://github.com/afokapu/atdd/issues/887)
- **Coach operating manual:** doc §19
- **Session handoff protocol:** doc §20
