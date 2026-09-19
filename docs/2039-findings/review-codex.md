codex
1. “Measurable outcome” is directionally right, but slightly stronger than the contract proves. The schema requires a direction and dimension, not a threshold, unit, metric binding, or observable. I would use **“directional outcome statement”** (or simply “outcome statement”). It preserves the JTBD meaning without implying every WMBT is quantitatively measurable.

Your proposed sentence also overstates two details:

- “qualified by a `context_clarifier`” makes it mandatory, but it is optional in both the schema and validator.
- “its `acceptances` … of which at least one must be a SMOKE” is enforced operationally with an explicit suppression path; it is not a universal schema property.

2. No. The nesting argument is not sound on its own. A requirement can be an acceptance criterion and still carry acceptance tests as evidence. JSON Schema nesting tells us containment, not the semantic category of the parent. The stronger argument is terminology and role separation: WMBT is the **outcome/condition to achieve**; embedded acceptances are **verification evidence**. That supports changing “criterion” where it ambiguously equates WMBT with an acceptance test, but not a blanket claim that a WMBT cannot be an acceptance criterion in any meaningful sense.

3. Do not drop both claims merely because they are not top-level schema fields. Definitions may legitimately state semantics enforced elsewhere.

“Closes a feedback loop” should stay, qualified: **“where the feature is a feedback-loop feature, it closes that loop through its SMOKE evidence.”** There is an active validator for that conditional behavior.

“Stays within its size limits” should also stay, but make it precise: **“is sized using declared WMBT coverage and architectural footprint, subject to the feature hard-limit and size-max rules.”** `sizing` alone does not express the limits, but the active rules do. Removing these makes the anchor less truthful, not more.

There is also a material premise error: `feature.schema.json` does **not** set top-level `additionalProperties: false`. Thus `status` and `acceptance` are not schema-rejected; they are absent from the documented property set and corpus, but the schema does not prohibit them. Your proposed feature replacement is still better, but the rationale should not say the schema makes those fields invalid.

4. A “no named field absent from schema” test is necessary but insufficient. Alone, it is theatre against the drift that matters:

- it will not catch the wrong acronym;
- it will not catch required-versus-optional drift (`context_clarifier`, `acceptances`);
- it will not catch invalid cardinality, enum, or reference claims;
- it will not catch claims about semantics enforced by validators rather than schemas;
- arbitrary prose can evade a token-based checker.

You do not need to bind these family nodes to make the protection real. Keep them advisory, but add a real parity validator with machine-readable claims, e.g. per definition: `schema_ref`, field paths, required/optional status, cardinality, enum assertions, and `validator_refs` for semantic claims. Test those claims against schemas and the named validators; keep prose as the human projection. That preserves the approval boundary while giving the definitions a checked maintenance contract.

Two smaller review notes:

- The interlocking rewrite is materially better, but “each route selected by a declarative `guard` expression” should say each route **references** a declared guard expression (`guard_ref`); the expression lives under `fragments[].guards[]`.
- “four coach sites” is imprecise: you list five locations across three files—three in `issue.convention.yaml`, plus `label_taxonomy.schema.json` and `rule_binding.py`.
hook: Stop
hook: Stop Completed
