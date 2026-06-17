# Coach Design-Candidate Tracker

> **Issue #1122 (Slice 3 of #1113).** Tracker only — **no normative nodes authored.**
> Records coach concepts the aligned model wants but that have no stable legacy source
> yet, plus open schema/composition questions for later graph work.

## Design candidates (no source text yet → no node)

| candidate_id | source hint | future question |
|--------------|-------------|-----------------|
| `coach.execution.work-provenance` | `commit-trailers` (phase/wmbt/agent) | abstract provenance from git trailers once execution + git-worktree workspace contracts exist; bind git trailers as one realization. (Already referenced as a `design_candidates` entry in `atdd.extension.github`'s manifest — kept OUT of `depends_on.targets` until shipped.) |
| `coach.execution.command-policy-classifier` | `forbidden_commands` substrate | define the fail-open command-policy classifier as core enforcement substrate; platform patterns stay in extensions. |
| `coach.workspace.freedom-set-declared-as-data` | `session` freedom_layer (E031) | make "freedom set is data read by launch planes" a workspace-provider contract rule once that contract exists. |
| `coach.execution.*` (instance, workspace-binding, implementation-invocation, result-capture, resume) | aligned model §5 | needs the coach execution schema; author first real node when defined. |
| `coach.extension.*` (manifest, owned-artifacts, installation, graph-contribution, composition, uninstall-boundary) | aligned model §5 | backed by the #1097 author substrate, not coach legacy text; author when packages are built. |
| `coach.workspace.*` (provider-contract, contract-version, runtime-resolution, implementation-execution, conformance) | aligned model §5 | author when the workspace provider contract is formalized. |

## Open composition questions (for a later graph-composition issue)

1. **Extension relationship vocabulary.** `atdd.extension.github`'s `relationships.yaml`
   uses extension-local types (`depends_on`, `refines`, `part_of`, `enforces`,
   `complements`) under its own `graph_id`. Decide whether extension relationship types
   are a sanctioned **extension-local vocabulary** or must **normalize to the core
   relationship verb set** (the 10 Janet verbs) at composition time. *Not* a blocker for
   any shipped package — a composition-time decision.
2. **Core ↔ extension/workspace edges.** Currently forbidden in the core graph; package
   graphs stay separate. The composition design must define how a `core node →
   extension/workspace node` reference resolves (by id reference vs a real edge).
3. **`depends_on.targets` resolution.** Established by #1118/PR #3: only shipped core nodes
   go in `targets`; `design_candidates` are a separate block. A loader spec should make
   this a validated rule.

## Acceptance

- [ ] design candidates listed with source hints + future questions
- [ ] open composition questions recorded (incl. extension relationship vocabulary)
- [ ] **no normative nodes authored**
