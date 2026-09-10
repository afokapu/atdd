# Spike — why is each permanently-red test red? (#1893)

**Question.** E023 requires `ATDD_SKIP_ALL_GATES` in the pre-push hook and E026
requires it absent. Is that one contradiction, or an instance of something?

**Why a spike.** The contradiction itself needed no measuring — it is two plan
files, read. What was unknown is the SIZE of the class, and that decides the fix:
retiring one acceptance, or building a detector.

**Method.** Three passes over a clean `origin/main`, each because the previous
one's answer was wrong in a way the next could check.
Harnesses: `labs/1893-permanently-red-acceptances/`.

## Measured

**17 test files are permanently red on a clean main, and all 17 are bound to a
declared acceptance.** Every one has a plan artifact asserting it must pass.
Nothing anywhere reports that they do not.

Why each is red:

| cause | n |
|---|---|
| environment-coupled SMOKE (live store, real CLI, network) | 9 |
| other | 6 |
| abandoned RED-phase stub | 2 |

The E023/E026 pair accounts for **2**, not 3. `test_e026_smoke_001` looked like a
third and is not: it fails because the version gate falls back to PyPI, so its
verdict tracked how recently the operator had upgraded.

## Findings

1. **Only ONE of the two E023 acceptances actually contradicted E026.**
   `E023-UNIT-001` requires the flag in its `then` clauses — a real conflict.
   `E023-SMOKE-001`'s acceptance says "No gate-bypass env-var was needed", which
   is E026's goal exactly; only its TEST asserted the retired mechanism. The test
   still carried `# Phase: RED` and "this test drives the implementation" long
   after E023 completed. Two different defects behind one symptom.

2. **E026 settles which side wins, in its own words.** `ATDD_SKIP_ALL_GATES` was
   "structurally additive: individual flags still work independently, the
   meta-bypass just lowered the typing cost of bypassing everything." E026's
   object of control is `bypass-escape-hatches-without-mandatory-audit-record`.
   E023's GOAL — a routine push needing no bypass cocktail — survives and is
   better served; only the mechanism it named was superseded.

3. **The E026 SMOKE test set two bypass env vars to make itself pass.** In a test
   whose acceptance is "a routine push needs no bypass env var". They had been
   retired by E030, so they did nothing except leave the version gate to consult
   PyPI — making a SMOKE verdict depend on the network. Declaring
   `release.minimum_version` exercises the deterministic path E023-UNIT-002
   actually shipped.

4. **A stale `# Phase:` header is NOT a usable signal on its own.** 307 test files
   in `src/` declare a phase their acceptance does not (259 of them `RED` where
   the acceptance says `GREEN`) — and nearly all of those tests PASS. The
   abandoned-stub signature is the INTERSECTION: stale header AND permanently
   red. That is 2 files, not 307.
   Recorded because the first cut of this measurement counted `build/lib/` too
   and reported 520; a packaging artifact tree is not source.

## Consequence for the fix

Amend `E023-UNIT-001` to assert the mechanism that shipped rather than the one it
proposed, keeping its goal. Rewrite both tests against their own acceptances.
Give the E026 SMOKE a declared version floor instead of two dead bypasses.

Deliberately NOT done here: the other 14 permanent reds, and the 307 stale phase
headers. Both are real and both are larger than this issue. The 14 in particular
want the ratchet treatment this repo already uses for lint — a register that
holds the count flat and fails when it grows — because a blocking gate on day one
would red every PR.

## Disposition

Harnesses kept. The failure lists they consume are regenerated, not stored.
