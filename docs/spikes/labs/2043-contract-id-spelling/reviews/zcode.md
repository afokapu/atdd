# Adversarial review — contract `$id` double-prefix brief

Reviewed at sha `36ce055ae5056d7a0f7d012c1e4aaa5df628ce51` (verified). All
measurements below were re-run in this worktree against this checkout
(`PYTHONPATH=/private/tmp/ctr-review-zcode/src`).

## Verdict

**The bug is real and reproduces exactly as measured. But the brief's central
normative claim is false, its chosen end-state contradicts the repo's own active
written convention, and candidate c4 is not just "ambiguous in an exotic case" —
I constructed an input where c4+r gives a wrong answer that `r` alone gets
right.** The engineering measurements survive adversarial re-run; the diagnosis
("no rule says which wins") and the E1/E2 cost argument do not.

---

## 1. Citation audit (brief §2)

Every fact was checked against this worktree. Facts: **11/11 true**. Line
numbers: **8/11 exact, 3 with drift**.

| # | Citation | Verdict |
|---|---|---|
| 1 | `author.py:1095` | **Line off by 2** — `$id` write is `author.py:1097` (`"$id": f"contract:{identity}"`); 1095 is `doc: dict = {`. Fact true. |
| 2 | `author.py:1055-1059` | Accurate — `"identity": identity` at 1057; docstring at 1047-1051 states identity is bare. **But only conditionally true** (see §5, seam gap). |
| 3 | `tests/...test_e008_unit_001...py:37,50` | **Lines off** — the `$id` assert is line 38; the `"contract:" not in entry["identity"]` assert is line 54 (37 is the `json.loads`, 50 is the theme assert). Facts true; test re-run here: **2 passed, GREEN confirmed**. |
| 4 | `resolver.py:848` | Exact — `urn=f"contract:{contract_id}"` in `_contract_declaration`. |
| 5 | `graph_builder.py:910` | Exact — `return f"contract:{schema_id}"` in `_contract_urn_from_schema`. |
| 6 | `graph_builder.py:1544` | Exact — `urn=f"contract:{schema_id}"` in `_jel_contract_node`. Slightly misleading to lump under "the same": JEL `$id`s start with `urn:jel:` (1534), so this emits `contract:urn:jel:…`, a deliberate composite, not the `contract:` doubling. c4 leaves it untouched. |
| 7 | `graph_builder.py:883-884` | Exact — pass-through of `contract:`-prefixed refs. |
| 8 | `edge_validator.py:450-452` | Accurate — `_has_producer` spans 450-453; pure `get_incoming_edges` lookup, no normalization. |
| 9 | `resolver.py:756` | Exact — `urn.replace("contract:", "")` replaces **every** occurrence. |
| 10 | `urn_grammar.yaml:92` | Exact — pattern admits `contract:contract:…`. Note it requires ≥2 post-family segments, so `contract:result` is *not* a valid URN — this is what makes c4 behave differently in world2 vs world3. |
| 11 | `contract_resolution.py:34-41` | Exact — `normalize_identity` strips one prefix. |

Supporting claims also checked: 21 contract schemas, all bare `$id`s (listed;
`commons:binding-lock`, `frontend:train:render-metadata` among them) — true.
`theme_map.py:82-120` consumer theme overrides — true (`get_theme_map`, `.atdd/config.yaml`
`themes:` block; `match` is default theme 3, so world1 is a legal default-config
repo). `contract_resolution.py:94-113` non-canonical-path support — true (the
`$id` scan is at 110-113).

**Misleading-in-effect citation:** none rise to "wrong", but #1 and #3 would
send a reader to the wrong lines, and #6 implies a shared defect where the JEL
site is a different scheme.

## 2. Lab re-run (brief §6) — numbers

Harness fidelity: `lab/candidates.py` monkeypatches the real
`_contract_declaration`, `_contract_urn_from_schema`, and `resolve` and re-runs
the real `GraphBuilder.build()` + `EdgeValidator.validate_contracts()`. The
instrument is honest. Three harness/brief nits:

