# #2029 lab — cutover rehearsal

`rehearsal.py` answers the question #2029 rests on: does the shipped sequence —
`migrate-store`, `project`, commit, `cutover` — reach 3/3 against the real corpus?

```
python3 docs/spikes/labs/2029-cutover-rehearsal/rehearsal.py
```

**Read-only against the live store by construction.** The Control Root database is
WAL-checkpointed and copied aside before anything runs — the two steps
`reconcile.backup_store()` performs, because a plain `cp` of a WAL-mode database silently
omits recent commits. Every mutation lands on that copy, inside a throwaway checkout the
script creates and removes.

It exists because the first rehearsal was run by hand and thrown away, leaving prose that
could not be re-derived — and its counts were stale within the hour. This script re-measures
on every run.

It also demonstrates the working-tree/HEAD defect that #2024 owns, because #2029's Done-when
depends on it. If those two lines stop reporting `UNMET` / `MET`, #2024 has landed and
#2029's acceptance can tighten.

Result on 2026-09-14:

```
corpus            1051 work items, 1 already contract-shaped
defects           0
migrated          1050 rekeyed, 1050 attributed, drops on 945
projected         747 documents | canonicality OK
committed         747 files
cutover           MET=True  (3/3)
committed-not-in-tree   -> UNMET  (the criterion ignores HEAD)
in-tree-not-committed   -> MET    (3/3 before anything is committed)
```
