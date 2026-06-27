# Phase A review — coder dead-code + duplication (core-agnostic atomization)

Cluster: `coder` role; two lone core-agnostic rules atomized to
`src/atdd/coder/conventions/nodes/`. PARTIAL de-monolith — every other rule in
each source monolith left intact.

| rule_id | new node | source monolith | EXT rules left intact |
|---|---|---|---|
| `coder.dead-code.reachability` | `nodes/coder.dead-code.reachability.convention.yaml` | `dead-code.convention.yaml` | `coder.dead-code.reachability-typescript` |
| `coder.duplication.no-structurally-identical-code` | `nodes/coder.duplication.no-structurally-identical-code.convention.yaml` | `duplication.convention.yaml` | `coder.duplication.no-structurally-identical-typescript`, `coder.duplication.no-intra-layer-code-python`, `coder.duplication.no-intra-layer-code-typescript` |

## Pass 1 — extraction fidelity (high_fidelity)
- Statements copied verbatim from the legacy `description:` of each rule.
- `coder.dead-code.reachability`: disposition `strict`, severity `2`, alias
  `DEAD-CODE-REACHABILITY-001`, `introduced_in: 1.67.0`, validator
  `test_dead_code_python::test_no_unreachable_python_files` — all preserved from
  the legacy top-level `rules:` entry.
- `coder.duplication.no-structurally-identical-code`: disposition
  `documentation-only`, alias `SPEC-CODER-DUP-0001` preserved. Legacy
  `severity: warning` (non-enum string) mapped to integer `2` per the
  convention-node schema (`metadata.severity` is `integer 1..4`). Per the
  reverse-coherence contract, documentation-only rules MUST NOT carry a
  `validator:` field → the node intentionally omits `implementation`.
- Each node carries `source:` (legacy_path / legacy_section / legacy_rule_id /
  extraction_mode: high_fidelity) and a defining `term`.

## Pass 2 — partial de-monolith integrity
- `dead-code.convention.yaml`: only the `coder.dead-code.reachability` list entry
  removed from the top-level `rules:` block; replaced with a pointer comment.
  `reachability-typescript` (TS EXT) untouched. All non-`rules` sections
  (graph_roots, exclusions, examples, enforcement, …) untouched.
- `duplication.convention.yaml`: the `duplication.rules.intra_layer_duplication`
  block doubles as the **operational config** read directly by
  `test_duplication_detector` (`min_fragment_statements`, `scan_dirs`, `layers`,
  `exclusions`, …). Only the *rule-identity* keys (`id`, `aliases`,
  `disposition`, `description`, `severity`) were lifted to the node; the
  operational config is retained in place with a pointer comment. The block key
  `intra_layer_duplication` (non-namespaced, no `id`) is now Shape-C → skipped by
  the registry walker, so no duplicate registration. The `intra_layer_duplication_typescript`
  block and the top-level `rules:` entries are untouched.

## Pass 3 — graph wiring + registry/tests
- `relationships.yaml`: one `runs_alongside` edge
  (`coder.dead-code.reachability` → `coder.duplication.no-structurally-identical-code`),
  making both lone nodes relationship endpoints (peer coder GREEN-phase
  static-analysis quality gates). No orphans introduced. No mirror of an
  existing node, so no `refines` edge required.
- Registry (`build_registry`): both ids now resolve from their `nodes/` file
  (authoritative per #1225); EXT siblings still resolve from their monoliths; no
  duplicate representations.
- Verification suite (no_orphan_nodes, sentinels, rule_validator_binding,
  no_duplicate_rule_representation, all coder validators):
  **197 passed, 112 skipped, 0 failed**. No monolith-reading test needed
  patching — `test_duplication_detector` still finds its config block, and
  binding/no-duplicate guards pass against the nodes/ representation.
