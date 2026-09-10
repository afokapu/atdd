# Spike — how much of its input does the sub-issue check read? (#1907)

**Question.** The `return` inside the loop is visible in the source. What does it
actually cost?

**Why spike at all when the bug is readable.** Because "stops after the first
parent" and "the verdict depends on which parent is first" are different defects
with different severities, and reading cannot tell them apart. The second is
worse, and it is the true one.

**Method.** Feed the shipped control flow permutations of the SAME data.
Harness: `labs/1907-order-dependent-gate/probe.py`.

## Measured

| input | verdict | parents examined |
|---|---|---|
| `{dirty, clean}` | **FAIL** | 1 of 2 |
| `{clean, dirty}` | **PASS** | 1 of 2 |
| `{clean, clean, dirty}` | **PASS** | 1 of 3 |
| `{dirty, dirty}` | FAIL, reports **1 of 2** | 1 of 2 |

Rows one and two are the same repository state in a different order.

On the live repository: **1 of 12 parents examined, 36 sub-issues unlabelled
behind it.**

## Findings

1. **The verdict was order-dependent.** Not "misses some" — *answers differently
   depending on dict order*. The same repository could go green and red across
   runs with no code change, and every green would be believed. That is strictly
   worse than a gate that always misses: a consistent blind spot can at least be
   reasoned about.

2. **Even when it failed, it under-reported.** `{dirty, dirty}` named one parent.
   An operator fixes it, re-runs, and meets the next one — which reads as a new
   regression rather than the remainder of the old one.

3. **Removing the `return` exposed a second defect underneath.** The trailing
   `pytest.skip("No issue with sub-issues found")` was the loop's fall-through.
   With the early return gone it fired on every CLEAN run, so a fully-labelled
   repository would report SKIPPED and could never report PASSED. The fix has to
   distinguish three outcomes, not two: FAIL, PASS, and the one genuine
   NOT_APPLICABLE (no parent has sub-issues at all), decided after the loop so it
   cannot mask drift.

4. **A comment asserted the thing that was false.** `# Found and validated — pass`
   sat directly above the `return`. Whoever wrote it believed the loop had
   validated something. This is the third artifact in this session whose comment
   described an intent the code did not implement — after
   `check_placeholders`'s "avoids regex false positives on user content" and
   E023-UNIT-003's acceptance.

## Disposition

Harness kept: the permutation probe is three lines of control flow and reproduces
the order-dependence in isolation, which the repo tests now assert against the
real function.
