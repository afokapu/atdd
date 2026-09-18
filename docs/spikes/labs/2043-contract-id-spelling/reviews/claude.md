# Adversarial review — contract `$id` double-prefix

Worktree `/private/tmp/ctr-review-claude`, sha `36ce055ae5056d7a0f7d012c1e4aaa5df628ce51` (verified).
Everything below was re-measured in this checkout with `PYTHONPATH=/private/tmp/ctr-review-claude/src`.

**Verdict:** the *diagnosis* is roughly right and the *fix is wrong*. I broke c4+r with a
repo shape the brief itself names in section 4 and then never built. Separately, the brief
under-scopes the seam by four reader sites, and the fix it proposes for defect #9 is the
wrong fix — which its own labs would have shown with one more world.

---

## 1. Citation audit (section 2)

| # | Cited | Actual | Verdict |
|---|---|---|---|
| 1 | `author.py:1095` | **1097** (`"$id": f"contract:{identity}",`) | **wrong line** |
| 2 | `author.py:1055-1059` | `"identity": identity,` at 1057 | ok |
| 3 | `test_e008_…:37,50` | **38** (`$id ==`) and **54** (`"contract:" not in`) | **both wrong** |
| 4 | `resolver.py:848` | 848 | ok |
| 5 | `graph_builder.py:910` | 910 | ok |
| 6 | `graph_builder.py:1544` | 1544 | line ok, **claim misleading — see below** |
| 7 | `graph_builder.py:883-884` | 883-884 | ok |
| 8 | `edge_validator.py:450-452` | `_has_producer` is 450-**453**; the `return any(...)` is at 453 | range truncated, claim correct |
| 9 | `resolver.py:756` | 756 | ok |
| 10 | `urn_grammar.yaml:92` | 92 | ok — I confirmed `contract:contract:match:result` matches the pattern |
| 11 | `contract_resolution.py:34-41` | 34-41 | ok |

### 1a. Fact #6 is dead code, and the proposal builds on it

`_jel_contract_node` is guarded at `src/atdd/coach/utils/graph/graph_builder.py:1534-1535`:

```python
schema_id = data.get("$id", "")
if not schema_id.startswith("urn:jel:"):
    return None
```

