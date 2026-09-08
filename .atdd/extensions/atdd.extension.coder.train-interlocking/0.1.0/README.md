# atdd.extension.coder.train-interlocking

Official ATDD **train-interlocking coder extension**. It enforces, in a consumer
repo, that the train-interlocking route-control model is actually wired into
runtime — the **source-surface** half of interlocking enforcement.

> **Persona split (afokapu/atdd#1531).** This package is the coder-lane half of
> the former `atdd.extension.train-interlocking-enforcement`, which declared
> `role: coder` yet co-hosted four `tester.interlocking.*` conventions. The
> four-segment grammar (afokapu/atdd#1343) makes persona explicit, so the mixed
> package was split: the test-surface conventions now live in the sibling
> **`atdd.extension.tester.train-interlocking`**. Every convention here is a
> `coder.train.*` rule.

> **Boundary in one line:** *Core owns the interlocking model + planner-time
> validation; this extension enforces its consumer-repo realization.* Core
> afokapu/atdd (#1246/#1248/#1249) owns the interlocking artifact schema,
> projections, and the Confirm gate; #1251 specifies the runtime call model. This
> extension owns the **consumer-side source checks**: that an `InterlockingRunner`
> exists and is wired (Station Master → InterlockingRunner → TrainRunner), and the
> systemic bilateral-binding closure.

## Identity

```text
publisher : atdd
kind      : extension
persona   : coder
name      : train-interlocking
id        : atdd.extension.coder.train-interlocking
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

- **Conventions (11)** — five granular runtime-infrastructure rules
  (`coder.train.interlocking-{runner-exists,resolution-model-exists,…}`), the
  systemic `coder.train.interlocking-bilateral-binding`, and five
  `coder.train.*.definition` runtime-machinery anchors (kind: family, advisory).
- **Implementations** — `implementations/interlocking-infrastructure` (the five
  granular rules) and `implementations/interlocking-binding` (bilateral binding),
  each targeting `atdd.workspace.python-pytest`.
- **Scopes** — `scopes/interlocking-targets.scope.yaml`: consumer selectors for
  the interlocking route space, train YAML, runtime code, Station Master, and e2e
  tests. (Shared verbatim with the tester sibling — both packages carry a copy.)
- **Gates** — `gates/interlocking-infrastructure.gate.yaml` and
  `gates/interlocking-binding.gate.yaml` (both CI/strict).
- **Relationships** — `relationships.yaml` (extension-internal graph).

## Convention → validator → core-design map

| Convention id                                | Validator                                     | Gate                                          | Realizes (core design, narrative) |
|----------------------------------------------|-----------------------------------------------|-----------------------------------------------|-----------------------------------|
| `coder.train.interlocking-runner-exists` (+ 4 siblings) | `implementations/interlocking-infrastructure` | `gates/interlocking-infrastructure.gate.yaml` | afokapu/atdd#1251 |
| `coder.train.interlocking-bilateral-binding` | `implementations/interlocking-binding`        | `gates/interlocking-binding.gate.yaml`        | afokapu/atdd#1248 (entrypoint.exposed/actions), #1251 (runtime + trace) |

## Cross-persona relationship (narrative, boundary spec §6.2)

Before the split, `coder.train.interlocking-bilateral-binding` carried a
`relates-to` **graph edge** to `tester.interlocking.trace-binds-declared-route`.
That node now lives in a **separate extension**
(`atdd.extension.tester.train-interlocking`), and cross-extension graph edges are
forbidden (§6.2), so the relationship is recorded here as prose:

> bilateral-binding's **trace_to_declaration** direction proves the asserted
> `interlocking_id`/`route_id` VALUES resolve back to a declared route in the
> YAML; the tester package's `trace-binds-declared-route` proves a trace test
> asserts every required field. Co-equal facets of trace↔declaration integrity,
> now enforced from two persona lanes.

## Cross-repo references

This extension enforces design owned by core `atdd`:

- afokapu/atdd#1246 — parent: train interlocking route-control model + terminology
- afokapu/atdd#1248 — planner artifact: interlocking YAML + deterministic projections (CLOSED)
- afokapu/atdd#1249 — planner validators + Confirm gate (CLOSED)
- afokapu/atdd#1251 — runtime: InterlockingRunner called by Station Master, delegates to TrainRunner
- afokapu/atdd#1531 — the persona split that produced this package
- afokapu/atdd-extensions#23 — extension enforcement parent
