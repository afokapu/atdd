# Spike — `create_contract` writes a `$id` the written convention forbids, and the gate that forbids it is blind

> **Provenance:** REPORTED (an agent in a consumer repo), therefore spiked.
> **Question:** Is every contract authored by `create_contract` structurally
> untraceable — and if so, is the graph reader wrong, as reported?
> **Shapes:** Lab (three disposable worlds, real code paths) + Blast radius
> (candidate readers scored against this repo's own 21 contracts).
> **Frozen sha:** `36ce055ae5056d7a0f7d012c1e4aaa5df628ce51`
> **Answer:** the defect is real; the reported diagnosis is inverted. The reader is
> right, the writer is wrong, and a shipped validator that claims to catch this
> cannot.

## The claim under test

> The graph builder prepends the `contract:` family prefix to an `$id` that
> already carries it, so `_has_producer` looks for an edge to a URN no producer
> can ever name. Every contract authored by `create_contract` is structurally
> untraceable, whatever the wagons declare.

Mechanism: confirmed. Attribution: wrong. Fixing what the report blames makes
things worse — measurement 4 below.

## Measurement 1 — the symptom is real, and worse than reported

world1: a throwaway repo, contract authored by the **real** `create_contract`,
wagon manifest in the shape this repo's own manifests use
(`plan/bind_extension_conventions/_bind_extension_conventions.yaml:24`). Real
`GraphBuilder.build()`, real `EdgeValidator.validate_contracts()`.

```
schema $id                  : 'contract:match:result'
registry identity           : 'match:result'
manifest produce[].contract : 'contract:match:result'
graph contract NODES        : ['contract:contract:match:result', 'contract:match:result']
graph produces EDGES        : [('wagon:score-match', 'contract:match:result')]
validate_contracts issues   : 1
  - [warning] contract:contract:match:result :: Contract has no producing wagon
```

One contract, **two nodes** — a file-backed node nobody produces, and a
producer-backed node with no file. The chain is not broken, it is forked, and
each half looks individually plausible. The report saw only the warning.

## Measurement 2 — there IS a written rule, and the writer violates it

The premise that no rule says which spelling wins is **false**. Three active
convention nodes speak to it, all extracted high-fidelity from the same legacy
source (`legacy_sha: eca68a67c92694c9`) — and they do not agree with each other:

| node | kind | says |
|---|---|---|
| `planner.artifact-naming.schema-identifier` | rule, active | `$id` is the clean name, **NO** `urn:contract:` prefix |
| `planner.artifact-naming.urn-structure` | rule, active | URN = `contract:{artifact_name}`, e.g. `commons:identifiers.uuid → contract:commons:identifiers.uuid` |
| `planner.artifact-naming.validation-rules` | constraint, active | "`$id` is `urn:contract:{artifact_name}`" — **a third spelling** |

Two of the three agree: `$id` bare, URN = prefix + `$id`. The third prescribes a
form matching neither the 21 committed artifacts nor the writer. Note that
`schema-identifier`'s statement forbids the exact phrase `validation-rules`
prescribes, so `schema-identifier` reads as the correction of `validation-rules`
— and the extraction faithfully preserved both sides of a contradiction the
legacy document already carried.

The majority, and the operative rule, say `$id` is bare:

`src/atdd/planner/conventions/nodes/planner.artifact-naming.schema-identifier.convention.yaml`
(`status: active`):

> A contract's `$id` is the clean artifact name `{theme}:{resource}[.{category}]`
> with **NO** `'urn:contract:'` prefix … `urn_reference` (in wagon produce/consume)
> = `contract:{artifact_name}`.

`src/atdd/tester/validators/test_contract_schema_compliance.py:365-386`
(SPEC-PLATFORM-CONTRACTS-0011) lists the failing case **verbatim**:

> `✗ "$id": "contract:match:result"  (wrong - has "contract:" prefix)`

And all 21 contracts committed in this repo carry a bare `$id`. The convention,
the platform spec, and the entire existing corpus agree. `create_contract`
(`author.py:1097`, `"$id": f"contract:{identity}"`) is the only dissenter — and
it dissents from itself, writing the registry `identity` **bare** two lines later
(`author.py:1055-1059`).

That contradiction is frozen into a **GREEN acceptance**:
`test_e008_unit_001_derives_path_id_and_registers.py:38` asserts
`doc["$id"] == "contract:commons:compliance:probe"`, and line 54 asserts
`"contract:" not in entry["identity"]`. One test pins both spellings of the same
identity, and pins the forbidden one onto the artifact.

This is the README's own canonical failure, recurring: *an untested premise,
once written into a plan artifact, stops being a guess and becomes the
requirement.*

## Measurement 3 — the gate that should have caught this is blind

SPEC-PLATFORM-CONTRACTS-0011 documents the rule. Run it against world1:

```
$ ATDD_REPO_ROOT=<world1> pytest …::test_contract_id_format_follows_convention
1 passed    rc=0
```

It passed. Not skipped — it resolved the lab root, found the file, read the
prefixed `$id`, and passed anyway:

```
scanned root : <world1>
scanned files: ['<world1>/contracts/match/result.schema.json']
  $id='contract:match:result' matches_documented_pattern=True
```

Its regex is `^[a-z][a-z0-9\-]+(:[a-z][a-z0-9\-]+)+(\.[a-z][a-z0-9\-]+)*$`, which
happily matches `contract:match:result` — `contract` simply satisfies the first
segment. The docstring names that exact string as `✗ wrong`; the implementation
accepts it. **The gate cannot express the rule it documents.**

This closes the causal chain: the rule existed, the gate could not enforce it,
so the violating writer shipped, and its acceptance made the violation
requirement.

## Measurement 4 — no reader-side fix is correct

Candidates, installed by monkeypatching the **real** reader methods so each is
measured in situ:

- **c1** blind strip — `"contract:" + $id.removeprefix("contract:")`
- **c3** path-derived — identity from the file's location under `contracts/`
- **c4** `$id`-is-the-URN — use `$id` as-is when it parses as a valid contract URN
- **r** strip-once — `urn.replace("contract:", "")` → strip the *leading* prefix only
  (`resolver.py:756`)

Worlds: **world1** as above. **world2** / **world3** are consumer repos whose
theme map names a theme `contract` — legal under `theme_map.py:82` and
`planner.artifact-naming.theme-taxonomy` — with correct, convention-obeying bare
`$id`s of two and three segments. world3 is the case that matters: a bare
three-segment identity is *itself* a syntactically valid contract URN, so no
amount of string inspection can tell it from a prefixed one.

| world | none | c1 | c3 | c4 | **r** | c4+r |
|---|---|---|---|---|---|---|
| world1 (violating `$id`) | 1 warn + split | 0 | 0 | 0 | 1 warn + split | 0 |
| world2 (bare, 2-seg, theme `contract`) | 1 error | 1 error + split | 1 error | 1 error | **0** | 0 |
| world3 (bare, 3-seg, theme `contract`) | 1 error | 1 error + split | 1 error | 1 error | **0** | 1 error + split |

Readings:

1. **Every reader-side normalization fails somewhere.** c1 mangles a legal
   identity into `contract:result`, which fails the contract grammar outright.
   c4 — the one that looked safest, and the one this spike originally proposed —
   splits the graph in world3 and returns an **error**, which is worse than the
   warning it set out to fix. c3 mis-keys any contract not at its convention
   path, which `contract_resolution.py:101-115` deliberately supports.
2. **`r` alone is clean on every world whose artifacts obey the convention.**
   It "fails" world1 only because world1's artifact is itself illegal.
3. So the readers need **exactly one** change — the strip-once bug — and the
   `$id` spelling must be fixed where it is written, not where it is read.

*(world3 was constructed by an adversarial reviewer to falsify this spike's first
conclusion, and did. It is reproduced here independently.)*

## Measurement 5 — the "prefix the `$id`" idiom is correct, six times over

`grep -rn 'f"contract:{' --include="*.py" src/` finds six sites that build a
contract URN by prefixing a `$id`. Measured against world1, all six produce
`contract:contract:match:result`:

| site | |
|---|---|
| `coach/utils/graph/resolver.py:848` | measured |
| `coach/utils/graph/graph_builder.py:910` | measured |
| `coach/commands/registry.py:983` | measured |
| `coach/commands/consumers.py:258` | measured |
| `tester/validators/test_telemetry_structure.py:95` | measured |
| `tester/validators/test_contract_schema_compliance.py:212` | same construction, not separately exercised |

The first instinct is to call this six copies of one bug. Measurement 2 says the
opposite: **all six are correct**, they are the convention's own
`urn_reference = contract:{artifact_name}` rule implemented faithfully, and they
agree with 21 of 21 committed artifacts. Had the fix gone where the report
pointed, it would have had to be applied six times, each one moving the codebase
further from its own written rule.

`graph_builder.py:1544` also prefixes but only ever sees a `urn:jel:*` `$id`
(`_jel_contract_node` returns `None` otherwise). It is deliberately marking a
non-ATDD id and must **not** change.

## Measurement 6 — blast radius of `r`

`r` applied to this repo's real data: output **byte-identical** to baseline —
same 21 nodes, same 19 produces edges, the same 2 pre-existing warnings **by
name** (`commons:documentation-verdict`, `frontend:train:render-metadata`).
Zero regressions. (Diffed by name, not by count.)

## Measurement 7 — the proposed gate fix, fault-injected

The fix for the blind gate is a negative lookahead on the family name:
`^(?!contract:)[a-z][a-z0-9\-]+(:[a-z][a-z0-9\-]+)+(\.[a-z][a-z0-9\-]+)*$`.
Scored against both corpora before writing any code:

```
world1 (create_contract-authored)
  '$id=contract:match:result'   current=True   proposed=False      <- goes red
this repo's committed contracts
  scanned=21  rejected_by_current=0  rejected_by_proposed=0        <- stays green
```

The guard has been seen red against the exact defect and green against the whole
real corpus. Note it also rejects a legal `contract`-themed identity — which is
not a side effect but the same decision as the namespace reservation below,
written once.


## Measurement 8 — the writer doubles the prefix on its own, with no reader involved

The ambiguity is not only a reader's problem. `validate_contract`'s identity regex
(`author.py:942-944`) does not forbid a leading `contract` segment, and the theme
check passes for any configured theme. So in a consumer repo whose theme map names
a theme `contract`, the writer accepts and emits:

```
create_contract({"identity": "contract:match:result", ...})   # accepted, no exception
file written      : contracts/contract/match/result.schema.json
$id               : 'contract:contract:match:result'
registry identity : 'contract:match:result'
registry theme    : 'contract'
```

The doubled spelling comes straight out of `create_contract`. No graph, no
resolver, no reader. And the registry `identity` here still carries a leading
`contract:`, so the "identity is bare" shape that `author.py:1047-1051` documents
and that `planner.contract.registry-coherence` relies on ("the `contract:` prefix
is stripped before lookup") is true only by convention, never by enforcement —
in this repo it double-strips.

This is the measurement that makes the namespace reservation a fix rather than a
tidy-up: while a theme may be called `contract`, `$id → URN` is not a function,
and no amount of care at either end can make it one.

*(Seam identified by an adversarial reviewer; reproduced independently here.)*


## Measurement 9 — the adversarial round, and what it changed

Three models reviewed this spike independently, each in its own detached worktree
at the frozen sha (they write, so they cannot share one). All three re-ran the
harness and reproduced every filled cell. All three **rejected this spike's first
conclusion**, which had proposed changing the readers, and all three independently
arrived at the same end-state: `$id` is bare, fix the writer.

What they found that this spike had not:

| finding | by | verified here |
|---|---|---|
| The written rule exists — `planner.artifact-naming.schema-identifier` (active) | codex, zcode | yes, §2 |
| A *third* active node, `validation-rules:18`, prescribes `urn:contract:{name}` | zcode | yes, §2 |
| world3 — a bare 3-segment `$id` under a `contract` theme breaks c4 | codex, claude | yes, §4 |
| "replace-all is what makes it a warning" is false | zcode | yes — world1 under `r` still warns |
| The writer alone emits the doubled `$id` under a `contract` theme | zcode | yes, §8 |
| The blast-radius result is **vacuous for c4** | claude | yes — all 21 `$id`s are bare, so c4's branch never fires; it measures inertness, not safety |
| `c3+r` is also clean on worlds 1 and 2; "c4+r is the only clean combination" was false | claude | conceded — never run |
| Four reader sites beyond the graph module | claude | yes, §5 (found here independently) |
| Harness defects: `measure.py` world1-only, `candidates.py` always exits 0 | all three | fixed; see the lab README |

The one recommendation **not** adopted, and why. claude argued the resolver fix is
not strip-once but *normalize both sides of the comparison* (as
`contract_resolution.py:106,111` does), because under a prefixed `$id` the exact-match
strategies can never fire and resolution silently degrades to path-derivation —
demonstrated on world4, a contract off its convention path. Measured, that is true
**of E1 only**. world5 is world4 with the writer fix applied — bare `$id`, still off
its convention path:

```
world5  none: 0 issues    r: 0    n: 0    r+n: 0
```

Clean with **no resolver change at all**: strategy 1 matches the `$id` exactly,
path notwithstanding. So normalize-both-sides is a *transition-window* measure for
repos still holding prefixed `$id`s, not a permanent requirement — and the
objection it rests on is an argument against E1, which is already rejected.

The deeper point survives and is worth keeping: every candidate this spike first
considered was a string heuristic over an ambiguous string. The reason the answer
is "fix the writer" is that no heuristic over `$id` can be correct while two
spellings exist.


## Conclusion

Six defects, one causal chain:

1. `test_contract_id_format_follows_convention` documents the bare-`$id` rule but
   its regex cannot detect a violation — a check that cannot establish its answer
   reports the clean answer.
2. `create_contract` (`author.py:1097`) therefore shipped writing a forbidden
   prefixed `$id`, while writing the registry identity bare.
3. E008-UNIT-001 froze that violation into a GREEN acceptance.
4. `ContractResolver.resolve` (`resolver.py:756`) strips `contract:` with
   `str.replace`, i.e. every occurrence — an independent latent bug that breaks
   any identity whose own theme is `contract`.

   *Correction:* an earlier draft of this spike claimed the `replace`-all bug was
   also what degrades defect 2 from a hard error to a soft warning. Measured, that
   is false: world1 under `r` still reports a warning, because the doubled URN
   resolves under strip-once too — by exact `$id` match instead of the path
   fallback. The softness comes from the resolver's fallback strategies, not from
   `replace`-all. Flagged by an adversarial reviewer and reproduced here.

5. Nothing reserves `contract` as a theme name, so the writer itself can emit the
   doubled `$id` (measurement 8) and `$id → URN` is not a function.
6. The written corpus contradicts itself: `validation-rules` (active) prescribes a
   third spelling, `urn:contract:{artifact_name}`, that no artifact and no code
   uses. Nothing detects the disagreement between two active convention nodes.

The fix is at the writer, the gate and the conventions — not the readers. Details
in the plan.

## What this cost and returned

About three hours, including one adversarial review round against three models. The spike's **first**
conclusion was wrong in the same direction as the report — it proposed changing
the readers (c4) — and was overturned by a counterexample that a code reading
would never have constructed. Reading alone would have shipped a fix that turns a
warning into an error on legal input, applied six times, against the repo's own
written convention.
