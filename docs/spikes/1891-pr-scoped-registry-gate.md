# Spike — is the PR-scoped registry gate wired, and does it work? (#1891)

**Question.** `atdd-registry-main-guard.yml` names a per-PR scoped check as the
protection against registry mirror drift. Does anything run it, and if it runs,
does it catch drift?

**Why a spike.** Both halves are claims about a running system, not about source.
"Is it wired" is answerable by reading workflows — but "does it catch drift" is
not answerable by reading `_drifted_wagon_slug`, because the question is what it
sees relative to what the FULL check sees, and only running both on the same
commit produces that comparison. Reading the function would have told me it
compares `description`. It would not have told me that this is 1 of 14 fields,
because nothing in that function names the other 13.

Harnesses: `labs/1891-pr-scoped-registry-gate/` — `probe_scoped_gate.sh` runs the
scoped gate on a branch carrying injected drift; `probe_full_check.sh` runs the
full check on the same commit.

## Measured

**Nothing invoked it.** `grep -rn "scope changed-files" .github/workflows/` over a
clean `origin/main`: zero hits. The gate had existed since E018 with three
passing unit tests and no caller. The workflow comment describing it as the
per-PR protection was the only thing that connected it to anything.

**The guard that DOES run cannot block.** `atdd-registry-main-guard.yml` is
`on: push` to main with `continue-on-error: true`, and says so in its own words:
"alert only, does not revert the merge". So drift had no blocking check before
the merge and no reverting check after it.

**Invoked, it reported a drifted branch as clean.** Same commit, both probes:

| probe | verdict |
|---|---|
| full check (`atdd registry update --check`) | `Drift detected in wagon registry` |
| scoped gate (`--scope changed-files`) | `1 wagon source(s) checked, all in sync` |

The injected drift added a WMBT to a wagon manifest — the single most common
real drift in this repository, and the one every issue in this batch produced.

**Why.** `_drifted_wagon_slug` compared `manifest["description"]` against
`entry["description"]` and nothing else. A wagon entry carries fourteen fields.
The gate could detect exactly two things: a wagon absent from the aggregate, and
a reworded description.

## What the lab changed about the fix

Two things, neither visible from the source.

**The fix is not a longer field list.** The scoped check and the full check are
two implementations of one comparison, so any list I wrote would be the drift
between them written down — the same defect as #1901's `OPTIONAL_SECTIONS`, one
layer down. The scoped check now rebuilds the entry with `_build_wagon_entry`,
the function the full check regenerates from. It cannot compare a subset because
it no longer decides what the set is.

**Wiring it needed `fetch-depth: 0`, and I would not have known.** With the job
written the obvious way, the lab's drifted branch passed. `_get_pr_changed_files`
resolves the diff through `git merge-base HEAD origin/main`; a shallow checkout
has no merge-base, the resolver returns `[]` on any git error, and an empty scope
is a trivial pass. A wired gate over a shallow clone is indistinguishable from no
gate — it prints a green check on every PR. That is asserted in E079-SMOKE-001 so
that removing the line fails a test rather than silently disarming the gate.

## The shape, again

A check that cannot establish its answer reporting the clean one — twice over in
one gate. It could not see thirteen fields, and said "all in sync". It could not
see the diff at all under a shallow clone, and said "trivial pass". Neither
surface said "I did not look".

Count for this session: eleven, then this.
