# Spike — are "no such issue" and "GitHub refused" separable? (#1895)

**Question.** `_fetch_issue` returns `None` for both, so a rate limit prints as a
missing issue. Can the two be told apart from what `gh` actually emits — and how
many conditions are there?

**Why a spike.** The defect was read out of the code in a minute. What was NOT
knowable by reading: what `gh` emits per condition. The fix is a classifier over
strings the code has never seen, and a classifier built from guessed strings
matches nothing in production while passing every test written from the same
guesses.

**Method.** Capture the real output first, then replay it.

1. Two conditions hit for real against this repository: `gh issue view 99999999`
   (absent) and a genuinely rate-limited call, observed earlier in the same
   session.
2. A stub `gh` replaying those captured strings plus the remaining conditions,
   exiting non-zero for every failure exactly as the real one does.
   Harness: `labs/1895-gh-failure-classification/`.

## Measured

| condition | rc | output |
|---|---|---|
| exists | 0 | `{"number":1,...}` |
| **absent** | 1 | `GraphQL: Could not resolve to an issue or pull request with the number of 99999999.` |
| **rate limit** | 1 | `GraphQL: API rate limit already exceeded for user ID 8843832.` |
| secondary rate limit | 1 | `You have exceeded a secondary rate limit.` |
| no credential | 1 | `gh: ... set the GH_TOKEN environment variable.` |
| unreachable | 1 | `dial tcp: lookup api.github.com: no such host` |
| server error | 1 | `GraphQL: Something went wrong while executing your query. (502)` |
| malformed | **0** | not JSON |

Bold rows are verbatim from real failures, not composed.

## Findings

1. **The return code carries no information — every failure is 1.** All the
   signal is in stderr, which `_fetch_issue` discarded. That is the whole defect:
   not a missing check, a discarded one.

2. **Only ONE of eight conditions is an answer.** "No such issue" is a fact about
   the repository. The other seven are the absence of a fact, and printing them
   as absence sends the operator to look for something that is there.

3. **`malformed` exits 0.** It cannot be caught by any return-code test, and it
   is neither absent (nothing said so) nor retryable (the call succeeded).

4. **The obvious verification of a rate-limit diagnosis appears to refute it.**
   `gh api rate_limit` reported the GraphQL bucket FULL while GraphQL calls were
   being refused — REST and GraphQL are counted separately. A remedy that says
   "check the rate limit" without saying which bucket sends the reader to a number
   that contradicts the message. The shipped remedy says it.

## Consequence for the fix

Classify stderr; reserve the absence claim for the one condition that establishes
it. **An unrecognised failure must classify as UNAVAILABLE, never ABSENT** — a
message nobody has seen says nothing about whether the issue exists, and guessing
would reintroduce the conflation invisibly, which is the failure mode being
removed.

Control flow does not change: an unestablished verdict still refuses, exactly as
`coach.documentation.verdict` treats COULD_NOT_CHECK. Only the sentence changes.

## Disposition

Stub and probe kept. The strings in the stub are evidence — if `gh` changes its
wording the classifier goes stale silently, so they are recorded next to the
classifier that depends on them.
