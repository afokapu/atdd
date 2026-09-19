# Adversarial review: reject c4+r as proposed

The reported double-prefix defect is real, but the proposed E1/c4+r remedy is
not safe.  There is an existing written rule for the opposite convention, and
c4+r demonstrably corrupts a valid `contract`-themed three-segment identity.
Do not ship stage 1 as described.

## 1. Citation audit

The following is what the frozen worktree actually says.

| Brief fact | Verdict | Review |
|---|---|---|
| 1 | Mis-cited, substance true | The assignment is at [author.py:1097](src/atdd/planner/commands/author.py:1097), not line 1095 (which only opens `doc`). |
| 2 | True | The registry entry takes bare `identity` at [author.py:1055-1059](src/atdd/planner/commands/author.py:1055). The immediately preceding docstring explicitly says it is bare at [author.py:1046-1050](src/atdd/planner/commands/author.py:1046). |
| 3 | Mis-cited, substance true | `$id` is asserted at [test_e008_unit_001_derives_path_id_and_registers.py:38](src/atdd/planner/commands/tests/test_e008_unit_001_derives_path_id_and_registers.py:38), and the no-prefix assertion at [line 54](src/atdd/planner/commands/tests/test_e008_unit_001_derives_path_id_and_registers.py:54), not 37 and 50. |
| 4 | True | The declaration scanner unconditionally forms `contract:{contract_id}` at [resolver.py:842-852](src/atdd/coach/utils/graph/resolver.py:842). |
| 5 | True | The file-reference reader does the same at [graph_builder.py:907-911](src/atdd/coach/utils/graph/graph_builder.py:907). |
| 6 | Misleading | [graph_builder.py:1533-1551](src/atdd/coach/utils/graph/graph_builder.py:1533) prefixes a **`urn:jel:`** schema header when synthesizing a JEL node. It is not a second path for ordinary `contract:` `$id`s and cannot support the claimed double-prefix diagnosis. |
| 7 | True | A manifest `contract:` reference is returned unchanged at [graph_builder.py:882-891](src/atdd/coach/utils/graph/graph_builder.py:882). |
| 8 | True | `_has_producer` is only an incoming-edge query at [edge_validator.py:450-453](src/atdd/coach/utils/graph/edge_validator.py:450). |
| 9 | True | `replace`, rather than leading-prefix removal, is used at [resolver.py:748-765](src/atdd/coach/utils/graph/resolver.py:748). |
| 10 | True | The grammar accepts `contract:contract:...`: `contract` satisfies the first ordinary segment in [urn_grammar.yaml:91-95](src/atdd/coach/utils/graph/urn_grammar.yaml:91). |
| 11 | True | The planner resolver strips exactly one optional leading prefix at [contract_resolution.py:34-41](src/atdd/planner/interlocking/contract_resolution.py:34). |

The assertion that there is “no rule” is false.  An active planner convention
says a schema `$id` is the clean artifact name and explicitly reserves
`contract:{artifact_name}` for wagon references
([planner.artifact-naming.schema-identifier.convention.yaml:4-16](src/atdd/planner/conventions/nodes/planner.artifact-naming.schema-identifier.convention.yaml:4)).
The platform validation documents `contract:match:result` as wrong
([test_contract_schema_compliance.py:365-395](src/atdd/tester/validators/test_contract_schema_compliance.py:365)).
This conflicts directly with the newer writer and its acceptance test; it is
not an absence of policy.

I also verified the inventory: the 21 committed schema `$id`s are bare.  That
is consistent with the active convention and with the graph reader's original
`contract:{schema_id}` construction.

## 2. Independent lab results

I used the supplied venv with `PYTHONPATH` set to this checkout's `src`, built
both disposable worlds anew, and ran every supplied candidate.

| world | none | c1 | c3 | c4 | r | c4r |
|---|---|---|---|---|---|---|
| world1 | 1 warning; two nodes | 0 | 0 | 0 | 1 warning; two nodes | 0 |
| world2 | 1 error | 1 error and two nodes | 1 error | 1 error | 0 | 0 |

These match the brief's table.  World1 baseline specifically produced
`['contract:contract:match:result', 'contract:match:result']`, one `produces`
edge to the latter, and the warning on the former.  The raw resolver found the
same schema for *both* node spellings because `replace` reduces both to
`match:result` **and** the resolver's path fallback then finds
`contracts/match/result.schema.json`; it is not an exact `$id` match.

Two reproducibility defects in the brief/lab matter:

* The first prescribed measurement command uses `/tmp/ctr-$r-world`, but `r`
  is unset by the instructions.  It does not name either constructed world.
