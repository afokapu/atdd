# conventions/ — train interlocking enforcement

**Placeholder (afokapu/atdd-extensions#24 scaffold).** No convention node bodies
are authored in this slice. This directory is the home for the convention nodes
the build slices add:

| Convention id                              | Owner | Realized by                          | Realizes (core design)        |
|--------------------------------------------|-------|--------------------------------------|-------------------------------|
| `coder.interlocking.runner-infrastructure` (5 granular `coder.train.interlocking-*`) | #25 | `implementations/interlocking-infrastructure` | afokapu/atdd#1251 |
| `tester.interlocking.route-coverage` (+3 sibling tester rules) | #26 | `implementations/interlocking-coverage` | afokapu/atdd#1248, #1249 |
| `coder.train.interlocking-bilateral-binding` | #27 | `implementations/interlocking-binding` | afokapu/atdd#1248 (entrypoint.exposed/actions — CONSUMED), #1251 (runtime + trace) |

Each convention node added here MUST follow the convention-node schema (see the
existing `official/atdd.extension.{coder,tester,github}/conventions/*.convention.yaml`
for the shape) and be wired through the full coverage matrix before merge:

```text
convention -> implementation        (impl manifest realizes_convention + relationships.yaml edge)
implementation -> workspace contract (impl manifest targets_workspace + contract_version)
convention -> scope                  (scopes/interlocking-targets.scope.yaml selector)
convention -> gate                   (gates/<name>.gate.yaml)
convention -> tests/fixtures         (the validator's tests/ + fixtures/clean|dirty)
convention -> core design reference  (NARRATIVE: node body + manifest, per boundary spec §6.2)
```

When the first real convention file lands here, add it to `owns.conventions` in
`../atdd.extension.yaml` and add its node + edges to `../relationships.yaml`.
