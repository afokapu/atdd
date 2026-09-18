# Adversarial review brief — contract `$id` double-prefix breaks traceability

**Frozen sha: 36ce055ae5056d7a0f7d012c1e4aaa5df628ce51** (repo `afokapu/atdd`).
You are in a detached worktree at that sha. It is yours; nobody else writes it.

Your job is to **falsify** what follows. Do not agree politely. If the diagnosis
is wrong, say so and show where. If the measurements do not support the
conclusion, say so. If there is a better fix, name it and say what it costs.
Systemic and systematic: check the whole seam, not the line that was reported.

---

## 1. The report (from an agent in a consumer repo — provenance: REPORTED, not verified by them)

> - the wagon manifest declares `contract: contract:match:result`
> - the schema's `$id` is `contract:match:result` — written by the tool's own `create_contract`
> - the traceability graph keys the node `contract:contract:match:result`
>
> The graph builder prepends the `contract:` family prefix to an `$id` that already
> carries it, so `_has_producer` looks for an edge to a URN no producer can ever
> name. Every contract authored by `create_contract` is structurally untraceable,
> whatever the wagons declare.

## 2. What the code says (DERIVED — every claim has a file:line)

| # | Fact | Citation |
|---|---|---|
| 1 | `create_contract` writes `$id` = `f"contract:{identity}"` — the **family-prefixed** form | `src/atdd/planner/commands/author.py:1095` |
| 2 | ...and writes the registry `identity` **bare** (no prefix) | `src/atdd/planner/commands/author.py:1055-1059` |
| 3 | That split is pinned by a GREEN acceptance: asserts `$id == "contract:commons:compliance:probe"` AND `"contract:" not in entry["identity"]` | `src/atdd/planner/commands/tests/test_e008_unit_001_derives_path_id_and_registers.py:37,50` |
| 4 | The graph's declaration scanner keys the node `f"contract:{$id}"` | `src/atdd/coach/utils/graph/resolver.py:848` |
| 5 | The graph builder does the same when resolving a produce/consume ref by file | `src/atdd/coach/utils/graph/graph_builder.py:910` |
| 6 | ...and again for JEL nodes | `src/atdd/coach/utils/graph/graph_builder.py:1544` |
| 7 | A manifest ref that already starts with `contract:` is passed through **unchanged** | `src/atdd/coach/utils/graph/graph_builder.py:883-884` |
| 8 | `_has_producer` is pure edge lookup — no normalization | `src/atdd/coach/utils/graph/edge_validator.py:450-452` |
| 9 | `ContractResolver.resolve` strips the prefix with `urn.replace("contract:", "")` — **every** occurrence, not just the leading one | `src/atdd/coach/utils/graph/resolver.py:756` |
| 10 | The contract URN grammar admits `contract:contract:...` as well-formed, so nothing rejects the doubled URN | `src/atdd/coach/utils/graph/urn_grammar.yaml:92` |
| 11 | The planner layer already solved this for itself with `normalize_identity` (strip one optional `contract:`) | `src/atdd/planner/interlocking/contract_resolution.py:34-41` |

**The asymmetry nobody mentioned:** all 21 contracts in this repo carry a **bare**
`$id` (`commons:binding-lock`, `frontend:train:render-metadata`, …) and their
manifests declare the full URN (`contract: contract:commons:binding-lock`). So
`"contract:" + $id` is *correct here* and the toolkit's own graph is clean. The
defect only fires on contracts authored by `create_contract` — i.e. exactly the
ones the tool itself writes. None of this repo's own contracts were authored that
way; they predate the writer.

## 3. What was MEASURED (spike; real code paths, disposable world)

Lab 1 (`world`): throwaway repo, contract authored by the **real** `create_contract`,
plus a wagon manifest declaring `contract: contract:match:result`. Real
`GraphBuilder.build()` + real `EdgeValidator.validate_contracts()`.

```
schema $id                  : 'contract:match:result'
registry identity           : 'match:result'
manifest produce[].contract : 'contract:match:result'
graph contract NODES        : ['contract:contract:match:result', 'contract:match:result']
graph produces EDGES        : [('wagon:score-match', 'contract:match:result')]
validate_contracts issues   : 1
  - [warning] contract:contract:match:result :: Contract has no producing wagon
```

Report confirmed — and it **understated** it. The graph holds a **split identity**:
a file-backed node nobody produces, plus a producer-backed node with no file. The
reported symptom is only the warning; the structural damage is two nodes where
there is one contract.