- `lab/measure.py:15,22` **hardcodes world1's paths** (`contracts/match/result.schema.json`,
  `plan/score_match/_score_match.yaml`). The brief says "`lab/measure.py <world>`
  prints the raw facts" — it **crashes on world2** (FileNotFoundError, rc=1).
- `lab/candidates.py:176` — `sys.exit(0 if ... >= 0 else 1)` is always 0, so the
  brief's "capture rc from the command itself" advice is vacuous: rc carries no
  signal for any run in this review.
- Brief §6's own snippet contains `lab/candidates.py /tmp/ctr-$r-world none` —
  `$r` is undefined there; that line measures `/tmp/ctr--world`, which does not
  exist.

World1 raw facts (`lab/measure.py`) — **match the brief exactly**:
`$id 'contract:match:result'`, registry `'match:result'`, manifest
`'contract:match:result'`, nodes `['contract:contract:match:result',
'contract:match:result']`, edge `wagon:score-match → contract:match:result`,
1 warning on the doubled node. Mechanism note: the second node is not
file-backed — `TraceabilityGraph.add_edge` auto-creates it from the manifest
edge target (`graph_builder.py:963-967`); the file node comes from the
declaration scanner. So "split identity" = one declaration node + one
edge-manufactured node. The brief's description is correct.

Candidate matrix (issues; both worlds re-run by me):

| world | none | c1 | c3 | c4 | r | c4+r |
|---|---|---|---|---|---|---|
| world1 | 1 warn + split | 0 | 0 | 0 | 1 warn + split | 0 |
| world2 | 1 error | 1 error + split + ungrammatical | 1 error | 1 error | **0 (brief said "—")** | 0 |

**Difference from the brief, stated loudly:** the brief left world2×`r` as
"not measured". I measured it: **r alone scores 0 in world2**. This matters for
the argument: `r` is the only single change that repairs world2, and world2 is
the world built from the toolkit's own majority spelling (bare `$id`). The
brief's reading "the two defects are independent and both are needed" is true
only *under E1*; under E2 neither c4 nor r is needed for world1 (the writer
stops emitting prefixed `$id`s), and `r` remains needed for world2 as an
independent latent bug.

Blast radius on this repo's real data: baseline vs c4r outputs are identical
except the label line — same 21 nodes, same 19 produces edges, same 2 warnings
by name (`commons:documentation-verdict`, `frontend:train:render-metadata`).
**The brief's "byte-identical" claim is confirmed.**

One causal claim in the brief is **wrong**: "the replace-all bug … is also what
makes the reported case a soft warning rather than a hard error." False — under
`r` (strip-once), world1's doubled node still resolves (strip-once →
`contract:match:result` → exact `$id` match, strategy 1) and the issue stays a
soft warning, as my re-run of world1×r shows. The softness comes from the
resolver's fallback strategies, not from replace-all.

## 3. The attack: c4+r gives a wrong answer (brief §5 Q3)

**World3 (constructed, measured; builder kept at
`/tmp/ctr-zcode-world3/build_world3.py`):** a consumer repo overrides theme 1 to
`contract` (legal, `theme_map.py:100-118`), and authors a contract under the
**active written convention** — bare `$id`:

- `$id` = `contract:match:result` (bare identity, theme `contract`, 3 segments)
- file at the convention path `contracts/contract/match/result.schema.json`
- manifest correctly declares the URN `contract: contract:contract:match:result`

This is exactly the brief's own world2 with one added segment — squarely inside
its own threat model, and it is the spelling the repo's active convention
prescribes (see §4). Results (all six candidates re-run):

| world3 | none | c1 | c3 | c4 | r | c4+r |
|---|---|---|---|---|---|---|
| issues | 1 error | 1 error + split | 1 error | 1 error + split | **0** | **1 error + split** |

