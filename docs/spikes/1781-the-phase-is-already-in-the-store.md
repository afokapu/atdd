# 1781 spike — the phase is already in the store; the hooks just never ask

Discovery for #1781, 2026-09-13. This issue was filed on a premise that was already
false, and re-scoping it needed evidence rather than argument. That evidence is here.

## What the issue claimed, and what is true

| Claim (2026-08-09) | Status | Evidence |
|---|---|---|
| `work_item` carries no phase | **false** | `objects.state` IS the phase; 1025/1025 populated |
| Phase lives only on the GitHub label | **false** | store-first since `5f9b353e`, 2026-06-30 (#1203/#1266) |
| `transition()` writes the provider, store never learns | **false** | `issue.py:279` `_store_set_status` → `objects.set_state()` |
| No hook can enforce the phase machine | **half true** | it *can* read it — `store_mirror_gate` does — but nothing acts on it |
| No transition is ever recorded | **TRUE** | 7 event types, none is a transition |

`issue.py:270` says it outright: *"#1270 slice F: the State Store is authoritative for
the work-item phase (#1203 Phase 2) and every reader now resolves the phase from it."*

Entry 1's measurement was real but generalised wrongly: it sampled #1761 and #1762,
two work items authored and never transitioned, saw `state` null, and concluded the
field did not exist.

## The pre-push lab

Disposable repo + bare remote + the shipped hook copied byte-for-byte. `atdd` replaced
by a shim that logs argv and fails `validate`, as a RED test makes it fail. The
decision block was extracted from the hook with `awk` rather than retyped, so the
harness tests the hook and not a transcription of it.

| changed files | bits | verdict |
|---|---|---|
| `.atdd/evidence/<n>/note.md` | `00000` | fast path — push passes |
| `docs/spikes/<n>.md` | `00000` | fast path — push passes |
| (empty commit) | `00000` | fast path — push passes |
| `src/atdd/planner/validators/tests/test_*.py` | `01000` | validators run — push blocked |

Phase held at INIT / PLANNED / RED / GREEN: **bits identical every time (`01000`).**

End to end: a first commit outside the blast radius pushes clean and `atdd validate` is
never invoked; a RED test inside it is blocked. The only variable is the file path.

## Why that matters beyond the annoyance

`store_mirror_gate._check_divergence(result, issue, state)` receives the Store phase
for the work_item bound to THIS branch, in-process, in the pre-push hook. Sixty lines
later the blast-radius block blocks the push having consulted nothing. The hook does
not lack the fact. It has the fact and drops it.

Consequence, observed on #1959: a RED commit touching a blast-radius path cannot be
pushed, so the PR that `INIT→PLANNED` demands cannot be opened, so the phase walk
happens after the work is done. The workaround — first commit outside the blast
radius, which is what landed this very file — is real and undiscoverable.

## Prototype

A 12-line patch consulting the phase before blocking:

| phase | shipped hook | patched hook |
|---|---|---|
| INIT | BLOCKED | BLOCKED |
| PLANNED | BLOCKED | BLOCKED |
| RED | BLOCKED | **ALLOWED** |
| GREEN | BLOCKED | BLOCKED |

GREEN still blocks, so a genuinely broken build is still caught, and the escape is
bounded by the lifecycle: RED→GREEN is gated on the tests passing.

Caveat: the prototype stubbed the phase lookup through the shim. A real implementation
should reuse the resolution `store_mirror_gate` already performs rather than shell out.
