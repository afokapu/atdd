# Spike — can a pre-push hook fix the file it just resynced? (#1888)

**Question.** `.atdd/hooks/pre-push` detects registry-mirror drift, runs
`atdd registry update --yes`, `git add`s the result, and lets the push proceed.
The resynced mirror does not reach the remote. What *can* a hook do here?

**Why a spike.** The fix changes a hook that gates every push in the repo. The
obvious remedy read off the code — "make the hook commit it" — turns out to be
worse than the defect, and nothing in the source says so. This is git behaviour,
not ATDD behaviour, so it was not inferable from the codebase.

**Method.** Real git, real bare remote, real hooks. ATDD stubbed: `registry
update --check` is `echo drift; exit 1`, `--yes` is a line that rewrites a file.
The subject under test is git <-> hook <-> remote, nothing else.
Harness: `scratchpad/lab-prepush/{lab,verify_b,verify_d}.sh`.

## Measured

| Variant | hook body | push rc | mirror on remote | worktree after |
|---|---|---|---|---|
| A (shipped) | `git add` | 0 | **stale** | fix left staged |
| B | `git add` + `commit --amend` | 0 | **stale** | **clean** |
| C | `git add` + `exit 1` | 1 | unchanged | fix staged |
| D | heal at **pre-commit**; pre-push verifies | 0 | **correct** | clean |

## Findings

1. **A pre-push hook cannot influence what is pushed.** git resolves the refs
   before running the hook and passes them on stdin:

       HEAD 9765dad… refs/heads/main badf77a…
       sha at hook entry = 9765dad
       sha after amend   = d166357
       To ../origin.git
          badf77a..9765dad  HEAD -> main     <- pushed 9765dad, not d166357

2. **Amending in pre-push is worse than the bug.** Variant B exits 0, leaves a
   clean worktree, and pushes the pre-amend commit — local HEAD and remote have
   silently diverged. The defect it "fixes" at least leaves a modified file
   visible in `git status`.

3. **At pre-commit, `git add` does reach the commit.** Variant D: the mirror is
   inside the new commit, remote matches local, worktree clean.

4. `atdd registry update --check` costs 0.32s, so pre-commit can afford it.

## Consequence for the fix

E023's `context_clarifier` chose self-heal deliberately — "rather than blocking
and requiring a manual remediation loop." That intent is sound and is preserved
by moving the heal to pre-commit, where staging works. Pre-push stops pretending
to heal and becomes a truthful gate: drift still present at push time refuses,
and a resync that FAILS no longer reports success (the shipped code runs
`atdd registry update --yes ... || true` and prints "resynced" either way).

## Disposition

Lab is throwaway; findings live here. Nothing under `scratchpad/` is shipped.