```
--- r            (clean: single node, resolved, producer attached)
    contract nodes : ['contract:contract:match:result']
    produces edges : [('wagon:settle-contract', 'contract:contract:match:result')]
    issues         : 0
--- c4r          (wrong answer)
    contract nodes : ['contract:contract:match:result', 'contract:match:result']
    produces edges : [('wagon:settle-contract', 'contract:contract:match:result')]
    issues         : 1
      - [error] contract:match:result :: Contract URN broken: Contract schema not found for: contract:match:result
```

Why it breaks: `contract:match:result` starts with `contract:` **and** validates
against the grammar (`urn_grammar.yaml:92` needs ≥2 post-family segments —
world2's 2-segment `contract:result` does not, world3's does), so c4 takes it
as-is and keys the file node `contract:match:result`, while the manifest
pass-through (`graph_builder.py:883-884`) targets `contract:contract:match:result`.
The declaration node then resolves through `graph_builder.py:771` under r's
strip-once → `match:result` → path `match/result` ≠ `contract/match/result` →
`is_broken` → **a false "schema not found" error on a file that exists, is
correctly placed, and follows the written convention**, plus the split identity.

So the brief's "known weakness" understates it: c4 does not merely stay
ambiguous — it **converts an input that `r` alone scores 0 into an error +
split**. Adding c4 to r is strictly harmful on this input class. The brief's
claim that stage 2 "removes it permanently" is true only for repos that run the
migration; consumer repos following the bare-`$id` convention keep mis-keying
from stage 1 until stage 3 *breaks them outright*.

A second, writer-side instance of the same seam (measured): with theme
`contract` configured, `create_contract({"identity": "contract:match:result"})`
is **accepted** — `validate_contract`'s regex (`author.py:942-944`) doesn't
forbid a leading `contract` segment and the theme check passes — and it writes
`$id: contract:contract:match:result` plus a registry `identity` of
`contract:match:result`, violating the documented "identity is bare" registry
shape (`author.py:1047-1051`) and `planner.contract.registry-coherence.convention.yaml:20`
("the contract: URN prefix is stripped before lookup" — an identity that still
carries the prefix double-strips in such consumers). Nothing rejects the
doubled spelling at the door; fact #2's "writes the registry identity bare" is
true only by convention, not by enforcement.

## 4. Was there a written rule? Yes — two, and they contradict each other

The brief's load-bearing claim — "no rule says which wins… a convention nobody
wrote down" — is **false**:

- `planner.artifact-naming.schema-identifier.convention.yaml:6-16` (**kind:
  rule, status: active**, high-fidelity extraction, reviewed 2026-06-16):
  "A contract's `$id` is the clean artifact name {theme}:{resource}[.{category}]
  with NO 'urn:contract:' prefix… `$id` = clean artifact identifier…
  urn_reference (in wagon produce/consume) = contract:{artifact_name}."
- `planner.artifact-naming.urn-structure.convention.yaml:6` (active):
  "A contract URN exactly matches the artifact name… contract:{artifact_name}"
  — i.e. the URN is prefix + **bare** name.
- `planner.contract.registry-coherence.convention.yaml:20` (active): registry
  keys are bare identities; the prefix is stripped before lookup.

There is also a genuine contradiction inside the written corpus:
`planner.artifact-naming.validation-rules.convention.yaml:18` (active
constraint) says "…`$id` is urn:contract:{artifact_name}" — a third spelling
matching neither the 21 artifacts nor the writer.

Consequences: (a) a written rule does exist and it prescribes **bare `$id`**
(E2); (b) `create_contract`'s prefixed form matches **neither** active rule;
(c) the real documentation defect is the internal contradiction between
`schema-identifier` and `validation-rules`, which the proposal should resolve
rather than deepen. The brief did not cite any of these three files.

## 5. Answers to the five questions

**1. Is the diagnosis right?** Half. "Two spellings in code" — yes, verified.
"No rule says which wins" — no: `schema-identifier.convention.yaml:6` is an
active rule that picks bare, and the readers (`resolver.py:848`,
`graph_builder.py:910`) implement it. The correct diagnosis is: *the writer
defects from a written convention that the readers follow, and a second active
constraint contradicts that convention.* That reframes everything downstream.

