# Lab — #2042: nothing proves the committed projection covers the store

Two hypotheses, each stated so it could be false.

| probe | hypothesis | verdict |
|---|---|---|
| `residual.py` | the store→projection gap is a silent truncation, not a declared filter | **REFUTED** — residual is **zero**; every object carries a reason |
| `truncation.py` | a projection missing objects the store holds passes every check | **HELD** — cutover reports MET, canonicality reports canonical |

Together they relocate the defect. The gap is *legitimate*; what is missing is any
**executable** statement of that fact. So this issue is not "find the lost objects" —
it is "make the account of them a check that can fail".

## Running them

    ./lab.sh                                     # both probes
    PYTHONPATH=../../../../src python3 residual.py   <control-root>
    PYTHONPATH=../../../../src python3 truncation.py # builds its own repo

`residual.py` is **read-only** with respect to the live store: it measures a copy, and
migrates that copy so the numbers describe the post-migration world. `truncation.py`
touches no existing repo at all — it builds one under `tmp` and throws it away.

## Probe 1 — the residual is zero

Reading of 2026-09-19, against a store holding 1,282 objects:

| bucket | count | rule that puts it there |
|---|---|---|
| projected | 757 | — |
| excluded: `phase=COMPLETE` | 307 | `ARCHIVED_PHASES` — COMPLETE is derived from merge-to-main, so it has no legal projection document |
| excluded: `kind=agent_session` | 158 | `build_documents` lists `kind=work_item` only |
| excluded: `kind=wmbt` | 56 | same |
| excluded: `kind=hub_adapter` | 2 | same |
| excluded: `kind=hub_session` | 1 | same |
| excluded: `kind=release` | 1 | same |
| **TOTAL** | **1,282** | equals the store exactly |
| **UNEXPLAINED** | **0** | |

**The issue's own alternative branch is the one that holds:** "the 305-object gap may be
fully explained by declared filters — in which case the issue narrows to making that
explanation executable rather than prose." It is, and it does.

Two corrections to the issue as written, both from measurement rather than argument:

- The numbers are stale and **structurally so**. The issue says 1,053 work items and a
  305 gap; the store now holds 1,064 work items and the gap is 307. It moves every time
  anyone authors an issue, so the Done-when must be an invariant (*residual is empty*),
  never a literal (*the gap is 305*). A check pinned to 305 would start failing on the
  next `atdd author issue`.
- The gap is **not** 1,053 → 748 in the sense of work items lost. Of the 525 unprojected
  objects, 218 are not work items at all and were never candidates.

## Probe 2 — and every check still passes without them

A real git repo, a real store, three work items, a committed projection — then one
document deleted and the truncation committed:

    seeded store work items : 3
    committed documents     : 3
    cutover projection criterion, WHOLE projection : MET

    removed wi_01M2WQ7N3P9QZMZ1W2Q6ZG9X8E.yaml
    committed documents now : 2   (store still holds 3)
    cutover projection criterion, TRUNCATED        : MET
    check_canonicality over the truncated tree     : canonical
    non-empty                                      : True

A third of the corpus gone and the cutover certifies it. That is the whole defect in one
screen: byte-identity proves the writer is deterministic, self-canonicality proves the
serializer is stable, and neither has any opinion about what is **absent**, because
nothing in the chain ever consults the store.

This probe is also the acceptance bar the brief set — *a projection with an object
deliberately removed must fail the check* — so it stays as a regression check with the
sign of its verdict flipped once coverage lands.
