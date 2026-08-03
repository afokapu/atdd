# #1635 — prior-session handoff

**Honest summary: I know nothing about #1635 beyond its four commit messages.** Everything
below is either (a) what I was actually doing when interrupted, which was unrelated to #1635,
or (b) explicitly labelled as unverified inference from the commit subjects.

## What I was doing when interrupted

Nothing to do with #1635. The user asked me to report the content and goal of **issue #1636**
("Delete the agent-specific pre-tool-use hook and hold the bootstrap at commit time instead").
I got as far as:

- `atdd coach issues 1636` → Status `INIT`, State `OPEN`, branch `feat/commit-layer-enforcement`,
  **WMBTs: none found**, next step `atdd coach transition 1636 PLANNED`. No body/scope text is
  surfaced by that command.
- I was hunting for the State Store backing file to read #1636's body directly when the session
  was cut. I had **not** found it.

No files were modified, no commands with side effects were run. Nothing is half-done on the
#1635 branch because of me.

## Environment facts worth not rediscovering

These cost several tool calls to learn and are not in any commit message:

1. **The CLI is version-skewed.** Every `atdd` invocation prints
   `⚠️  ATDD upgraded (3.106.0 → 4.33.0). Run: atdd sync && atdd init`. Unclear whether the
   installed 4.33.0 CLI matches this worktree's tree. Consider running `atdd gate` (the
   CLAUDE.md bootstrap step) before trusting any `atdd` output.
2. **`atdd state doctor` currently reports `Status: INVALID`.** Not a #1635 defect — it is a
   layout problem: ~10 sibling worktrees under `/Users/alecfokapu/Github/atdd/` each carry their
   own `.atdd/extensions` and `.atdd/workspaces`, and sibling-worktree mode allows only one, at
   the Control Root. It tells you to run `atdd state migrate-layout`. **Do not run that
   casually** — it consolidates to a single project-root store and rebuilds from main's
   manifest, which would touch every sibling worktree.
3. `atdd state` subcommands of likely use for reading issue bodies: `object`, `project`,
   `hydrate`, `overlay`, `trace`. `atdd coach issues <N>` alone does not print issue scope.
4. `.atdd/runtime/` in this worktree contains only `issue-1635/approvals/PLANNED-RED.json` —
   i.e. the PLANNED→RED approval for #1635 is recorded. Nothing for later phases.
5. Uncommitted at session start (pre-existing, not mine): modified
   `.atdd/baselines/validation/{coach,planner,tester}.yaml`.

## What is implemented on this branch

I did not read a single line of the #1635 diff, so I cannot tell you what
`38bd9f33 feat(green): populate, validate and read the issue↔feature binding` actually does
beyond its subject line. Do not treat any of the following as verified — it is only the commit
order, which suggests a standard ATDD cycle:

- `15d37bcc` plan — decomposition authored, "fourth break" added
- `71fd04e4` red — 12 issue↔feature binding acceptances anchored as failing tests
- `38bd9f33` green — populate / validate / read the binding
- `c889937a` fix(substrate) — new WMBTs + the binding rule registered in the graphs

A fresh agent should start by reading those four diffs; I have no knowledge that would let it
skip that.

## Half-done work

None that I created. The only open thread is the original question — **what is the content and
goal of #1636** — which remains unanswered.
