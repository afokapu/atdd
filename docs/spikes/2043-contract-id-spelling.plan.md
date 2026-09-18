# Fix plan — contract `$id` spelling

**Diagnosis (corrected).** The reported mechanism is real: a contract authored by
`create_contract` is keyed `contract:contract:<identity>` in the traceability
graph and no wagon can name it. The reported *attribution* is inverted. The graph
reader implements the repo's written convention correctly; the writer violates it;
and the shipped gate for that convention cannot detect the violation.

Four defects, one chain — each with its own owner and its own guard.

---

## D1a — the gate cannot express the rule it documents  *(fixed)*

`src/atdd/tester/validators/test_contract_schema_compliance.py`
(`test_contract_id_format_follows_convention`, SPEC-PLATFORM-CONTRACTS-0011) lists
`✗ "$id": "contract:match:result"` in its own docstring, then matches it with
`^[a-z][a-z0-9\-]+(:[a-z][a-z0-9\-]+)+(\.[a-z][a-z0-9\-]+)*$`. Measured: it scans
the file, reads the prefixed `$id`, and passes.

**Change:** `CONTRACT_ID_PATTERN` now excludes a leading `contract:` *and* a
leading `urn:` — both spellings `planner.artifact-naming.schema-identifier`
forbids by name ("the clean artifact name ... with NO `urn:contract:` prefix").
**Guard:** three detection proofs, deliberately **not** `platform`-marked so they
run wherever the module does. Fault-injected: restoring the old pattern turns
both rejection proofs red and leaves the acceptance proof green.
**Measured before implementing:** red on `contract:match:result`, 0/21
regressions across this repo's committed contracts.

## D1b — even fixed, that gate never runs where violations happen

`test_contract_id_format_follows_convention` is `@pytest.mark.platform`, and
`test_runner.py:283-285` sets `consumer_mode = not is_atdd_source_repo()`, which
appends `-m 'not platform'`. Measured against the lab world:

```
is_atdd_source_repo: False  =>  consumer_mode: True  =>  adds: not platform
pytest …test_contract_schema_compliance.py -m "not platform"
  no tests collected (9 deselected)
```

So the `$id` rule has **zero enforcement in exactly the repos that can violate
it**. The validator reads consumer artifacts — `CONTRACTS_DIR = REPO_ROOT /
"contracts"`, under a comment that literally says "Consumer repo artifacts" —
while carrying a marker that confines it to the toolkit. D1a makes the toolkit's
own gate honest; it does not protect a consumer repo, and would not have caught
the reported defect.

**This is a disposition decision, not a patch.** Dropping the `platform` marker
would start the scan in every consumer repo and go red on whatever `$id` debt is
already there — which is the point, but it is a ratchet someone owns. The repo
has the machinery for this (advisory → strict); choosing the entry disposition is
the decision. Deliberately not taken here.

**Why D1 came first:** every other fix is unenforceable while the gate is blind —
and D1b says it is still blind for consumers even now.

## D2 — `create_contract` writes the forbidden spelling

`src/atdd/planner/commands/author.py:1097` — `"$id": f"contract:{identity}"`.
Two lines later the same function writes the registry `identity` bare
(`:1055-1059`), so the writer contradicts itself as well as the convention.

**Change:** `"$id": identity`.
**Blast radius:** none in this repo — no committed contract was authored by this
writer; all 21 predate it and are already bare.

## D3 — a GREEN acceptance pins the violation

`src/atdd/planner/commands/tests/test_e008_unit_001_derives_path_id_and_registers.py:38`
asserts `doc["$id"] == "contract:commons:compliance:probe"`, while `:54` asserts
`"contract:" not in entry["identity"]`. One test pins both spellings of one
identity and pins the forbidden one onto the artifact.