It returns `None` for anything that is not a JEL header, so it can **never** see a
`contract:`-prefixed `$id`. Listing it as one of three defective readers is misleading, and
section 4's "readers adopt c4 (facts #4/#5/**#6**)" would add unreachable code at 1544.
Your own harness agrees with me and not with your prose: `lab/candidates.py` patches only
`ContractResolver._contract_declaration` (#4) and `GraphBuilder._contract_urn_from_schema`
(#5). **The measurement and the proposal disagree about the fix's own scope.**

### 1b. Section 2 is incomplete — four more readers do the same thing

`grep -rn 'f"contract:{' src/atdd --include='*.py'` finds these, none of which the brief
lists, all of which read `$id` and prepend the family prefix:

- `src/atdd/coach/commands/registry.py:983` — `"urn": f"contract:{schema_id}"`, `$id` read at 978. This is what `atdd registry` writes into `contracts/_artifacts.yaml`.
- `src/atdd/coach/commands/consumers.py:258` — `contract_id_map[f"contract:{contract_id}"] = rel_path`.
- `src/atdd/tester/validators/test_contract_schema_compliance.py:212` — `{f"contract:{cid}" for cid in collect_contract_ids()}`, and `collect_contract_ids` reads `$id` at line 87. Every `$ref`/dependency check at 229 and 248 compares against that set.
- `src/atdd/tester/validators/test_telemetry_structure.py:95` — `urns.add(f"contract:{contract_id}")`, `$id` read at 93.

So section 4's promise — *"Fixes the consumer repo with **zero artifact edits**"* — is **not
supported**. Stage 1 as scoped fixes the traceability graph and leaves `atdd registry`, the
consumer scanner, and two platform validators double-prefixing. A consumer repo would get a
clean `atdd graph` and a still-broken `atdd registry`. "Systemic and systematic: check the
whole seam" was your instruction; the seam is 7 sites, not 3.

---

## 2. Re-running the lab (section 6)

Harness problems first, because they affect how much the numbers are worth:

- **`lab/candidates.py:163`**: `sys.exit(0 if measure(root, which) >= 0 else 1)`. `len(issues) >= 0` is a tautology — **the exit code is always 0**. Section 6 says "Capture rc from the command itself, not from a pipe"; there is nothing to capture. I confirmed `world2 / none`, which emits a hard `[error]`, exits 0.
- **`lab/measure.py:15`** hardcodes `contracts/match/result.schema.json`. Section 6 advertises `lab/measure.py <world>` as a general tool; it raises `FileNotFoundError` on `world2` (rc=1). Only `world1` is measurable this way.
- Section 6's own command block contains `lab/candidates.py /tmp/ctr-$r-world none`. `$r` is unset, so this expands to a nonexistent path.

### Numbers I got

**Every cell the brief filled reproduces exactly**, including `world1`'s raw facts — same
`$id`, same registry identity, same two nodes, same single produces edge, same warning text.
Credit where due: world1 is a clean, honest repro.

The full matrix I measured (`w1`/`w2` are the brief's; `w3`/`w4` are mine, see §3-4):

| | none | c1 | c3 | c4 | r | c1+r | c3+r | c4+r | c4+r+n | c5+r+n |
|---|---|---|---|---|---|---|---|---|---|---|
| **w1** reported case | 1 warn + split | 0 | 0 | 0 | 1 warn + split | 0 | **0** | **0** | 0 | **0** |
| **w2** theme `contract`, 2 seg | 1 err | 1 err + split + ungrammatical | 1 err | 1 err | **0** | 1 err + split | **0** | **0** | 0 | **0** |
| **w3** theme `contract`, 3 seg | 1 err | 1 err + split | 1 err | **1 err + split** | **0** | 1 err + split | **0** | **1 err + split** | 1 warn + split | **0** |
| **w4** off-convention path | 1 err + split | 1 err | 1 warn + split | 1 err | 1 warn + split | — | 1 warn + split | **1 err** | 0 | **0** |

**The cell you left blank is the one that breaks your conclusion.** You wrote `—` for
`world2 / r`. I measured it: **0 issues.** That means:

1. **"c4+r is the only combination clean in both worlds" is false on your own two worlds.**
   I measured **c3+r: 0 in world1, 0 in world2.** You never ran it. `c1+r` is genuinely bad
   (world2 still errors), so c1 is correctly rejected — but c3 is not.
2. **World2 does not discriminate between the candidates you are actually choosing between.**
   `none`, `c3` and `c4` all produce the identical single error in world2, and that error is
   purely defect #9. World2 separates `c1` from everything else. It says nothing about c3 vs
   c4 — which is the decision section 4 makes. Calling it "the case that discriminates
   between candidate fixes" overstates what it does.

### Blast radius — reproduced, and vacuous for c4

I ran `lab/candidates.py . none` and `. c4r` against this repo. Output is **byte-identical
apart from the label line**: 21 nodes, 19 produces edges, the same 2 warnings
(`commons:documentation-verdict`, `frontend:train:render-metadata`). Your claim holds.

It also proves nothing. I dumped all 21 `$id`s — every one is bare (`commons:binding-lock`
… `frontend:train:render-metadata`). c4's branch is `if schema_id.startswith("contract:")`,
which is False for all 21, so **c4 is a no-op on this repo by construction**. "Zero
regressions" here means "inert where every input is bare." The state that would have
mattered is stage 2's *migrated* repo, and that was not measured.

---

## 3. Breaking c4+r — world3

Section 4 states the weakness in prose: *"stage 1's c4 is still ambiguous for a bare identity
whose theme is literally `contract` and which has 3+ segments (e.g. bare `contract:match:result`
is indistinguishable from prefixed `match:result`)."* You named it and then published a table
saying c4+r is 0/0. I built it (`/tmp/ctr-claude-lab/build_world3.py`), reusing world2's own
premise — the `themes: {1: contract}` override — and adding one segment:

- `$id`: `contract:match:result` (**bare**, theme `contract`, hand-authored — the spelling 21/21 of this repo's contracts use)
- manifest: `contract: contract:contract:match:result` (correct: family prefix + bare identity)

```
##### world3 / c4r
    contract nodes : ['contract:contract:match:result', 'contract:match:result']
    produces edges : [('wagon:settle-contract', 'contract:contract:match:result')]
    issues         : 1
      - [error] contract:match:result :: Contract URN broken: Contract schema not found for: contract:match:result

##### world3 / r
    contract nodes : ['contract:contract:match:result']
    produces edges : [('wagon:settle-contract', 'contract:contract:match:result')]
    issues         : 0
```

**c4+r is not merely unhelpful here — it regresses.** Baseline has one error and *one* node.
c4+r has one error and *two* nodes: the split identity that section 3 correctly calls "the
structural damage." And `r` **alone** is clean. So on world3, c4 is strictly negative.

Why the grammar saves you in world2 and not world3: `urn_grammar.yaml:92` is
`^contract:[a-z][a-z0-9-]*(:[a-z][a-z0-9-]+)+…$` — the trailing group is `+`, so at least
three segments are required. `contract:result` fails validation, c4 falls through to the
prefix branch, and world2 looks clean *by accident of a minimum-segment-count rule*.
`contract:match:result` passes, and c4 fires. World2's 2-segment identity is the only reason
the weakness stayed hidden.

This is not exotic. Section 2's own asymmetry note shows the 3-segment shape is the normal
one here — `commons:coach:dashboard-card`, `commons:compliance:gate`,
`frontend:train:render-metadata`. The only unusual ingredient is the theme name, and that
ingredient is already conceded as legal by world2.

**Therefore section 4's "Backward compatible: bare `$id` keeps working" is false.** Bare
`$id` keeps working *except* for the shape c4 cannot distinguish, where it newly breaks.

---

## 4. A defect you missed: `r` is the wrong fix at #9, and E1 breaks resolution

Look at what `r` hands to `_find_contract_files` (`resolver.py:766-804`). All three match
strategies compare against a **bare** id:

- Strategy 1 (786): `file_id == contract_id`
- Strategy 2 (791-793): the same after `.`→`:` normalization
- Strategy 3 (798-802): the file's path under `contracts/` vs `contract_id.replace(":", "/")`

Strip-once passes `match:result` while a `create_contract`-authored file declares
`$id: "contract:match:result"`. Strategies 1 and 2 **can never fire under E1**. Only the
*path* strategy can. World1 hides this because the file sits at its convention path.

World4 (`/tmp/ctr-claude-lab/build_world4.py`): real `create_contract`, file then moved to
`contracts/shared/v1/match-result.schema.json`, manifest unchanged.

```
##### world4 / c4r
    contract nodes : ['contract:match:result']
    produces edges : [('wagon:score-match', 'contract:match:result')]
    issues         : 1
      - [error] contract:match:result :: Contract URN broken: Contract schema not found for: contract:match:result
```

The node key is now *correct* and the file still cannot be found.

**This is an internal contradiction in the proposal.** Section 4 rejects c3 because it
"mis-keys any contract not at its convention path, which `contract_resolution.py:94-110`
deliberately supports." But E1 reduces the coach-side resolver to path-derivation anyway —
it kills strategies 1 and 2 for every contract in every repo. **E1 buys exactly the weakness
it rejects c3 for, and charges a 21-file migration for it.**

And the fix at #9 is not "strip once". It is **normalize both sides** — which is precisely
what fact #11 actually does: `contract_resolution.py:106` and `:111` call
`normalize_identity()` on the *file's declared `$id`* and on the *target*, i.e. they apply
normalization to the **comparison**, never to a node key. Section 2 cites #11 as precedent
for c4. c4 is not what #11 does. #11 is the precedent for the fix I recommend below.

---

## 5. What I'd ship instead — c5 + n, measured

Neither c1, c3 nor c4 can work, because all three are *string heuristics over `$id`* (or over
the path) and the string is genuinely ambiguous. Stop guessing. There is a non-heuristic
disambiguator already on disk: `contracts/_contracts.yaml`, whose `identity` is bare **by
construction** (`author.py:1057`, guarded by the GREEN assertion at test line 54) and whose
`path` is written alongside it (`author.py:1058`).

- **c5** — the node URN for a registered schema is `contract:{registry identity}`; match by resolved path, falling back to normalized-`$id`; unregistered files keep today's behaviour.
- **n** — `_find_contract_files` compares `normalize_identity()` on **both** sides, exactly as `contract_resolution.py:106,111` already does.

No grammar sniffing, no path convention, no dependence on which spelling wins.

```
world1 c5+r+n : 0     world2 c5+r+n : 0     world3 c5+r+n : 0     world4 c5+r+n : 0
world1 c4+r+n : 0     world2 c4+r+n : 0     world3 c4+r+n : 1 (split node)   world4 c4+r+n : 0
world1 c3+r   : 0     world2 c3+r   : 0     world3 c3+r   : 0     world4 c3+r   : 1 (split node)
```

Against this repo's real 21 contracts, `c5+r+n` output is **identical to baseline** — same 21
nodes, same 19 produces edges, same 2 warnings by name. Same blast radius as c4+r, and it is
the only variant clean in all four worlds. (Harness: `/tmp/ctr-claude-lab/c5.py`, `run5.py`.
Nothing under `src/` was touched.)

Cost: one YAML read in the resolver, and `_find_contract_files` gains a normalized pass.
Crucially it makes E1-vs-E2 **non-urgent** — it is correct under both spellings, permanently,
because it never asks whether `$id` "is a URN".

---

## 6. The five questions

**1. Is the diagnosis right, or is there a written rule you missed?**

"Two spellings" — yes, and I confirm the convention layer is silent on it:
`src/atdd/planner/conventions/nodes/planner.artifact-naming.contract-file-mapping.convention.yaml`
governs *identity → file path* only, and its normative examples are bare
(`commons:identifiers.uuid -> contracts/commons/identifiers/uuid.schema.json`).

But **"no rule says which wins" is wrong.** There are rules; you counted only the prose ones.
On the prefixed side: the `author.py:1083` docstring, the GREEN acceptance at
`test_e008_…:38`, and `docs/smoke-audit.md:525` ("carries $id contract:{identity}"). On the
bare side there are **four executable rules** you never listed — `registry.py:983`,
`consumers.py:258`, `test_contract_schema_compliance.py:212`, `test_telemetry_structure.py:95`
— two of which are *platform validators that run in CI*. Executable rules outrank docstrings.
The rule is written, in code, four times, and it says **bare**. That inverts your cost
argument before it starts.

**2. Is E1 the right end-state?**

No, and E2 is much cheaper than you priced it. You price E2 as "changing a GREEN acceptance
+ a consumer migration" and E1 as "readers adopt c4." The real ledger:

- **E1**: 7 reader sites (3 named + 4 you missed), a 21-file artifact migration, a new validator, a deprecation stage, *and* the permanent loss of off-convention-path resolution demonstrated in world4 — the exact capability you cite to reject c3.
- **E2**: one line (`author.py:1097`), two assertions in one test (line 38; line 54 already passes either way), and **zero consumer migration**, because every existing reader is already bare-correct. A consumer repo's `create_contract`-authored files get rewritten by re-running the writer, not by hand.

"Same cost, worse provenance" is not supported. Re-opening a landed acceptance that pins one
writer's *output format* is a far smaller act than changing the identity model of seven
readers plus every artifact. Provenance is a real cost, but it is one artifact, not the
larger number.

My actual recommendation is neither first: ship **c5+n**, which is correct under both
spellings, then take E2 at leisure with the ambiguity already defanged.

**3. Does c4+r have a failure mode the labs did not construct?**

Three. (i) **world3** — bare `$id`, theme `contract`, 3+ segments: c4+r yields 1 error *and*
a split node, worse than baseline, while `r` alone is clean. You named this in prose and
never built it. (ii) **world4** — any contract off its convention path: c4+r errors, because
strip-once is the wrong fix at #9 (§4). (iii) The four unpatched readers in §1b are untouched
by c4+r in *any* world, because the harness only patches two methods.

**4. Is staging correct?**

No, in one specific way and one general one.

Specific: stage 1 is sold as "backward compatible: bare `$id` keeps working." World3 falsifies
that — it is backward compatible *except* on the shape c4 cannot distinguish, where it newly
regresses to a split node. A staged plan whose first stage regresses a currently-working repo
shape is not a safe first stage.

General: stage 3 ("drop the bare-`$id` tolerance") is a one-way door that can only be taken
once every consumer repo has migrated, and you do not control consumer repos — that is the
whole reason this arrived as a report from one. Stage 3 as written has no completion
criterion you can observe.

What I would land, in order: **(a) the resolution fix at #9 — normalize both sides, not strip
once — alone and immediately.** It is 0-regression on this repo, it fixes world2 and world3
outright with no node-keying change at all, and it is the only piece that is unambiguously a
*bug fix* rather than a *convention choice*. **(b) c5 node keying**, which closes world1 and
world4 and ends the ambiguity without any artifact edit. **(c) then** decide the spelling, at
which point the migration is a tidy-up rather than a correctness dependency — so no, the
migration should not land with the fix, but not for the reason you gave.

**5. What did you get wrong?**

- The `world2 / r` cell you marked `—` is **0**. It is the cell that decides the argument.
- "c4+r is the only combination clean in both worlds" — **c3+r is too** (measured 0/0). Never run.
- World2 "discriminates between candidate fixes" — it separates c1 from the rest and is blind to c3-vs-c4, the choice you actually made.
- Fact #6 (`graph_builder.py:1544`) is unreachable for this defect (guard at 1534-1535); section 4 proposes changing it; your own harness doesn't.
- Section 2 misses four reader sites, so "fixes the consumer repo with zero artifact edits" is false.
- "Backward compatible: bare `$id` keeps working" is false — world3.
- The blast-radius result is true and **vacuous**: all 21 `$id`s are bare, so c4's branch never fires; it measures inertness, not safety.
- `r` (strip-once) is the wrong fix at #9, and it makes E1 dependent on the path convention you reject c3 for.
- Three citation line numbers are off (#1 → 1097; #3 → 38, 54), and #8's range stops one line short of the code it describes.
- The harness always exits 0; `lab/measure.py` only works on world1; section 6's command block has an unset `$r`.

**What you got right**, since disagreement is not the same as dismissal: world1 is an exact,
honest repro. The severity read — that the split node, not the warning, is the real damage —
is correct and is the framing I used to break c4. The c1 regression is real and well
constructed. Flagging #9 as an unreported third defect was the best catch in the brief; it is
just larger than you described, and it is the one that should ship first.

---

### Reproduction

```sh
cd /private/tmp/ctr-review-claude
export PYTHONPATH=/private/tmp/ctr-review-claude/src
PY=/Users/alecfokapu/Github/atdd/main/.venv/bin/python

$PY lab/build_world.py            /tmp/ctr-claude-world
$PY lab/build_ambiguous.py        /tmp/ctr-claude-world2
$PY /tmp/ctr-claude-lab/build_world3.py /tmp/ctr-claude-world3   # breaks c4+r
$PY /tmp/ctr-claude-lab/build_world4.py /tmp/ctr-claude-world4   # breaks r

for w in world world2 world3 world4; do
  for c in none c1 c3 c4 r c4r; do $PY lab/candidates.py /tmp/ctr-claude-$w $c; done
  $PY /tmp/ctr-claude-lab/combo.py /tmp/ctr-claude-$w c3r
  $PY /tmp/ctr-claude-lab/run4n.py /tmp/ctr-claude-$w          # c4+r+n
  $PY /tmp/ctr-claude-lab/run5.py  /tmp/ctr-claude-$w c5rn     # counter-proposal
done

$PY lab/candidates.py . none; $PY /tmp/ctr-claude-lab/run5.py . c5rn   # blast radius
```

Nothing under `src/` was modified. New lab files live in `/tmp/ctr-claude-lab/`, outside the worktree.
