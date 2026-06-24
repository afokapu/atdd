# Legacy-vs-Convention Catch Matrix (#1212)

Differential measurement: each fault run through BOTH suites on identical input.

## Tally

- cases: **2**
- parity (both): **2**
- convention-only (improvement or FP — adjudicate #1211): **0**
- legacy-only (coverage gap): **0**
- neither (shared blind spot): **0**
- clean-repo false positives (convention flags on clean): **0**

## Cells

| case | family/template | clean-FP | legacy catches | convention catches | cell |
|---|---|---|---|---|---|
| theme-noncanonical | grammar/theme_must_be_canonical | 0 | yes | yes | **both** |
| duplicate-rule-id | uniqueness/scoped_identifier_uniqueness | 0 | yes | yes | **both** |

> Corpus is seeded for cases with a legacy counterpart + injectable fault.
> #1212 E027 expands to one fault per legacy rule. Decommission stays BLOCKED
> until parity (both) is shown for every P0 pair with zero clean-repo FPs.