**This is a plan-artifact change, not a coder patch.** The acceptance is the
requirement; correcting it needs a planner decision, exactly as
`phase_machine.convention.yaml` says ("the decomposition is the one artifact no
downstream gate can re-derive"). Route it through the planner for
`wmbt:author-plan-substrate:E008`, with this spike as the evidence.

## D4 — `ContractResolver.resolve` strips every occurrence, not the prefix

`src/atdd/coach/utils/graph/resolver.py:756` — `urn.replace("contract:", "")`.
Independent of D1–D3, and doubly harmful: it is what degrades D2's symptom from a
hard error to a soft warning (the doubled URN accidentally resolves via the
path-based fallback), and it breaks any identity whose own theme is `contract`.

**Change:** strip the leading prefix once. Two sites in this repo already use the
correct idiom — `contract_resolution.py:38-40` and
`test_contract_registry_coherence.py:109`; this one is the outlier, so the change
is *adopting* an established idiom, not inventing one.

**Correction to an earlier draft:** this bug is *not* what makes D2 present as a
warning rather than an error. Measured: world1 under strip-once still warns,
because the doubled URN resolves either way — by exact `$id` match instead of the
path fallback. D4 stands on its own (it breaks `contract`-themed identities
outright), not on that claim.

**Reviewed and narrowed.** One reviewer argued the fix here is not strip-once but
*normalize both sides of the comparison*, as `contract_resolution.py:106,111`
does — because under a prefixed `$id` the exact-match strategies can never fire
and resolution silently degrades to path-derivation. Demonstrated on a contract
sitting off its convention path. Measured, that is true **of the prefixed-`$id`
world only**: with D2 applied, the same off-convention world is clean with *no*
resolver change at all, because strategy 1 matches the `$id` exactly regardless of
path. So normalize-both-sides is a **transition-window** measure — worth shipping
alongside D4 for as long as consumer repos still hold prefixed `$id`s on disk, and
removable afterwards. It is not the permanent fix, and the argument for it is an
argument against the end-state this plan already rejects.
**Blast radius:** measured — output byte-identical to baseline on this repo's 21
contracts (same nodes, same 19 edges, same 2 pre-existing warnings by name).

## D5 — reserve the family namespace  *(new; makes the mapping total)*

The spike's worlds 2 and 3 name a consumer theme `contract`. Nothing forbids it
today (`theme_map.py` has no reserved names; `_CONTRACT_IDENTITY_RE`,
`author.py:942`, accepts any kebab first segment), and while it is legal the map
`$id → URN` is **provably** ambiguous: a bare three-segment `contract:match:result`
is indistinguishable from a prefixed `match:result`. That ambiguity is what
falsified every reader-side candidate.

Measured, this is not hypothetical and not only a reader's problem: with a theme
named `contract`, `create_contract` **accepts** identity `contract:match:result`
and writes `$id: contract:contract:match:result` with registry identity
`contract:match:result` — the doubled spelling straight from the writer, and a
registry identity that is not bare, which `planner.contract.registry-coherence`
then double-strips.

**Change:** reject `contract` as a theme name at `validate_contract`
(`author.py:942-944`) and state the reservation in
`planner.artifact-naming.theme-taxonomy`. With D2 + D5, `contract:` + `$id` is
total and unambiguous, and no reader ever has to guess.

## D6 — two active convention nodes contradict each other

`planner.artifact-naming.schema-identifier` (rule, active) and
`planner.artifact-naming.urn-structure` (rule, active) say `$id` is bare and the
URN prefixes it. `planner.artifact-naming.validation-rules` (constraint, active)
says "`$id` is `urn:contract:{artifact_name}`" — a third spelling used by no
artifact and no code. All three were extracted high-fidelity from the same legacy
file (`legacy_sha: eca68a67c92694c9`), so the extraction faithfully preserved a
contradiction the legacy document already carried.

**Change:** reconcile `validation-rules:18` with `schema-identifier`. Until that
lands, any fix here is arguing with one of the repo's own active constraints.
**Guard worth considering:** nothing currently detects two active convention nodes
prescribing different forms of the same field — that absence is why this survived
since 2026-06-16.

---

## What must NOT change

The six `f"contract:{...}"` read sites (`resolver.py:848`,
`graph_builder.py:910`, `registry.py:983`, `consumers.py:258`,
`test_telemetry_structure.py:95`, `test_contract_schema_compliance.py:212`) are
the convention's `urn_reference = contract:{artifact_name}` rule implemented
correctly. Patching them — the fix the report asked for — would have to be done
six times, each one moving further from the repo's own written rule, and
measurement 4 shows every such patch breaks legal input somewhere.

`graph_builder.py:1544` prefixes a `urn:jel:*` id deliberately. Leave it.

One caveat carried from review: the produce-side `urn:` override
(`graph_builder.py:977-980`) passes any `contract:*` value straight through
un-normalized. It is not part of this defect, but it means "the readers are
correct" is a statement about the six `$id` sites, not about every path into a
contract URN.

## Fallback if consumer repos cannot be migrated on a schedule

One reviewer proposed keying the node from the registry's bare `identity`, matched
by resolved path, rather than from `$id` at all — `contracts/_contracts.yaml` is
bare by construction (`author.py:1057`, guarded at E008-UNIT-001:54), so it is the
one non-heuristic disambiguator on disk. Measured clean on every world.

This plan does not adopt it, because it makes every contract resolution depend on
a registry read in order to work around artifacts that a one-time migration
removes. But it is the right answer if the migration below cannot be scheduled —
it is correct under either spelling, permanently, because it never asks whether
`$id` "is a URN".

## Consumer-repo migration

Contracts already authored by `create_contract` carry the forbidden `$id` on
disk. `$id` alone cannot be repaired by inspection (D5's ambiguity), so migrate
from the authoritative pair the registry already stores: for each
`contracts/_contracts.yaml` entry, rewrite the schema at `entry.path` to
`$id: entry.identity`. The registry identity is bare by construction and asserted
so (`author.py:1046-1050`, E008-UNIT-001:54), which makes it the one unambiguous
source. Anything not in the registry is reported, not guessed.

## Sequencing

**Landed:** D4, then D1a. Both are unambiguously bug fixes rather than convention
choices, both measured, both with fault-injected guards.

**Remaining:** D6 next if it is cheap (a docs reconciliation, and every other fix
cites the rule it settles) → D1b's disposition decision → (D2 + D5) → D3 as the
planner decision that unblocks D2's acceptance → consumer migration.

D4 can land independently and immediately: self-contained, measured zero blast
radius, and correct under either end-state — both reviewers said ship it on its
own regardless of how the rest sequences.

Explicitly **not** staged: no interim reader heuristic. The first version of this
plan shipped one (use `$id` as-is when it parses as a URN) and both reviewers
falsified it with the same counterexample — it converts an input that the D4 fix
alone scores clean into an error plus a split node.

## What the reviewers changed, for the record

Adopted: the end-state (all three), the written-rule finding that inverted the
diagnosis (codex, zcode), the third contradicting convention → D6 (zcode), the
writer-side seam → D5's measurement (zcode), world3 which falsified the first
proposal (codex, claude), the transition-window narrowing of D4 (claude), and two
defects in the spike's own harness (all three).

Conceded and corrected: "no rule says which wins" was false; "the replace-all bug
is what makes it a warning" was false; "c4+r is the only clean combination" was
false (`c3+r` is clean on worlds 1 and 2 — never run); and the blast-radius result
is **vacuous for c4**, since all 21 committed `$id`s are bare, so c4's branch never
fires. It measured inertness, not safety.

## Provenance

Every claim above is either derived with a `file:line` citation or measured in
`docs/spikes/<issue>-contract-id-spelling.md`. The one thing that is neither —
whether a consumer repo has in fact authored contracts with the prefixed `$id` —
is a question for the reporting repo, not this one.