* `lab/measure.py` hard-codes `contracts/match/result.schema.json` and the
  `score_match` manifest ([measure.py:15-23](lab/measure.py:15)). It succeeds
  for world1 (rc 0) but crashes on world2 with `FileNotFoundError` (rc 1).
  Thus it cannot be used as instructed to obtain world2 raw facts.  Further,
  `candidates.py` deliberately exits 0 for any non-negative issue count
  ([candidates.py:176](lab/candidates.py:176)); command status is not a pass
  signal.

The author acceptance itself passed: `2 passed` (rc 0).  That only confirms
the conflicting new convention, not that it is the correct system contract.

## 3. c4+r failure: constructed counterexample

The brief names c4's ambiguity, but its world2 has only the two-segment bare
identity `contract:result`.  That string fails the contract URN grammar, so it
does not exercise c4's ambiguous branch.

I constructed the missing valid case in a disposable world:

```
contracts/contract/match/result.schema.json
  $id: contract:match:result             # bare identity; theme = contract
contracts/_contracts.yaml
  identity: contract:match:result
plan/settle_contract/_settle_contract.yaml
  produce[].contract: contract:contract:match:result
```

This is valid under the configurable-theme mechanism
([theme_map.py:82-120](src/atdd/coach/utils/theme_map.py:82)) and the
theme-first identity grammar ([artifact_naming.py:66-107](src/atdd/planner/artifact_naming.py:66)).
The manifest is also the required URN spelling: family prefix plus the bare
identity.

With **c4+r**, the actual result was:

```
contract nodes : ['contract:contract:match:result', 'contract:match:result']
produces edges : [('wagon:settle-contract', 'contract:contract:match:result')]
issues         : 1
  - [error] contract:match:result :: Contract URN broken:
    Contract schema not found for: contract:match:result
```

c4 calls the bare `$id` an already-prefixed URN because it syntactically
matches the permissive grammar; it therefore emits `contract:match:result`.
The wagon correctly emits `contract:contract:match:result`.  `r` cannot repair
the resulting split identity.  This is a wrong answer, not a tolerable
warning, and falsifies “c4+r is the only combination clean in both worlds.”

## 4. Answers to the five questions

1. **Diagnosis:** Two spellings exist, and the graph bug is real.  But “no
   rule” is wrong: the active schema-identifier convention and platform test
   say `$id` is bare.  The writer/its green test are the contradictory recent
   rule, not proof that the contract became undefined.

2. **End state:** Choose **E2**, bare `$id`, not E1.  It preserves all 21
   existing schemas and the active convention, keeps the natural mapping
   `URN = contract: + identity`, and needs only a writer/test correction plus
   the strip-once resolver correction.  E1 requires rewriting every existing
   schema, changes the documented public format, and still cannot represent
   the `contract` theme during transition.  A green test is implementation
   evidence that must be changed when it contradicts the active contract; it
   is not an argument to change the contract.  Previously emitted prefixed
   external artifacts need an explicit migration or registry/path-based
   compatibility adapter; inference from `$id` alone is information-theoretically
   ambiguous.

3. **c4+r failure mode:** Yes—the three-segment `contract`-theme example
   above fails.  It is worse than the brief's stated weakness because stage 1
   claims backward compatibility while returning a split graph and an error.
   `URNGrammar.validate_urn` is a syntax check, not provenance capable of
   telling a family prefix from a valid theme token.

4. **Staging:** Do not ship c4 as an interim reader.  Land the E2 writer
   correction, its changed acceptance, and the strip-once resolver fix
   together.  Existing committed bare artifacts need no rewrite.  For already
   emitted prefixed artifacts, either migrate them in the same release or use
   the registry's authoritative `path -> identity` mapping and reject an
   unregistered ambiguous file.  The registry is explicitly the source of
   truth ([planner.contract.registry-coherence.convention.yaml:14-20](src/atdd/planner/conventions/nodes/planner.contract.registry-coherence.convention.yaml:14)); it can disambiguate where raw `$id` cannot.  A noncanonical path is not a reason to use c4: the registry stores a path, while the planner's scan deliberately supports noncanonical files
   ([contract_resolution.py:101-115](src/atdd/planner/interlocking/contract_resolution.py:101)).

5. **What the brief gets wrong:** it misses the written bare-ID rule; has
   inaccurate line citations for facts 1 and 3; overstates the relevance of
   the JEL code in fact 6; calls a two-segment test a discriminator for a
   three-segment ambiguity; and supplies a broken world2 raw-measurement path
   plus an unset `$r` command.  Its empirical results are reproducible, but
   they do not establish the proposed end state or its safety.
