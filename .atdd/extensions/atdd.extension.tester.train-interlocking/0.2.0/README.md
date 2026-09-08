# atdd.extension.tester.train-interlocking

Official ATDD **train-interlocking tester extension**. It enforces, in a consumer
repo, that the train-interlocking route-control model is actually covered by tests
that drive the production runners — the **test-surface** half of interlocking
enforcement.

> **Persona split (afokapu/atdd#1531).** This package is the tester-lane half of
> the former `atdd.extension.train-interlocking-enforcement`, which declared
> `role: coder` yet co-hosted these four `tester.interlocking.*` conventions. The
> four-segment grammar (afokapu/atdd#1343) makes persona explicit, so the mixed
> package was split: the source-surface conventions now live in the sibling
> **`atdd.extension.coder.train-interlocking`**. Every convention here is a
> `tester.interlocking.*` rule.

> **Boundary in one line:** *Core owns the interlocking model + planner-time
> validation; this extension enforces its consumer-repo test coverage.* This
> package owns the **consumer-side test checks**: that every admissible
> interlocking route has e2e coverage, that the coverage drives the real
> InterlockingRunner/TrainRunner (not a mock), that exposed Station Master actions
> have smoke coverage, and that traces bind back to their declared route.

## Identity

```text
publisher : atdd
kind      : extension
persona   : tester
name      : train-interlocking
id        : atdd.extension.tester.train-interlocking
manifest  : atdd.extension.yaml
targets   : atdd.workspace.python-pytest (contract ^1.0.0)
```

## Train-domain terminology (core afokapu/atdd#1246)

```text
Interlocking      = route / signal / variant selection (the guarded route space)
Train             = one runtime-executable linear path
TrainRunner       = linear train execution engine
InterlockingRunner= route-control layer; resolves one admissible train, delegates to TrainRunner
Station Master    = primary caller of InterlockingRunner
Cargo / Wagon     = payload transport / transformation inside the selected train
```

## What this package owns

- **Conventions (4)** — `tester.interlocking.route-coverage`,
  `tester.interlocking.production-runner-used`,
  `tester.interlocking.smoke-coverage-for-station-master`,
  `tester.interlocking.trace-binds-declared-route`.
- **Implementation** — `implementations/interlocking-coverage`: one python-pytest
  detector emitting all four rule_ids, targeting `atdd.workspace.python-pytest`.
- **Scopes** — `scopes/interlocking-targets.scope.yaml`: consumer selectors for
  the interlocking route space, train YAML, runtime code, Station Master, and e2e
  tests. (Shared verbatim with the coder sibling — both packages carry a copy.)
- **Gates** — `gates/interlocking-coverage.gate.yaml` (CI/strict).
- **Relationships** — `relationships.yaml` (extension-internal graph).

## Convention → validator → core-design map

| Convention id                                          | Validator                               | Gate                                    | Realizes (core design, narrative) |
|--------------------------------------------------------|-----------------------------------------|-----------------------------------------|-----------------------------------|
| `tester.interlocking.route-coverage`                   | `implementations/interlocking-coverage` | `gates/interlocking-coverage.gate.yaml` | afokapu/atdd#1248, #1249 |
| `tester.interlocking.production-runner-used`           | `implementations/interlocking-coverage` | `gates/interlocking-coverage.gate.yaml` | afokapu/atdd#1251 |
| `tester.interlocking.smoke-coverage-for-station-master`| `implementations/interlocking-coverage` | `gates/interlocking-coverage.gate.yaml` | afokapu/atdd#1248, #1251 |
| `tester.interlocking.trace-binds-declared-route`       | `implementations/interlocking-coverage` | `gates/interlocking-coverage.gate.yaml` | afokapu/atdd#1251 |

## Cross-persona relationship (narrative, boundary spec §6.2)

`tester.interlocking.trace-binds-declared-route` relates to the coder package's
`coder.train.interlocking-bilateral-binding` (its **trace_to_declaration**
direction). That node lives in a **separate extension**
(`atdd.extension.coder.train-interlocking`), and cross-extension graph edges are
forbidden (§6.2), so the relationship is recorded as prose:

> `trace-binds-declared-route` proves a trace test asserts every required binding
> field; bilateral-binding's trace_to_declaration direction additionally proves
> the asserted `interlocking_id`/`route_id` VALUES resolve back to a declared
> route. Co-equal facets of trace↔declaration integrity, now enforced from two
> persona lanes.

## Cross-repo references

This extension enforces design owned by core `atdd`:

- afokapu/atdd#1246 — parent: train interlocking route-control model + terminology
- afokapu/atdd#1248 — planner artifact: interlocking YAML + deterministic projections (CLOSED)
- afokapu/atdd#1251 — runtime: InterlockingRunner called by Station Master, delegates to TrainRunner
- afokapu/atdd#1531 — the persona split that produced this package
- afokapu/atdd-extensions#23 — extension enforcement parent
