# `atdd.extension.github` — Package Boundary Specification

> **Issue #1118 (Slice 3 of #1113).** Backlog materialization — this specifies the
> package boundary. It moves no conventions, changes no core, and implements no
> runtime. Source rows are mapped from `docs/coach-convention-decomposition-plan.md`
> (PR #1115); core targets are the nodes shipped in Slice 2 (PR #1117).

## 1. Identity

```
publisher : atdd            (reserved — see §6)
kind      : extension
name      : github
id        : atdd.extension.github
manifest  : extensions/atdd.extension.github/atdd.extension.yaml
home      : extensions/atdd.extension.github/   (per the author resolver)
```

The manifest declares `contract`/`targets` against ATDD core: this extension
*targets* the core coach protocol and contributes GitHub platform behavior. It does
**not** redeclare any core lifecycle/role/graph node.

## 2. The boundary in one line

```
Core owns the lifecycle. This extension maps GitHub concepts onto the lifecycle.
```

The extension never owns *when* a unit may advance or close — that is core. It owns
*how GitHub expresses* advancement and closure (labels, PR keywords, Projects, the
auto-phase workflow), and it must defer to the core nodes below.

## 3. Convention → lifecycle mapping (the heart of the boundary)

Every GitHub behavior maps onto a **core node shipped in Slice 2** — it realizes that
node on the GitHub platform, it does not restate it.

| GitHub behavior (this extension) | Maps onto core node (owns the rule) |
|----------------------------------|-------------------------------------|
| `atdd:<PHASE>` issue labels | `coach.lifecycle.phase-machine` |
| auto-phase on PR merge (`atdd-auto-phase.yml`, `closingIssuesReferences`) | `coach.lifecycle.single-step-advance-on-delivery` |
| merge-blocks-on-pre-smoke-close, closes-keyword-discipline, green-ships-without-smoke | `coach.lifecycle.no-terminal-before-lifecycle-satisfied` |
| PR runtime-artifacts-blocked (diff inspection) | `coach.execution.runtime-state-not-a-delivery-artifact` |
| gh-issue-create block + manifest registration on issue create | `coach.execution.atomic-registry-write` |
| Issue trailer interpretation (issue number) | (design_candidate `coach.execution.work-provenance`, tracked in #1122) |
| `coach.pr.base-must-be-default-branch`, `coach.pr.mass-delete-guard` | platform safety rules — extension-owned, no core counterpart |

Reading: the extension's job is the **left column**; the **right column** stays in
core and is the authority. A GitHub rule that cannot point at a core node (bottom two
rows) is genuinely platform-local and owned outright by the extension.

## 4. Source-row inventory → planned extension artifacts

From the Slice-1 plan rows classified `extension → atdd.extension.github`:

| Source (legacy) | Planned extension artifact kind |
|-----------------|---------------------------------|
| `issue.convention.yaml::github_issue_tracking` (labels, Projects, sub-issues, templates, gh deps) | conventions + templates |
| `issue.convention.yaml::status.auto_transition_on_merge.workflow` | gate + workflow asset |
| `pr.convention.yaml` rules + `phase_labels` + `auto_close_keywords` | conventions + gate (PR merge) |
| `rule-id.convention.yaml` → `coach.pr.base-must-be-default-branch`, `coach.pr.mass-delete-guard` | conventions + implementations (validators) |
| `path_shim_gh.convention.yaml` patterns | implementations (PATH shim + pre-commit) |
| `forbidden_commands.convention.yaml` → `ATDD-FORBID-GH-*`, `ATDD-LOOP-GH-PR-POLL` | implementations (command-policy patterns) |
| `commit-trailers.convention.yaml::issue-required` | convention (Issue trailer) |

Selector types (spec §7) this extension will use: `github_issue`, `github_pr`.

## 5. Owns / does not own

**Owns:** GitHub conventions; `github_issue`/`github_pr` selectors; the PR-merge gate;
implementations (gh shims, forbidden-command patterns, PR validators); issue/PR templates.

**Does not own:** core lifecycle, core graph semantics, core role semantics, any core
coach node. It references them (§3) and must break if it tries to redefine them.

## 6. Open boundary findings (for whoever advances the build)

1. **Reserved publisher.** `atdd author extension init --extension atdd.extension.github`
   is **rejected** — the `atdd` publisher is reserved for official packages and the
   public CLI exposes no allow-reserved path. Consequence: the official GitHub
   extension is authored either (a) in the dedicated `atdd-extensions` repo where
   official `atdd.*` packages live, or (b) behind a reserved-bypass authoring path if
   it is to live in this repo. **This must be decided before scaffolding.** (Same
   constraint applies to the #1119–#1121 workspace packages.)
2. **Graph composition unproven.** Core↔extension edges (`core coach node → github
   node`) are not yet allowed in the core graph (Slice-2 guardrail). Extension edges
   live in `extensions/atdd.extension.github/relationships.yaml` with graph_id
   `atdd.extension.github.relationships`; how the extension graph composes with the
   core graph is a prerequisite design (cf. #1122 `coach.extension.*`).
3. **No runtime move in this issue.** Legacy `*.convention.yaml` stay as the source of
   truth until a consuming loader reads extension-owned nodes; moving them is a
   separately-scoped follow-up, not this issue.

## 7. Acceptance (this issue)

- [x] package boundary is specified (§1–§5)
- [x] source rows are mapped (§4)
- [x] no core files are changed (this is a `docs/` artifact only)
- [x] no runtime behavior is implemented (scaffolding blocked by §6.1; deferred)
- [x] migration blockers surfaced for the build phase (§6)
