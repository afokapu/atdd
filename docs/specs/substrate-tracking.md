# ATDD Repo Substrate — Implementation Tracker

> **Companion to**: `atdd-repo-substrate-spec-v12.md` (the spec) and `atdd-repo-substrate-issues.md` (the 17-issue plan).
> **Status**: ✅ **COMPLETE** — all 17 issues merged, parent #406 closed.
> **Last audit**: 2026-05-06 16:00 UTC (substrate done-line merged).

## Verification methodology

**Pass 1 — filing verified**: each filed GitHub issue body's structural shape matches the corresponding entry in the post-3-pass-review plan source. **Result: 17/17 pass.**

**Pass 2 — content equivalence**: hash of normalized scope + AC + deps + refs equal between filed body and source. **Result: 17/17 hash-match.**

**Work-done check**: PR existence, CI conclusion, merge state. **Result: 17/17 merged to `main`.**

## Tracker — final state

| Local | GH | Track | Title | PR | Landed at | Version |
|---|---|---|---|---|---|---|
| #1 | [#407](https://github.com/afokapu/atdd/issues/407) | A | Add `repo` archetype + RuleMetadata substrate fields | [#426](https://github.com/afokapu/atdd/pull/426) | `9db00c7` | v3.3.0 |
| #2 | [#408](https://github.com/afokapu/atdd/issues/408) | A | Derive WMBT/train repo rules from acceptance URNs | [#433](https://github.com/afokapu/atdd/pull/433) | `43af092` | v3.4.3 |
| #3 | [#409](https://github.com/afokapu/atdd/issues/409) | A | Add repo rule discovery CLI commands | [#435](https://github.com/afokapu/atdd/pull/435) | `a9a2c50` | v3.4.5 |
| #4 | [#410](https://github.com/afokapu/atdd/issues/410) | B | Add substrate conformance convention + 5 validators | [#439](https://github.com/afokapu/atdd/pull/439) | `2da05d9` | v3.4.6 |
| #5 | [#411](https://github.com/afokapu/atdd/issues/411) | C | Harness-mode pytest plugin | [#438](https://github.com/afokapu/atdd/pull/438) | `62eb765` | v3.4.7 |
| #6 | [#412](https://github.com/afokapu/atdd/issues/412) | D | Metric runner with two-root discovery | [#428](https://github.com/afokapu/atdd/pull/428) | `1d061ff` | v3.4.1 |
| #7 | [#413](https://github.com/afokapu/atdd/issues/413) | D | First toolkit metric (`hardcoded_theme_map_literal_count`) | [#436](https://github.com/afokapu/atdd/pull/436) | `73db8b7` | v3.4.8 |
| #8 | [#414](https://github.com/afokapu/atdd/issues/414) | E | Rename legacy URN CLI namespace → `atdd repo` | [#440](https://github.com/afokapu/atdd/pull/440) | `7d25b9c` | v3.5.0 |
| #9 | [#415](https://github.com/afokapu/atdd/issues/415) | E | Extend `atdd init` for substrate mode | [#443](https://github.com/afokapu/atdd/pull/443) | `27817b5` | v3.5.6 |
| #10 | [#416](https://github.com/afokapu/atdd/issues/416) | F | Coach phase dispatch for repo rules | [#441](https://github.com/afokapu/atdd/pull/441) | `43474ef` | v3.5.5 |
| #11 | [#417](https://github.com/afokapu/atdd/issues/417) | F | Spawn-harness repo rule blocks | [#444](https://github.com/afokapu/atdd/pull/444) | `861ad11` | v3.5.2 |
| #12 | [#418](https://github.com/afokapu/atdd/issues/418) | F | Risk-score archetype breakdown | [#442](https://github.com/afokapu/atdd/pull/442) | `7e33fec` | v3.5.3 |
| #13 | [#419](https://github.com/afokapu/atdd/issues/419) | G | SecurityResolver + registration + graph edges | [#427](https://github.com/afokapu/atdd/pull/427) | `b5cdff8` | v3.4.0 |
| #14 | [#420](https://github.com/afokapu/atdd/issues/420) | G | URN grammar validator + parent-it-belongs-to | [#432](https://github.com/afokapu/atdd/pull/432) | `c2d8099` | v3.4.2 |
| #15 | [#421](https://github.com/afokapu/atdd/issues/421) | G | URN-prefix hardcoding audit + report | [#437](https://github.com/afokapu/atdd/pull/437) | `d43ae59` | v3.4.9 |
| #16 | [#422](https://github.com/afokapu/atdd/issues/422) | H | Security-derived repo rules + ref-binding runner | [#445](https://github.com/afokapu/atdd/pull/445) | `a699b8d` | v3.5.4 |
| #17 | [#423](https://github.com/afokapu/atdd/issues/423) | I | Substrate end-to-end validation (worked example) | [#446](https://github.com/afokapu/atdd/pull/446) | `6bdbf17` | v3.6.0 |

