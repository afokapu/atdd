# Spike — is the placeholder detector finding placeholders? (#1904)

**Question.** Four issues blocked every open PR with "unfilled placeholders".
Are they actually unfilled?

**Why measure rather than fix.** The obvious action was to edit four issue bodies
and move on. The bodies looked wrong because a validator said so, and a validator
saying so is not evidence — it is the thing under question. One `grep` answered it.

## Measured

None of the four was unfilled. All four were prose containing the substring:

    #1687  DEFINE = "define"      # find the JTBD main job
    #1775  | 9 | Which predecessor is the pilot? | TBD — chosen before RED, recorded here |
    #1782  honestly-broken values (`TBD` 34, `none` 14, `N/A` 7) *will* be repaired.
    #1776  | rows with no binding | 34  TBD |

Across 120 open atdd-issues: **4 hits, 0 genuine. A 100% false-positive rate.**

## Findings

1. **`JTBD` contains `TBD`.** A Jobs-To-Be-Done comment read as an unfilled
   section. That single line is the whole diagnosis: the match was textual, over
   a section, with no notion of what a placeholder IS.

2. **The worst case is #1775, and it is not merely harmless.** A Decisions table
   row recording a pending decision — "chosen before RED, recorded here" — is
   that table doing exactly its job. The check punished the correct behaviour,
   which teaches authors to stop recording pending decisions.

3. **The docstring described the intent, not the code.** It claimed: "Only
   placeholder strings that *literally* appear in the body are flagged. This
   avoids regex false positives on user content." A substring match over prose IS
   a false positive on user content. The comment was written by someone who had
   this exact risk in mind and then did not check it.

4. **Both directions have to be asserted.** A detector that stops
   false-positiving by detecting nothing is the same defect, quieter, and would
   look identical in CI. Fault injection: 5 tests fail on the restored substring
   match, 8 fail on a detector wired to never fire.

## Consequence for the fix

A placeholder is unfilled when it is the WHOLE CONTENT of a line — markdown
emphasis, backticks, list bullets and enclosing parens stripped first, since the
template ships several placeholders already wrapped and an author who leaves
`_TBD_` has still left it.

Split from #1903 deliberately. This fix alone unblocks the queue and needs no
policy decision; the pagination fix changes what the validator can SEE, and that
surfaces 80 pre-existing non-compliant issues which is a separate question.

## Disposition

No harness: the measurement was a substring scan over live bodies, and it now
lives as the parametrised cases in E078-UNIT-001, taken verbatim from the four
issues.
