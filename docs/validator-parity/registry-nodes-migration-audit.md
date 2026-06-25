# #1225 Registry-reads-nodes/ migration — latent-bug audit & worklist

Audit of every item surfaced by making `bind_rule` + `build_registry` read `nodes/`
single-node convention files. Produced 2026-06-25 with the registry change + dedup
applied (uncommitted). **Refs #1207; blocks the broad #1207 decommission; does not close it.**

## Root cause
`_load_registry` (rule_binding.py) **skips any rule whose `severity` is not an `int`**.
Many `nodes/` files are **incomplete migrations** — missing the `metadata.severity` /
`metadata.disposition` / `implementation.ref` their monolith block carried. While the
monolith block exists the rule resolves from it; removing the block (dedup) drops the rule
from the registry → `bind_rule` callers fail at import, or reverse-coherence flags it.

## CLASS 1 — Incomplete `nodes/` files → BACKFILL metadata from the removed monolith block
| rule_id | problem | flagged by | fix |
|---|---|---|---|
| planner.issue-body.graph-context-required | missing severity(3)+disposition(suppress-and-clean)+validator | bind_rule import | sev=3, suppress-and-clean, impl.ref=`test_issue_body_has_graph_context::test_issue_body_has_graph_context` |
| planner.issue-body.dependency-entries-must-be-classified | missing severity(2)+disposition(advisory)+validator | bind_rule import | sev=2, advisory, impl.ref=`test_issue_deps_have_classification_tags::test_issue_deps_have_classification_tags` |
| planner.train.dispatch-map-is-registry | missing severity(3)+strict+validator | bind_rule import | sev=3, strict, impl.ref=`test_dispatch_registry::test_real_dispatch_entries_well_formed` |
| planner.train.dispatch-composite-key-exceptional | missing severity(3)+strict+validator | bind_rule import | sev=3, strict, same impl.ref as above |
| planner.train.family-matches-terminal-contract | missing severity(3)+strict+validator | bind_rule import | sev=3, strict, impl.ref=`test_train_family_matches_terminal_contract::test_real_trains_family_matches_terminal_contract` |
| planner.appendix.structure | missing severity(1)+disposition(documentation-only) | bind_rule skip | sev=1, documentation-only (no validator) |
| planner.steps.sequence | missing severity(2)+disposition(documentation-only) | bind_rule skip | sev=2, documentation-only |
| planner.relationship.no-orphan-nodes | missing validator (has sev+strict) | reverse-coherence | add impl.ref=`test_no_orphan_nodes::test_no_orphan_convention_nodes` |
| coach.source-layout.no-bare-version-detection | documentation-only BUT carries validator (contradiction) | reverse-coherence | set disposition to monolith's enforced value (verify HEAD; likely strict) OR drop impl.ref |
| coach.source-layout.no-toolkit-self-layout-assumption | documentation-only BUT carries validator | reverse-coherence | same as above |

Pre-existing incomplete (monolith severity already `None` → already unregistered; backfill for
completeness, not blocking): `planner.coverage.bidirectional-coverage-between-trains`,
`…between-wagons`, `planner.coverage.every-wmbt-must-be`.

## CLASS 2 — `nodes/`-only rule, no monolith block (pre-existing latent)
| rule_id | problem | fix |
|---|---|---|
| coach.lifecycle.phase-machine | strict, NO validator, NO bind_rule callsite anywhere (spec/structure rule) | set disposition `documentation-only`, OR author an enforcer + impl.ref |

## CLASS 3 — Structural dedup (part of the migration, not data bugs) — **52 monolith blocks**
- **42** canonical-duplicate blocks (rule_id in both monolith + `nodes/`) → handled by the
  shape-A dedup script (`scratchpad/dedup_remove_monolith_blocks.py`).
- **10** alias-collision blocks — **the dedup must be ALIAS-AWARE**: remove a monolith block
  whose canonical id is a `nodes/` rule's *alias* (renamed/consolidated rules where the monolith
  kept the old canonical id, now an alias on the renamed `nodes/` rule):
  `WF-001..WF-004` (issue.convention.yaml), 4× `coach.observer.*` (observer.convention.yaml),
  `coach.initializer.template-cli-drift` + `coach.workflow-template.command-must-parse`
  (rule-id.convention.yaml).

## Summary counts
- reverse-coherence violations: **4** (phase-machine, source-layout ×2, no-orphan-nodes)
- bind_rule-SKIP new breaks (monolith int severity, `nodes/` missing it): **7**
- pre-existing incomplete (mono severity already None): **3**
- structural removals: **42 canonical + 10 alias = 52** monolith blocks

## Other (non-rule) failures from the change
None independent. tester/coder dir "errors" (`test_contract_security`, `test_train_renders_content`,
`test_error_response_compliance`) are cascading collection aborts (collect cleanly in isolation);
they resolve once the 7 bind_rule-skip rules are backfilled. Forward-coherence passes.

## Recommended migration order
1. mapper (`single_node_rule_dict`) + wiring into `extract_rules` + `build_registry`
2. **alias-aware** dedup (52 blocks) — extend the dedup to also remove blocks whose id is a `nodes/` alias
3. backfill the 7 bind_rule-skip + 6 missing-validator `nodes/` files (Class 1)
4. reconcile source-layout ×2 + phase-machine dispositions (Class 1/2)
5. add the single-authoritative-representation guard (`test_no_duplicate_rule_representation`)
6. full-suite verify (coach + planner + tester + coder + conventions)
