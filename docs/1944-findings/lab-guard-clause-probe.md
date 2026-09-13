# #1944 — lab: guard clauses against the nesting and silent-swallow ratchets

Scratch branch `lab/1944-guard-clause-probe` off `origin/main` at `192e85cd`, no PR.
Ten functions, five files. Every number below came out of the exact CI command
or an executed probe; none is inferred.

```
atdd enforce --repo-root . --paths src/atdd --ratchet .atdd/enforce-ratchet.yaml
```

## Summary of what changes about the issue as written

| Issue says | Actually |
|---|---|
| `coach-silent-swallow` at 230 is the largest debt in the repo | 219 handlers, **219 of them already pragma-suppressed, 0 unsuppressed** — the ratchet counts annotation, not exposure |
| reduce `complexity-nesting` from 162 | **66 are genuinely nested; 96 are continuation-line indentation** a guard clause cannot touch |
| the file-length trade is real (#1929 `plan_session.py` 503 → over 500) | the rule counts **files over 500, not lines** — the trade only bites on a crossing, and exactly one file in the tree is within 21 lines of one |
| `cli.py::main` F(144) is "almost certainly a dispatch chain" | confirmed: 2395 lines, 113 `if`, 107 `return`, dispatch on `args.command` + 5 sub-command attributes |

The hypothesis holds. The targets it was aimed at do not.

---

## 1. The measured result

| rule | baseline | before | after | Δ |
|------|---------:|-------:|------:|--:|
| `coder.logging.coach-silent-swallow` | 230 | 219 | **216** | −3 |
| `coder.refactor.complexity-nesting` | 162 | 162 | **152** | −10 |
| `coder.refactor.complexity-cyclomatic` | 139 | 139 | **136** | −3 |
| `coder.refactor.complexity-cognitive` | 120 | 117 | **109** | −8 |
| `coder.refactor.complexity-length` | 66 | 63 | 63 | 0 |
| **`coder.refactor.quality-file-length`** | 37 | 37 | **37** | **0** |

`enforce verdict (ratcheted): PASS — 0 rule(s) above baseline`.

Line cost, per file:

| file | before | after | Δ | cleared |
|------|-------:|------:|--:|--------:|
| `coach/validators/shared_fixtures.py` | 664 | 672 | +8 | 5 |
| `coach/commands/traceability.py` | 4273 | 4259 | **−14** | 2 |
| `validators/conventions/policy/archetype.py` | 358 | 365 | +7 | 1 |
| `enforce/conventions.py` | 493 | 494 | **+1** | 1 |
| `coach/commands/merge_cascade.py` | 479 | 484 | +5 | 1 |

Net **+7 lines across five files for ten violations**. `enforce/conventions.py` has the
tightest headroom in the repo — 7 lines under 500 — and was picked deliberately as the
worst case. It cost 1 line.

### Behaviour preservation

All ten functions were run in both trees against this repo's real `plan/` corpus
(41 wagons, 188 feature files, 472 WMBT files) and their outputs compared:

```
conventions._parse_pyproject_script_modules  YES    policy._scan_no_stale_suppressions  YES
merge_cascade.screen_merge_for_orphans       YES    shared_fixtures.feature_files       YES
shared_fixtures.train_files                  YES    shared_fixtures.trains_registry     YES
shared_fixtures.wagon_manifests              YES    shared_fixtures.wmbt_files          YES
traceability.from_wagon_dir                  YES    traceability.from_wagons_yaml       YES
```

Byte-identical, all ten, once absolute paths are normalised to the tree root.

---

## 2. 96 of the 162 nesting violations are not nesting

`calculate_nesting_depth` (`coder/validators/test_complexity.py:164`) is an indentation
counter, and its `else` branch scores *every* line at `indent // 4`:

```python
if stripped.endswith(':') and any(stripped.startswith(kw) for kw in [...]):
    max_depth = max(max_depth, current_depth + 1)
else:
    max_depth = max(max_depth, current_depth)   # <- any wrapped argument line
```

So a wrapped argument list is charged as nesting. Executed split of all 162 on deepest
*block-opening* line:

```
total nesting violations              : 162
  genuinely nested (block depth > 4)  : 66
  ONLY continuation-line indentation  : 96   <- guard clauses cannot fix these
```

Worked example — `planner/commands/plan_session_cli.py:112 build_parser`:

```
reported depth=10
deepest real block line -> '    def with_id(sp):'   (depth 2)
```

Driving the raw count down by re-wrapping these 96 would move the metric without
improving anything — the same gaming the issue already refuses for cyclomatic.

---

## 3. Every silent swallow is already annotated, and the ratchet ignores it

Executed over `src/atdd`:

```
raw (detector-shape) handlers         : 219
carrying an atdd:suppress pragma      : 219
NOT suppressed                        : 0
```

This is by design in the detector. From
`.atdd/workspaces/atdd.workspace.python-pytest/0.1.0/implementations/silent_swallow_detector/silent_swallow.py:30-34`:

> `_is_suppressed` (the inline `# atdd:suppress(...)` marker check) — the detector emits
> RAW violations INCLUDING handlers that carry a suppress marker … that is the consumer's
> suppress-and-clean disposition decision, never the detector's.

`atdd enforce --ratchet` never makes that decision. But
`coach/runtime/suppression_filter.py` and `atdd coach rules --stale` **do** honour the
marker. Two governance paths, the same 219 lines, opposite verdicts.

The deadlines inside those markers are clustered and ahead of us:

| `UNTIL=` | count |
|---|---:|
| `2026-12-06` | 108 |
| `2026-10-31` | 85 |
| `2026-11-16` | 11 |
| `2026-11-19` | 4 |
| (empty) | **5** |
| other | 6 |

`_scan_no_stale_suppressions` returns **0 findings** today — nothing is stale yet, so
nothing is driving them down. In seven weeks 85 come due at once.

---

## 4. The file-length trade barely exists

`scan_file_line_count` (`coder/validators/test_quality_metrics.py:255`) counts *files over
500*, not lines — its own docstring says "There is no hard limit — the ratchet baseline
prevents growth." So the count only moves when a file **crosses** 500, and a file already
over absorbs unlimited growth for free.

Of the files carrying genuine nesting debt: **16 are already over 500**, and of the 21
under, only one is within 21 lines of the threshold.

```
 493 lines  headroom=  7  enforce/conventions.py
 479 lines  headroom= 21  coach/commands/merge_cascade.py
 448 lines  headroom= 52  coach/plugins/diagnostics.py
 431 lines  headroom= 69  coach/commands/viz_app.py
 342 lines  headroom=158  coach/commands/issue_graph.py
 ...
```

#1929's `plan_session.py` at 503 was a crossing. Crossings are the exception, and they are
predictable in advance from this table.

---

## 5. A technique note

Guard clauses alone bottom out at depth 5 on the `for → for → try → with` shape, which is
common in this tree. Clearing it needs one helper extracted **in place** — same file, no
new module. In `shared_fixtures.py` that helper *shrank* the file by 3 lines, because it
de-duplicated three copies of the same try/except block.

Extraction-in-place is the technique. Extraction-to-module was not needed once.

---

## Reproduce

The patch is not committed here — the Lab section specifies a scratch branch with no PR.

```
git worktree add --detach <dir> origin/main
cd <dir> && git apply <patch>
atdd enforce --repo-root . --paths src/atdd --ratchet .atdd/enforce-ratchet.yaml
```
