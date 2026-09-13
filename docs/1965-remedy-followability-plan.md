# 1965 — A convention node's remedy must be followable

PLANNED-phase record. Settles the issue's one open decision, states the
validator design, and records one finding the issue's lab did not adjudicate.

## Decision #3 — which root is authoritative (was: "Open — needs the operator")

**Resolved: the checkout only, platform-gated.**

The issue framed this as "the checkout or site-packages", because `atdd rules
show` reads the installed package while validators read the checkout, and the
two disagreed about a locally-modified node in #1958. Measured here:

| Root | Convention nodes | `plan/` | `docs/` | `.atdd/` |
|---|---|---|---|---|
| checkout (`src/atdd/…`) | 366 (316 in `nodes/`) | yes | yes | partial in a worktree |
| installed package (pipx venv) | 366 (identical file set) | no | no | no |

The operator's reframing settled it: the rule must behave correctly **in a
consumer repo that installed ATDD**. There, nodes arrive only from the installed
package, and the paths those nodes quote are paths in the *toolkit* repo
(`src/atdd/planner/validators/test_…py`, `plan/_lego/…`). They will never exist
in a consumer's tree, so a validator running there would flag nearly every path
as absent — a false-positive flood in someone else's repo, for defects they
neither caused nor can fix.

That is the exact failure `is_atdd_source_repo()` exists to prevent
(`src/atdd/coach/utils/repo.py:395` — "Otherwise those tests leak into consumer
`atdd validate coder` runs and fail with assertion errors against toolkit
fixture data", #272/#276). So the validator is marked `platform` and skips
unless it is in the ATDD checkout. Once it only ever runs where the checkout
exists, the root question answers itself: the checkout is the only root with a
`plan/` or `docs/` to resolve against.

Drift between the installed copy and the checkout is **not** checked here. The
two file sets are identical today (diffed: 366 = 366), nothing else in the repo
checks it, and folding a second concern into this validator would let it fail
for a reason unrelated to remedies.

### Correction to a briefing note

The briefing states `is_atdd_source_repo()` is false *in a worktree*. The cause
is the **interpreter**, not the worktree:

| Interpreter | `atdd` package dir | `is_atdd_source_repo()` |
|---|---|---|
| `uv run` (worktree's own editable install) | `…/worktrees/feat-…/src/atdd` | **True** |
| pipx CLI | `…/pipx/venvs/atdd/…/site-packages/atdd` | **False** |

`pkg_dir.relative_to(repo_root)` fails for the pipx venv. So `atdd validate
planner` deselects `platform` (the 217 `could_not_check`), but `pytest
src/atdd/planner/validators` under `uv run` runs them. A `platform` marker is
therefore safe: the validator runs in CI and under the pre-push verification
command, and is correctly inert in consumer repos.

## The defects

Reproduced the lab's classifier in this worktree: 137 provenance, 34
illustrative, 22 operative (14 distinct) — matching the issue exactly.

Triaging the 14 against the issue's verdict table leaves **five unaccounted
for**. Four are tokenizer artifacts, and one is a real defect:

| Candidate | Verdict | Why |
|---|---|---|
| `tests/ADRs` | not a defect | prose disjunction — "routed to tests/ADRs" means *tests or ADRs*; the slash is "or" |
| `plan/test/code` | not a defect | same — "the plan/test/code themes align to the planner/tester/coder archetypes" |
| `src/atdd/planner/conventions/nodes/planner` | not a defect | truncated placeholder. The real text is `…/planner.<artifact>.definition.convention.yaml`; the lab's token charset stops at `<`, so truncation defeated its own placeholder guard |
| `contracts/theme/seg1/seg2/aspect/variant.schema.json` | not a defect | illustrative, as the issue says — but it sits in `operational_guidance`, so the lab's key-based classifier mis-bucketed it as operative |
| `tests/platform_validation/` | **DEFECT (6th)** | see below |

### The sixth defect

`planner.interface.tests-subdirectory`, term `platform_validation_tests`:

> Enforcement lives in platform validation tests under `tests/platform_validation/`.
> The contracts leaf rule is checked by `test_contract_directories_have_tests_subdirectory`
> and the telemetry leaf rule by `test_telemetry_directories_have_tests_subdirectory`.

Verified: `tests/platform_validation/` exists in neither the worktree nor
`main`, and **neither named test function exists anywhere in the repo**. The
actual enforcement is `test_contract_tests_subdirectory::test_contract_tests_subdirectory`,
which the same node already declares in `implementation.ref`. So this remedy is
unfollowable three times over — one absent directory and two absent test names.

This is repaired as a sixth item. It is not scope creep: the issue's Done-when
is "Every remedy a convention node states can be followed", and a `strict` gate
at zero cannot pass while it stands. The alternative — excluding it — would be
wrong, because it is a genuine defect rather than one of the four exclusion
classes.

### The repairs

| # | Node | Names | Becomes |
|---|---|---|---|
| 1 | `planner.acceptance.authoring-guidelines` | `plan/_lego/acceptance-metrics.yaml` | drop the pointer; the catalog is `conventions:criteria:metrics`, already named in the same node's `constraints` |
| 2 | `planner.wmbt.must-have-smoke-acceptance` | `src/atdd/planner/validators/test_wmbt_has_smoke_acceptance.py` | `…/test_wmbt_smoke_acceptance_rule_registered.py` |
| 3 | `coach.lifecycle.no-terminal-before-lifecycle-satisfied` | `.atdd/labels.yaml` | drop — no such file; the labels are read from the issue itself |
| 4 | same node | `atdd issue <issue> --status SMOKE` | `atdd coach transition <issue> SMOKE` |
| 5 | `planner.plan.confirm-binds-an-issue` | `atdd issue open` | `atdd coach issues open` |
| 6 | `planner.interface.tests-subdirectory` | `tests/platform_validation/` + 2 absent test names | the node's own `implementation.ref` validator |

> **Superseded during the work — repair #1 is no longer ours.** #1971 (PR #1974)
> landed on `main` while this branch was at GREEN and fixed the same defect,
> replacing the dangling path with `planner.criteria.metric-mapping`. That is a
> better target than the `conventions:criteria:metrics` address this branch had
> used, because it names the node #1958 actually bound rather than the catalog
> address. The rebase resolved the conflict by taking `main`'s version outright
> and dropping our competing edit. Five repairs are ours; the sixth
> (`tests/platform_validation/`) is the one this issue's lab did not adjudicate.
>
> The strict gate is unaffected: their wording carries no path token at all, so
> the scanner sees nothing to resolve. Two rules independently converging on the
> same defect is the measurement holding up — it was a real dangling pointer,
> and someone else reading a different issue reached the same verdict.

Both replacement verbs are confirmed live by their own `--help`: `atdd coach
issues` says "the coach-archetype replacement for `atdd issue open` / `atdd
issue <N>`", and `atdd coach transition` says "…replacement for `atdd issue <N>
--status <TO>`". Exactly 2 nodes contain `atdd issue `, matching the issue's
verb count.

## Validator design

Files:

| File | Role |
|---|---|
| `src/atdd/planner/validators/remedy_followability.py` | pure scanner — tokenizer, the exclusion rules, retired-verb table |
| `src/atdd/planner/validators/test_convention_remedies_are_followable.py` | live validator; `platform` + `planner`; `assert_disposition_satisfied` |
| `src/atdd/planner/validators/tests/test_remedy_followability_exclusions.py` | fault injection, one case per exclusion rule |
| `src/atdd/planner/conventions/nodes/planner.convention.remedy-must-be-followable.convention.yaml` | the node — `strict`, severity 3 |
| `src/atdd/coach/graph/relationships.yaml` | one edge, so the new node is not an orphan |

The node and its validator land in **one commit**: `rule-id.convention.yaml`
`rule_schema.conditional` requires a validator when `disposition ∈ {strict,
suppress-and-clean, advisory}` and forbids one when `documentation-only`. There
is no legal intermediate. Sibling model: `planner.relationship.no-orphan-nodes`
— also `strict`, severity 3, also a rule *about* convention nodes.

### Tokenizer

The lab's tokenizer is too loose to gate `strict` at zero — it produced the four
artifacts above. Tightened:

1. A candidate must **end in a file extension or a `/`**. This alone retires
   `tests/ADRs` and `plan/test/code`, which are prose disjunctions with neither.
2. The token charset **includes** `<>{}*`, so a placeholder is seen and rejected
   rather than silently truncated in front of it. This is the lab's bug, fixed.
3. Strings introduced by `Formula:` are schematic templates, not pointers —
   which retires the `contracts/theme/seg1/…` case at its cause rather than by
   naming the token.

### Exclusion rules

Six, each keyed off text that is actually present, each pinned by a
fault-injection test:

| Rule | Detector | Cases |
|---|---|---|
| provenance | keypath passes through `legacy_path` | 137 |
| illustrative | keypath passes through `examples`/`values`/`positive`/`negative` | 34 |
| schematic formula | the string is introduced by `Formula:` | `contracts/theme/seg1/…` |
| excluded mechanism | token negated (`no <token>`) or in a string carrying `excluded mechanisms:` / `What is NOT` | `plan/_meta.yaml` |
| conditional | token inside an existence guard — `if … exists`, `when present`, `if present` | `telemetry/_tracking_manifest.yaml` |
| gitignored runtime | **`git check-ignore`** | `.atdd/runtime/`, `.atdd/state/state.sqlite`, `.atdd/smoke-evidence/` |
| historical record | token in a clause declaring it retired (`retired`, `removed`, `superseded`) | `.atdd/manifest.yaml` |

Two notes on the design:

- **`git check-ignore` rather than a hardcoded list.** Asking git is principled
  and self-maintaining, and it separates exactly the three runtime cases from
  every other candidate — verified: those three are `IGNORED`, and
  `.atdd/labels.yaml`, `plan/_lego/…`, `tests/platform_validation/`,
  `.atdd/manifest.yaml` and `plan/_meta.yaml` are all `not ignored`. A literal
  list would have gone stale the first time a runtime path moved.
- **The historical-record rule is what distinguishes defect 3 from exclusion 7.**
  `coach.execution.atomic-registry-write` says "*#1270 Slice G **retired** the
  `.atdd/manifest.yaml` mirror*" — past tense, marked retired. The
  `.atdd/labels.yaml` defect says the labels "**live under** `.atdd/labels.yaml`"
  — present tense, a pointer. The tense is the signal, and encoding it keeps the
  rule from excusing the very defect it exists to catch.

The issue's own accounting of exclusions is inconsistent — In Scope and the
verdict table say four, Success Criteria lists five (naming provenance and
illustrative, dropping the historical parenthetical). All six above are encoded,
which satisfies both readings.

### Disposition

`strict`, per Decision #1: at n=6 the remedy is affordable, so the rule is an
obligation rather than a reporter. This is the difference from #1958 (369 of 473
failing) and #1943 (101 of 229), both of which had to settle for `advisory`.

## RED plan

Failing first, proven against current code before any source changes:

1. Six assertions, one per defect, each naming the absent file or dead verb.
2. One assertion per exclusion rule, proving the rule does **not** fire on its
   legitimate case (fault injection: the clean baseline and the fault in one run,
   per the `no_orphan_nodes` model).
3. A corpus assertion: zero unfollowable remedies across all 316 nodes.

Expected RED failure: `ModuleNotFoundError` on
`atdd.planner.validators.remedy_followability`, plus the six defect assertions.

## Verification

Per the briefing, `atdd validate planner --local --skip-api` silently reports
217 validators as `could_not_check`, which is not a pass. Before pushing:

    pytest src/atdd/planner/validators -q -m "not github_api"

No new SMOKE acceptance is introduced, so `docs/smoke-audit.md` needs no row.
The live validator is unanchored, following
`test_wmbt_smoke_acceptance_rule_registered.py` and `test_hierarchy_coverage.py`
— there is no planned WMBT for this repair, so a bidirectional acceptance
binding would be artificial. That is recorded in the validator's docstring.
