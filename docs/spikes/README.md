# Spikes

A spike is a **timeboxed experiment whose deliverable is a measurement**. The code
written to get it is thrown away; the number, the count, or the transcript is kept
here.

This is not a test directory. Tests assert that shipped behaviour is correct. A
spike answers a question you must settle *before* you know what correct is.

## Why this exists

An agent cannot reliably tell its own inferences from its own knowledge. Fluency
and correctness are uncorrelated: the reasoning that produces a wrong answer feels
identical to the reasoning that produces a right one. Every spike in this
directory was run against a belief that felt solid, and the record so far is that
roughly half of them were wrong.

So the trigger for a spike is not "I feel unsure." It is **provenance**:

| provenance | means | spike? |
|---|---|---|
| Derived | read out of this repo, with a file:line citation | no |
| Reported | another team, a doc, an issue comment, a code comment said so | **yes** |
| Inferred | reasoned to it from the shape of the code | **yes** |

You may not build on a Reported or Inferred claim you have not executed. That
fires without requiring you to first notice you are guessing, which is the whole
point — a confidence-triggered rule never fires.

## The strongest signal in the record so far

`plan/govern_lifecycle/E023.yaml` (before #1888) required, verbatim:

> - The hook re-stages the mirror files
> - The hook exits 0 (push is not blocked)

Those two lines describe a mechanism that **cannot work**: git resolves the refs
it will push before running `pre-push`, so nothing the hook stages can reach the
remote. The acceptance specified the defect. Every gate below it — RED, GREEN,
SMOKE, the enforce ratchet — then enforced that faithfully for months.

An untested premise, once written into a plan artifact, stops being a guess and
becomes the requirement. `phase_machine.convention.yaml` already concedes that
"the decomposition is the one artifact no downstream gate can re-derive." That is
why the spike belongs at INIT: it is the last point where a wrong premise is still
cheap.

## Shape: pick by what is uncertain, not by habit

Three shapes have earned their place. They are not interchangeable, and choosing
the wrong one wastes the spike.

**Probe** — no lab at all. Run the real tool against real state and count.
Use when the question is factual about something you already have.
*Example:* core's digest covers 84 files, the hub's covers 19. `find | wc -l`,
twice. Building a lab here would have been procrastination.

**Lab** — a disposable world where the real code path executes, with everything
else stubbed. Mirror only where the uncertainty lives.
*Example (#1888):* real git, real bare remote, real hook; `atdd registry update`
stubbed to three lines. The subject was git↔hook↔remote, so stubbing git would
have answered a different question.

**Blast radius** — apply the candidate rule to the repository's real data and
count what it invalidates. No synthetic world at all.
*Example (#1890):* three candidate validation rules scored against every
`--train` value the repo's own source passes. The measurement changed the fix.

## What the labs have actually cost and returned

| # | question | shape | result |
|---|---|---|---|
| 1888 | can a pre-push hook fix the file it resynced? | Lab | **No.** Both fixes readable from the code measured WRONG. `--amend` is worse than the bug: exit 0, pre-amend commit pushed, local diverged from remote, clean `git status`. |
| 1890 | what would write-time train validation reject? | Blast radius | Every `--train` literal in the repo's own source is unregistered. Rejecting legacy *format* would orphan 7 registered trains; the migration is incomplete. |

Reading the code alone, on #1888, went 0-for-2. Ten minutes of real git went
2-for-2.

## Rules learned the hard way

1. **A negative result about lab shape is still a result.** The first #1890 lab
   tried a throwaway project plus the real CLI. It could not run: `atdd update`
   resolves a live GitHub issue and a Control Root. When the tool is coupled to
   external state, lab the *function* and measure the *data* — do not fake the
   world.
2. **Assert on the far side, not the near side.** #1888's smoke test asserts on
   the REMOTE's file content. Every claim the broken hook made was true of the
   worktree and false of the remote; a worktree assertion would have passed.
3. **Fault-inject every guard.** Re-introduce the exact defect and watch the test
   go red. A guard never seen red is a guard you are guessing about.
4. **Never trust a filtered result.** `grep`/`head`/`tail` in a pipeline replaces
   the command's exit code with the filter's, and truncates the evidence. Capture
   `rc=$?` from the command itself; write full output to a file and count it.
   This has produced three wrong statements in one session.
5. **Diff by name, never by count.** Two failure sets of equal size are not the
   same failure set.
6. **Derive the verification surface, don't recall it.**
   `grep -rhoE "pytest [^|&\"']*" .github/workflows/*.yml` — the CI surface is a
   fact to be extracted, not remembered. "The five validate scopes" was itself an
   unverified claim, and it was wrong.
7. **A gate that cannot run is not a gate that passed.** The ruff ratchet was
   never invoked locally because ruff was not installed; its silence read as
   approval.

Rule 4, 6 and 7 are the same defect this codebase manufactures over and over:
**a check that cannot establish its answer reports the clean answer.** It is worth
naming because a spike is structurally immune to it — a measurement cannot return
"probably fine".

## Layout

    docs/spikes/README.md              this file — the accumulated pattern
    docs/spikes/<issue>-<slug>.md      one finding per spike: question, method, measurement
    docs/spikes/labs/<issue>-<slug>/   the harness, kept so the measurement is reproducible

The harness is kept; the world it builds is not. Nothing under `labs/` is imported
by shipped code, and nothing there runs in CI.
