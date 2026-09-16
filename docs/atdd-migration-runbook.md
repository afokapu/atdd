# ATDD migration runbook — manifest and GitHub hot path → committed projection

The cutover from the legacy `.atdd/manifest.yaml` (and the GitHub hot-path read) to the committed,
deterministic projection. Seven steps, in order. Follow them top to bottom; every one names the
command it runs, the precondition that must hold before you run it, and the numbered invariant from
[the architecture spec](atdd-state-projection-plan.md) §2.2 that it preserves.

This document is **checked**, not merely written: `atdd state runbook-check` fails if the code ships
a migration step this file does not document, if a section omits its command, precondition or
invariant, or if a section cites an invariant the spec does not declare. A runbook nobody verifies
is a runbook that describes last quarter's migration.

Two of these steps are **one-way doors** (`hot-path`, `decommission-manifest`). Their rollback
triggers and restore procedures live in [`.atdd/policy/migration-rollout.yaml`](../.atdd/policy/migration-rollout.yaml),
checked by `atdd state rollout-check`. Read them *before* you open the door, not after.

---

## migrate-store — mint identity for every work item

The projection keys work items by **uid**, which is minted once and never reused, and requires an
`owner_actor` the legacy corpus never recorded. This step mints both, in the store, for every work
item that lacks them.

It replaces the manifest-era pair (`mint-uids`, then `migrate-manifest`). Those read
`.atdd/manifest.yaml`, which `decommission-manifest` deletes; once it was gone they could not run at
all, and they were removed in #2023.

- **Command**: `atdd state migrate-store --root .`
- **Precondition**: a clean working tree. This step *writes the store*, and you want that write
  reviewable on its own.
- **Invariant**: **I1** — `project(store)` is byte-identical for the same logical store. Identity is
  minted in its own recorded step precisely so it is *not* re-rolled on the next run: mint inside the
  migration and the second run emits a second file for the same work item, and the tool that promises
  byte-identical re-runs becomes the tool that doubles the corpus.

Idempotent: a work item that already carries a well-formed uid and owner is left exactly as it is.
Refuses the whole run before any write if an object cannot be migrated.

---

## shadow — watch the drift go to zero

The non-blocking CI job that recomputes `project(store)` on every push and reports its drift against
**both** the committed projection and the manifest-derived one.

- **Command**: `atdd state shadow --root .` (locally); in CI,
  `.github/workflows/atdd-projection-shadow.yml` runs it on every push.
- **Precondition**: the projection exists (`migrate-store` has run and the projection been committed).
- **Invariant**: **I2** — the projection is derived and gated. Shadow mode is the *measurement* that
  earns the right to gate: it reports and **exits 0, always**. That is not a bug. A shadow check
  that could fail a build is a blocking check with a misleading name, and it would demand the trust
  that this window exists to earn.

**Hold here.** This is the step that buys the evidence every later step spends. Move on when drift
has been zero long enough that the team believes it — that judgement is the point of the window, and
it is the one thing in this runbook you cannot automate.

---

## hot-path — stop every gate from reading GitHub

Removes the GitHub API read from every core lifecycle decision, validator, and gate. The phase
becomes the store's, and the store's alone.

- **Command**: `atdd state hot-path --root .` (proves it; exits non-zero while any decision module
  still reaches the GitHub API, `gh`, or a provider implementation).
- **Precondition**: `shadow` has reported zero drift. You are about to stop believing the labels;
  be sure the projection already agrees with them.
- **Invariant**: **I7** — the GitHub mirror is non-authoritative. A gate that lets a live label
  overrule the committed projection is a gate GitHub can be wrong about, an outage can block, and a
  rate limit can make non-deterministic.

⚠️ **One-way door.** Once gates stop reading labels, the labels drift; putting the read back later
would resolve phases from data that has been wrong for a week. Rollback trigger and restore
procedure: `.atdd/policy/migration-rollout.yaml`, step `remove-github-hot-path`.

Provider access is not banned — it is *confined*. An extension may still mirror outward through the
`SyncProvider` seam, and an authoring command may still ask the provider what issue #N is called.
What may not happen is a **decision** consulting GitHub.

---

## decommission-manifest — remove the readers, then the file

Removes every core reader of `.atdd/manifest.yaml` — **removed, not deprecated in place**, because a
deprecated reader still reads — and then deletes the file.

- **Command**: `atdd state manifest-fallback --root .` (proves no core reader opens, globs, or
  parses it), then `git rm .atdd/manifest.yaml`.
- **Precondition**: `shadow` reports zero drift **and** `hot-path` passes. Both, in that order.
- **Invariant**: **I2** — the projection is the derived, gated source of truth. A fallback is not a
  safety net; it is a second source of truth that only speaks up when the first is quiet, and while
  it answers, two developers can hold two different answers and both be reading a file the tool told
  them to trust.

⚠️ **One-way door.** The manifest goes stale the moment the last writer stops, so restoring the
readers restores readers of a lie. If you must roll back, regenerate the manifest **from the store**
— never from git history, which is stale by exactly the interval the fallback was gone. Trigger and
procedure: `.atdd/policy/migration-rollout.yaml`, step `decommission-manifest`.

---

## blocking-mode — make canonicality required

Turns the projection canonicality check from advisory into a **required** status check.

- **Command**: `atdd state canonicality --root .` is the check; making it required is a branch
  protection change (see `.github/atdd-merge-authority-policy.yaml`).
- **Precondition**: `decommission-manifest` is done and `shadow` has been clean throughout.
- **Invariant**: **I6** — local hooks are convenience; CI and branch protection are authority. This
  step is where that sentence stops being an aspiration.

Reversible: it is a protection setting, and turning it off restores the previous world in one click.
It is the *only* late step that is.

---

## cutover — declare M8 done, or find out you cannot

Evaluates the three M8 exit criteria. It changes nothing; it only tells you the truth.

- **Command**: `atdd state cutover --root .`
- **Precondition**: none. Run it whenever you like — including on day one, where it will fail and
  tell you exactly which of the three you have not done.
- **Invariant**: **I2** (the projection is the derived, gated shared state), **I7** (GitHub is an
  optional mirror no lifecycle decision reads). The third criterion — the manifest is not a fallback
  — is the one M8 adds, and the check names all three by the guard that owns each.

It fails while **any one** criterion is unmet and names which. It is deliberately *not* satisfied by
"the manifest file is gone": deleting the file while the readers survive is how you ship a tool that
works perfectly until the first developer who still has one.
