# Legacy-vs-Convention Catch Matrix (#1212)

Differential measurement: each fault run through BOTH suites on identical input.

Each legacy target is also run on the CLEAN tree; a target already red on clean
is marked **inconclusive** (its red is pre-existing and cannot be credited to the
injected fault), and is excluded from the parity count.

## Tally

- cases: **7**
- parity (both): **7**
- convention-only (improvement or FP — adjudicate #1211): **0**
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

> Corpus is seeded for cases with a legacy counterpart + injectable fault.
> #1212 E027 expands to one fault per legacy rule. Decommission stays BLOCKED
> until parity (both) is shown for every P0 pair with zero clean-repo FPs.

