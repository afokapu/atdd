# Spike — how much does a fail-open fixture hide? (#1896)

**Question.** `conftest.py` fixtures call `pytest.skip` when GitHub cannot be
queried. A skipped test is green. How many validators does that silence?

**Why a spike.** The one instance was read out of the code. The COUNT decides
whether this is a footnote or the largest instance of the defect this repository
keeps producing — and only a count can decide that.

**Method.** Walk `conftest.py` for fixtures that skip on an API failure, then walk
the validator suite for tests that consume them.
Harness: `labs/1896-fixtures-fail-open/blast_radius.py`.

## Measured

**6 fail-open fixtures. 16 test functions. 8 validator files.**

| fixture | test fns |
|---|---|
| `github_issues` | 5 |
| `protection_result` | 4 |
| `github_sub_issues` | 3 |
| `github_complete_issues` | 2 |
| `all_open_issues_unfiltered` | 1 |
| `github_closed_sub_issues` | 1 |

`protection_result` is the one that matters most: **"is `main` branch-protected?"
answered GREEN whenever the answer was unknown.**

## Findings

1. **#1892 is the proof, not a hypothesis.** `validate-coach` passed on one PR and
   failed on the next, same code, same 14 pre-existing unlabeled issues. The
   difference was API availability. The validator was never green — it was absent.

2. **An absent prefetch key is not an empty answer.** `all_open_issues_unfiltered`
   skipped on `data is None` with the message "No open issues in prefetch cache".
   `None` means the query never ran; `[]` would mean the repository really has
   none. The same conflation as #1895, one level down.

3. **THE ONE WORTH REMEMBERING — the defect ate its own regression test.**
   The first version of the guard used
   `pytest.raises(pytest.fail.Exception)`. Reintroducing the defect produced:

       11 passed, 4 skipped        <- GREEN. no failure at all.

   A `Skipped` exception is not caught by `pytest.raises(pytest.fail.Exception)`;
   it propagates, and pytest marks the GUARD skipped. A test asserting "this must
   not skip" was itself greened by the skip it existed to catch. Only fault
   injection found this — the guard passed perfectly against correct code.

   Catching `pytest.skip.Exception` first and converting it to a failure gives:

       4 failed, 11 passed         <- the guards actually fire.

## Consequence for the fix

`skip` → `fail` for the six "could not query" paths, with a message that says
COULD_NOT_CHECK, names the cause, and tells the operator how to deselect the
API-bound validators deliberately (`-m 'not github_api'`) so the suite reports
them unevaluated rather than green.

`skip` STAYS where the case is genuinely NOT_APPLICABLE: an unconfigured
repository, and a query that succeeded and found nothing. Turning those into
failures would just be a different false alarm.

## Disposition

Harness kept. This is the sixth instance of one shape in a single session, which
is why README.md now carries it as a checklist rather than an anecdote.
