# atdd.extension.train-interlocking-enforcement

Official ATDD **train-interlocking-enforcement extension**. It enforces, in a
consumer repo, that the train-interlocking route-control model is actually wired
into runtime and covered by tests.

> **Boundary in one line:** *Core owns the interlocking model + planner-time
> validation; this extension enforces its consumer-repo realization.* Core
> afokapu/atdd (#1246/#1248/#1249) owns the interlocking artifact schema,
> projections, and the Confirm gate; #1251 specifies the runtime call model. This
> extension owns the **consumer-side** checks: that an `InterlockingRunner` exists
> and is wired (Station Master → InterlockingRunner → TrainRunner), and that every
> admissible route has e2e coverage.

> **SCAFFOLD (afokapu/atdd-extensions#24).** This slice ships the **package +
> discovery substrate only** — manifest, convention home, relationships, scopes,
> gates, and two implementation manifests with `src/ tests/ fixtures/` skeletons.
> The convention node bodies and validator decision logic are authored by the
> sibling workers (#25/#26/#27). Every detector module is a
> `NotImplementedError` stub.

## Identity

```text
publisher : atdd
kind      : extension
name      : train-interlocking-enforcement
id        : atdd.extension.train-interlocking-enforcement
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

- **Conventions (home; authored by #25/#26/#27)** — `conventions/` is a
  placeholder this slice; see `conventions/README.md`.
- **Implementations (manifests + skeletons; logic by #25/#26)** —
  `implementations/interlocking-infrastructure` and `implementations/interlocking-coverage`,
  each a real discoverable unit (`atdd.implementation.yaml` + `src/ tests/
  fixtures/`) targeting `atdd.workspace.python-pytest`.
- **Scopes** — `scopes/interlocking-targets.scope.yaml`: consumer selectors for
  the interlocking route space, train YAML, runtime code, Station Master, and e2e
  tests.
- **Gates** — `gates/interlocking-infrastructure.gate.yaml` (CI/strict) and
  `gates/interlocking-coverage.gate.yaml` (CI/strict, downgradable to advisory).
- **Relationships** — `relationships.yaml` (extension-internal graph; empty in
  this scaffold, with a header pinning the edges #25/#26 must author).

## Coverage matrix (afokapu/atdd-extensions#24)

Each convention a build slice adds must be linked, machine-readably, to every
layer below. This scaffold provisions the home for each layer; the build slices
fill the convention + detector cells.

| Layer                       | Where it lives                                              | Status (scaffold) |
|-----------------------------|------------------------------------------------------------|-------------------|
| Convention node             | `conventions/<id>.convention.yaml`                         | home only (#25/#26) |
| → implementation ref        | impl `realizes_convention` + `relationships.yaml` edge     | impl manifests present |
| Implementation manifest     | `implementations/<name>/atdd.implementation.yaml`               | present |
| → workspace contract        | impl `targets_workspace` + `contract_version`              | present (python-pytest ^1.0.0 / 1.1.0) |
| Scope selector              | `scopes/interlocking-targets.scope.yaml`                   | present |
| Gate                        | `gates/<name>.gate.yaml`                                    | present |
| Tests / fixtures            | `implementations/<name>/{tests,fixtures/clean,fixtures/dirty}`  | skeleton (#25/#26) |
| Expected evidence keys      | impl `emits_rule_ids` + report channel                     | declared (rule ids) |
| Cross-repo core design ref  | this README + manifest header + node body (narrative §6.2) | present |

## Convention → validator → core-design map

| Convention id (planned)                    | Owner | Validator                              | Gate                                      | Realizes (core design, narrative) |
|--------------------------------------------|-------|----------------------------------------|-------------------------------------------|-----------------------------------|
| `coder.interlocking.runner-infrastructure` | #25   | `implementations/interlocking-infrastructure` | `gates/interlocking-infrastructure.gate.yaml` | afokapu/atdd#1251 |
| `tester.interlocking.route-coverage`       | #26   | `implementations/interlocking-coverage`       | `gates/interlocking-coverage.gate.yaml`       | afokapu/atdd#1248, #1249 |
| `coder.train.interlocking-bilateral-binding` | #27 | `implementations/interlocking-binding` | `gates/interlocking-binding.gate.yaml` | afokapu/atdd#1248 (entrypoint.exposed/actions — CONSUMED), #1251 (runtime + trace) |

## Cross-repo references

This extension enforces design owned by core `atdd`:

- afokapu/atdd#1246 — parent: train interlocking route-control model + terminology
- afokapu/atdd#1248 — planner artifact: interlocking YAML + deterministic projections (CLOSED)
- afokapu/atdd#1249 — planner validators + Confirm gate (CLOSED)
- afokapu/atdd#1251 — runtime: InterlockingRunner called by Station Master, delegates to TrainRunner
- afokapu/atdd-extensions#23 — extension enforcement parent

## Worker handoff contract

- **#25 (coder / infrastructure)** may add coder convention files + the
  `interlocking-infrastructure` detector logic + fixtures **only after** this
  package's path, implementation-manifest shape, scope, and gate (all present
  here) are agreed. The agreed contract: convention id
  `coder.interlocking.runner-infrastructure`, impl id
  `coder.interlocking.runner-infrastructure.impl`, entrypoint
  `src/interlocking_infrastructure.py`, report
  `tests/test_interlocking_infrastructure.py`.
- **#26 (tester / coverage)** may add tester convention files + the
  `interlocking-coverage` detector logic + fixtures **only after** the same
  shape is agreed. Agreed contract: convention id
  `tester.interlocking.route-coverage`, impl id
  `tester.interlocking.route-coverage.impl`, entrypoint
  `src/interlocking_coverage.py`, report `tests/test_interlocking_coverage.py`.
- **#27 (bilateral binding)** — LANDED. Convention id
  `coder.train.interlocking-bilateral-binding`, impl id
  `coder.train.interlocking-bilateral-binding.impl`, entrypoint
  `src/interlocking_binding.py`, report `tests/test_interlocking_binding.py`, gate
  `gates/interlocking-binding.gate.yaml`. One python-pytest detector emits the single
  rule_id over FIVE binding directions (declaration_to_runtime, runtime_to_declaration,
  station_to_declaration, declaration_to_station, trace_to_declaration) plus a
  parallel-reachability schema-drift guard. It CONSUMES core afokapu/atdd#1248's
  `entrypoint.exposed/actions` field for declaration_to_station reachability and defines
  no parallel reachability field. Fixtures under `fixtures/pass/` + `fixtures/fail/`.

When a build slice lands a real convention file it MUST also: add it to
`owns.conventions` in `atdd.extension.yaml`, add its node + edges to
`relationships.yaml`, and populate the validator's `fixtures/clean` +
`fixtures/dirty`.
