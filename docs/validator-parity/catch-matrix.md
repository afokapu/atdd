# Legacy-vs-Convention Catch Matrix (#1212)

Differential measurement: each fault run through BOTH suites on identical input.

Each legacy target is also run on the CLEAN tree; a target already red on clean
is marked **inconclusive** (its red is pre-existing and cannot be credited to the
injected fault), and is excluded from the parity count.

## Tally

- cases: **14**
- parity (both): **12**
- convention-only (improvement or FP — adjudicate #1211): **2**
- legacy-only (coverage gap): **0**
- neither (shared blind spot): **0**
- inconclusive (legacy red on clean): **0**
- clean-repo false positives (convention flags on clean): **0**

## Cells

| case | family/template | clean-FP | legacy green on clean | legacy catches fault | convention catches | cell |
|---|---|---|---|---|---|---|
| theme-noncanonical | grammar/theme_must_be_canonical | 0 | yes | yes | yes | **both** |
| duplicate-rule-id | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | yes | **both** |
| wmbt-urn-bad-step | grammar/identifier_grammar_conformance | 0 | yes | yes | yes | **both** |
| wagon-schema-extra-prop | schema/node_schema_conformance | 0 | yes | yes | yes | **both** |
| train-dangling-wagon-ref | resolution/direct_reference_resolution | 0 | yes | yes | yes | **both** |
| feature-ref-dangling | resolution/reference_chain_resolution | 0 | yes | yes | yes | **both** |
| rule-validator-missing-impl | binding/declaration_to_implementation_binding | 0 | yes | yes | yes | **both** |
| malformed-convention-source | composition/composed_graph_loads | 0 | yes | no | yes | **convention-only** |
| rule-validator-roundtrip-broken | binding/rule_validator_roundtrip | 0 | yes | yes | yes | **both** |
| dup-wagon-slug | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | yes | **both** |
| dup-produce-artifact | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | yes | **both** |
| dup-contract-urn | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | yes | **both** |
| dup-feature-urn | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | yes | **both** |
| dup-train-id | uniqueness/scoped_identifier_uniqueness | 0 | yes | no | yes | **convention-only** |

> NOTE (#1207): the `feature-doc-reference-dangling` convention-only case was removed
> when its negative-control legacy oracle (test_plan_urn_resolution.py) was retired.
> The feature.references doc-resolution coverage is still ENFORCED by the
> resolution/plan_urn_resolution variant; only its parity *measurement* (which needs a
> live legacy probe) was dropped — case count 15→14, convention-only 3→2.

> Corpus covers all 10 P0 sentinels. `both` = parity with the legacy
> counterpart. `convention-only` here = NEW coverage (legacy has no counterpart
> validator); each is adjudicated as improvement vs FP in
> stricter-findings-adjudication.md — both current convention-only cells are
> verified new-coverage, not FPs.
> #1212 E027 expands further toward one fault per legacy rule. Decommission stays
> BLOCKED until parity (both) is shown for every P0 pair a legacy validator owns,
> with zero clean-repo FPs.

