# Validators

Validators map evidence to rule-bound reports. Every rule declares a canonical
rule ID and a disposition; a validator binds its rule ID at module import, so a
report always names the rule it violated.

## Dispositions

| Disposition | CI behavior |
|---|---|
| `strict` | any violation fails CI |
| `suppress-and-clean` | pre-existing sites may carry deadline suppressions; new violations fail |
| `advisory` | warnings only |
| `documentation-only` | encodes the operating protocol for discoverability; dispatched by the coach runtime, not by a pytest validator, so no validator pointer is required |

## Phase coverage

```bash
atdd validate              # all phases
atdd validate planner      # or tester / coder / coach
atdd validate package <path>
atdd validate --quick --coverage --verify-baseline
```

| Phase | Checks |
|---|---|
| planner | wagons, WMBTs, acceptance, train shape, URNs |
| tester | RED tests, naming, contracts, telemetry, SMOKE coverage |
| coder | architecture, boundaries, dead code, complexity, implementation evidence |
| coach | issues, registries, lifecycle, release gates, label compliance |

## Conventions registry

Conventions are YAML declaring rule IDs, severities, dispositions, and fix
hints. They live in two shapes:

- `src/atdd/<role>/conventions/<name>.convention.yaml` — grouped convention files
- `src/atdd/<role>/conventions/nodes/` — flat per-rule convention nodes

| Domain | Conventions |
|---|---|
| planner | wagon, acceptance, WMBT, feature, artifact, decomposition protocol |
| tester | red, filename, contract, artifact, smoke |
| coder | green, refactor, boundaries, backend, frontend, design |
| coach | issue, phase machine, orchestration, persona prompts, judge call-sites |

Inspect the merged registry with `atdd rules show <rule_id>`,
`atdd rules where <rule_id>`, `atdd rules grep <pattern>`, and
`atdd rules disposition`.
