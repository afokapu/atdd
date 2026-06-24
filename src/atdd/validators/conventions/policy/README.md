# `policy` family

Graph-question family **policy** — reusable template shapes that ask one
executable question each against the composed convention graph.

## `policy/forbidden_construct_absence`

- **Question:** Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?
- **Selector:** graph nodes/artifacts matched by a policy scope
- **Traversal:** scope -> scan nodes/fields/edges/artifacts -> forbidden matcher
- **Invariant:** forbidden match set is empty
- **Auto-capture:** usually explicit; a new node is included if it falls inside a policy scope
- **Failure evidence:** matched_construct, policy_id, location, reason, suggested_replacement
- **Non-membership:** a node is NOT in `policy/forbidden_construct_absence` when it does not match the selector above (its schema/metadata does not opt it into this question).

### Variants (real-graph execution, #1212)

The evaluator dispatches on `config['variant']` and scans a concrete slice of the
real composed graph. Each variant is legacy-parity-proven (the convention evaluator
AND the legacy validator both catch an injected fault — see each `test_*.py`).

| Variant | Scope | Legacy parity source |
|---|---|---|
| `smoke_synthetic_fixture_bypass` (planner) | SMOKE acceptance test files: no `FakeMultiplexer` / stub `cat\|sleep\|python` Popen / `_SYNTHETIC_AGENT` | `planner/validators/test_smoke_synthetic_fixture_bypass.py` |
| `no_stale_suppressions` (coach) | suppression markers under the repo: no `atdd:suppress(...) UNTIL=<date>` past its deadline | `coach/validators/test_no_stale_suppressions.py` |
| `freedom_layer_bash_scope` (coach, E032) | `session.convention.yaml::spawn_time.freedom_layer`: every `allowed_bash` tightly scoped `Bash(<cmd>:*)`, none forbidden | `coach/validators/test_e032_smoke_001_*.py` |
| `bypass_inventory` (coach, E026) | git-hook source files: no `ATDD_SKIP_*` bypass flag (baseline 0) | `coach/validators/test_e026_bypass_inventory_guard.py` |

CLAUDE.md-document checks (e022/r003) are excluded — they police the operator
document, not the convention graph, and are deferred to a separate issue.