Lab 2 (`world2`): a consumer repo whose theme map names a theme `contract`
(themes are consumer-overridable — `planner.artifact-naming.theme-taxonomy`,
`src/atdd/coach/utils/theme_map.py:82-113`). Hand-authored **bare** `$id`
`contract:result`, correct manifest `contract: contract:contract:result`.
This is the case that discriminates between candidate fixes.

Candidates measured (real methods monkeypatched, real graph build re-run):

- **c1 — blind strip**: `urn = "contract:" + $id.removeprefix("contract:")`
- **c3 — path-derived**: identity from the file's location under `contracts/`
- **c4 — $id-is-already-a-URN**: if `$id` starts with `contract:` *and* parses as a
  valid contract URN, use it as-is; otherwise prefix it
- **r — resolve fix**: `urn.replace("contract:", "")` → strip the prefix **once**

| world | none | c1 | c3 | c4 | r | c4+r |
|---|---|---|---|---|---|---|
| world1 (reported case) | 1 warn + split node | 0 | 0 | 0 | **1 warn + split node** | **0** |
| world2 (theme named `contract`) | 1 error | **1 error + split + ungrammatical URN** | 1 error | 1 error | — | **0** |

Readings:
- **c1 regresses** world2: it mangles a legitimate `contract`-themed identity into
  `contract:result`, which fails the contract grammar outright.
- **r alone does not fix the reported bug** (world1 unchanged) — so the two defects
  are independent and both are needed.
- **c4+r is the only combination clean in both worlds.**
- A **third, unreported defect** surfaced: in world2 even the *baseline* is broken,
  because fact #9's `replace`-all strips both occurrences of `contract:` and the
  file is then never found. That bug is latent today and is also what makes the
  reported case a soft warning rather than a hard error.

Blast radius (candidate c4+r applied to **this repo's real data**, 21 contracts):
output **byte-identical** to baseline — same 21 nodes, same 19 produces edges,
same 2 pre-existing warnings **by name** (`commons:documentation-verdict`,
`frontend:train:render-metadata`). Zero regressions, zero new findings.

## 4. The proposal you must attack

**Diagnosis:** not "the graph builder is wrong". There are **two spellings of a
contract's `$id`** — bare (21/21 existing artifacts, the registry, every reader)
and prefixed (`create_contract`, pinned by a GREEN acceptance) — and no rule says
which wins. The readers are only wrong *relative to a convention nobody wrote down*.

**Chosen end-state (E1): the `$id` IS the URN.** `create_contract` is already
right; the readers stop reconstructing a URN from a fragment. Registry `identity`
stays bare — identity and URN are legitimately different things, and
`_insert_contract_registry` already documents that.

Rejected alternative **E2** (`$id` is bare everywhere): requires changing a GREEN
acceptance, i.e. re-opening a landed plan artifact, and still needs a consumer-side
migration. Same cost, worse provenance.

**Staged:**
1. **Ships now** — readers adopt c4 (facts #4/#5/#6) + the strip-once fix (#9),
   plus guard tests that are fault-injected (revert the fix, watch them go red).
   Backward compatible: bare `$id` keeps working, prefixed `$id` stops doubling.
   Fixes the consumer repo with **zero artifact edits**.
2. **Migration** — rewrite this repo's 21 bare `$id`s to the prefixed form; add a
   validator that a contract's `$id` equals `contract:{registry identity}`. This is
   what actually kills the ambiguity.
3. **Tighten** — once stage 2 is strict, drop the bare-`$id` tolerance from stage 1.

**Known weakness, stated:** stage 1's c4 is still ambiguous for a *bare* identity
whose theme is literally `contract` **and** which has 3+ segments (e.g. bare
`contract:match:result` is indistinguishable from prefixed `match:result`). Stage 2
removes it permanently. c3 (path-derived) is immune but mis-keys any contract not
at its convention path, which `contract_resolution.py:94-110` deliberately supports.

## 5. Questions to answer

1. Is the diagnosis (two spellings, no rule) right, or is there a written rule I missed?
2. Is E1 the right end-state, or is E2 / something else better? Argue cost.
3. Does c4+r have a failure mode the two labs did not construct?
4. Is staging correct, or should the migration land with the fix?
5. What did I get wrong?

Answer in prose with citations. Be specific. Disagreement is the deliverable.