**2. Is E1 the right end-state?** No — E2 is, and the brief's cost argument is
backwards. E1 ("the `$id` IS the URN") requires amending an active convention
(the same class of operation as re-opening a plan artifact, but higher
authority), rewriting 21 convention-conformant artifacts to match the deviant
spelling, and adding a stage-2 validator (`$id == contract:{registry identity}`)
that hard-codes a contradiction of `schema-identifier`. The brief's dismissal of
E2 — "requires changing a GREEN acceptance… same cost, worse provenance" — has
the provenance inverted: E2 has the active rule, all 21 artifacts, every reader,
the registry shape, and `normalize_identity` (`contract_resolution.py:34-41`,
which the brief itself cites as the planner layer's prior solution) on its side.
E2's actual cost: one line in `create_contract` (`author.py:1097` → write bare),
one test file's two asserts, and migrating the (new, few) prefixed artifacts
already written in consumer repos. E2 also needs **no reader heuristic at all**
— no c4, no ambiguity window, nothing to tighten in stage 3. `r`
(`resolver.py:756` strip-once) is worth shipping under either end-state; it is
an independent latent bug my re-runs confirm (world2 baseline error, world3
baseline error).

**3. Does c4+r have a failure mode the labs didn't construct?** Yes — world3
(§3 above): a false "Contract URN broken" error plus split identity on a
convention-conformant bare `$id`, where `r` alone scores 0. Additionally, the
fix surface is incomplete even under E1: the produce-side `urn:` override
(`graph_builder.py:977-980`) passes any `contract:*` through un-normalized, and
the JEL reader (`graph_builder.py:1544`) still reconstructs URNs from
fragments — "readers stop reconstructing a URN" overclaims.

**4. Is staging correct?** No. Stage 1 front-loads the risky half (c4, a
heuristic with a demonstrated false positive on the majority spelling) and
back-loads the cheap half (a one-line writer change). If anything ships "now"
it should be `r` alone plus the E2 writer change — that fixes world1 (no more
prefixed `$id`s emitted), world2, and world3 with zero heuristics. The brief's
staging exists to protect E1, and E1 is the wrong end-state. Bundling the
migration with the fix (the brief's own alternative) is also cheaper under E2
because the migration is "delete the prefix from artifacts the writer created,"
not "rewrite 21 conformant artifacts to a new spelling."

**5. What did the brief get wrong?** In order of severity:
1. "No rule says which wins / a convention nobody wrote down" — falsified by
   `schema-identifier.convention.yaml:6` (active), `urn-structure.convention.yaml:6`,
   and `registry-coherence.convention.yaml:20`; it also missed the genuine
   contradiction with `validation-rules.convention.yaml:18`.
2. E1 contradicts the active written rule; the E2 rejection ("worse
   provenance") is inverted.
3. c4's "known weakness" is actually a demonstrated wrong answer (world3):
   false error + split where `r` alone is clean.
4. "the replace-all bug … makes the reported case a soft warning" — false
   (world1×r stays a soft warning).
5. world2×`r` was left unmeasured ("—"); it scores 0, which weakens the
   "both halves needed" framing outside E1.
6. Citation drift: #1 (1095→1097), #3 (37,50→38,54); #6's JEL site is a
   different composite scheme, not the same doubling.
7. Lab/brief mechanics: `measure.py` hardcodes world1 paths and crashes on
   world2; `candidates.py` always exits 0 (rc is not a signal); §6's
   `/tmp/ctr-$r-world` line references an undefined variable.

## What survives

The reported defect is real, the split-identity mechanism is correctly
explained, the world1/world2 measurements reproduce exactly, and the
blast-radius claim is confirmed. The recommended fix, revised: **adopt E2**
(make `create_contract` write the bare `$id` per `schema-identifier`, update the
one acceptance test), **ship `r`** (strip-once in `ContractResolver.resolve`),
**drop c4**, and reconcile `validation-rules.convention.yaml:18` with
`schema-identifier` so the written corpus stops contradicting itself. Nothing in
src/ was modified for this review; world3's builder lives in /tmp only.