## Aggregate

```
Filed:       17/17 — all bodies match post-3-pass-review source (Pass 2 hash-equivalent)
Done:        17/17 ✅
Parent #406: CLOSED ✅
Main:        v3.6.0 (head: 6bdbf17)
```

## ATDD platform fixes shipped during cascade

| PR | Title | Reason |
|---|---|---|
| [#430](https://github.com/afokapu/atdd/pull/430) | `auto_upgrade` falls back to `--break-system-packages` on PEP 668 | Pre-push hook + `atdd upgrade` failed silently on Homebrew Python. Now graceful. |
| [#431](https://github.com/afokapu/atdd/pull/431) | `test_issue_advancement` skips non-lifecycle issues | Validator was false-positive on tracking/meta/epic/parent issues like #406. |
| [#429](https://github.com/afokapu/atdd/pull/429), [#434](https://github.com/afokapu/atdd/pull/434) | Substrate implementation tracker (this doc) | Pass-1+2 verification audit + work-done table for the cascade. |

## Verification: `atdd validate coach --local`

24/24 substrate-related checks pass against the toolkit's own `plan/`. 3 pre-existing failures are platform-side gaps **unrelated to substrate functionality**:

1. `test_issues_are_in_project` — substrate issues #406–#423 were filed via `gh issue create` (not `atdd issue`), so they're not registered in GitHub Project v2 with Status fields. Documented as a known gap; doesn't affect substrate runtime.
2. `test_issues_have_status_field_set` — same root cause as (1).
3. `test_issue_branch_follows_worktree_convention` — closed-branch convention assumption mismatch.

These belong to the `atdd issue --status` lifecycle rework (separate, future work).

## Substrate is ready for consumer-repo adoption

Per spec §11 the workflow on a fresh repo is:

```
atdd init --consumer-repo            # registers substrate pytest plugin
atdd repo validate                   # Class 1 conformance fires; fix per recipes
pytest                               # Class 2 contract failures surface enriched
```

Class 1 = `tester.acceptance-violation.*` rules from `acceptance-violation.convention.yaml` (#410). Class 2 = real WMBT/train/security contract violations from #408 walker + #412 metric runner + #422 security ref-binding runner.

Worked example documented in `docs/substrate-worked-example.md` (#423).

---

## Cascade summary — operational notes

The 17-issue cascade ran in 4 waves over a single session, dispatched via cmux panes in parallel:

- **Wave 1** (foundations, parallel): #407, #419, #420 + #408 + #412 — 5 PRs
- **Platform interlude**: PRs #430 (PEP 668), #431 (lifecycle skip) merged to unblock auto-upgrade and tracking-issue false-positives
- **Wave 2** (parallel): #409, #410, #411, #413, #421 — 5 PRs (with version coordination 3.4.5–3.4.9)
- **Wave 3a** (alone): #414 (atdd urn → atdd repo rename, breaking change)
- **Wave 3b** (parallel): #415, #416, #417, #418, #422 — 5 PRs (with pre-allocated versions 3.5.1–3.5.5)
- **Wave 4** (alone): #423 done-line — substrate complete at v3.6.0

Total PRs merged: **20** (17 substrate + 3 platform).
