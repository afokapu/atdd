# Judge Call Site Discipline

Per spec §6.9 fourth paragraph. This document gates the addition of new
judge call sites to the coach v9 routing surface.

## Criteria for Proposing a New Call Site

A new call site MAY be proposed only when ALL four criteria are met:

1. **Deterministic check is insufficient.** The routing decision cannot be
   expressed as a pure Python predicate over runtime context. If a
   deterministic check (severity threshold, retry count, violation set
   comparison) can resolve the ambiguity, the call site belongs in the
   mechanical floor, not the judge ceiling.

2. **Operator escalation is insufficient.** The ambiguity occurs at a
   frequency where escalating to the operator every time would dominate
   operator attention. If the situation is rare enough that operator
   escalation is affordable, prefer the human-in-the-loop path.

3. **Response schema is specified.** The call site has a frozen JSON Schema
   response contract at `src/atdd/coach/schemas/judge-<name>.response.schema.json`
   with a narrow decision enum and required fields. The schema is committed
   before the implementation PR is opened. No out-of-band control fields.

4. **Audit-trail expectation is specified.** The call site documents which
   audit log entries it produces (`judgments.jsonl`, `decisions.jsonl`) and
   what post-incident review joins are expected. The `call_site` enum value
   in `coach-judgment.schema.json` is updated in the same PR.

## Process

1. Open an issue that references this document and addresses all four
   criteria above.
2. Add the response schema and at least one valid example fixture.
3. Add the `call_site` enum value to `coach-judgment.schema.json` and the
   `CALL_SITES` tuple in `judge.py`.
4. Add the trigger predicate, invoke function, and route function to
   `judge_call_sites.py` following the discipline established by call
   sites #1, #3, #4, #5.
5. Wire coach routing per the response decision enum.

## Current Call Sites

| # | Name | `call_site` | Response Schema |
|---|------|-------------|-----------------|
| 1 | Borderline tier-1 | `borderline-tier1` | `judge-borderline-tier1.response.schema.json` |
| 2 | Reviewer concern verdict | *(track N)* | *(track N)* |
| 3 | Retry-vs-escalate | `retry-vs-escalate` | `judge-retry-vs-escalate.response.schema.json` |
| 4 | Cross-phase regression | `cross-phase-regression` | `judge-cross-phase-regression.response.schema.json` |
| 5 | Issue review aggregate | `issue-review-aggregate` | `judge-issue-review-aggregate.response.schema.json` |
| 6 | Superseded rule-ID consolidation | *(O4)* | *(O4)* |
