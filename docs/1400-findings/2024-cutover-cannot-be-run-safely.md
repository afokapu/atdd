# #2024 — the cutover's other two hazards: no backup, no atomicity, and an exit check that reads the working tree

Measured 2026-09-14 against `origin/main` at `5529abf4`. Companion to
`1622-projection-path-in-sibling-layout.md`, which covers the third hazard (the projection
path resolving outside git) and is not restated here.

## 1. `migrate-store` takes no backup, and cannot

`reconcile.py:381` ships `backup_store()`. It does the right thing in the right order:

```
checkpoint(db_path)                       # PRAGMA wal_checkpoint(TRUNCATE)
candidate = <db>.sqlite.backup[.N]        # never overwrites an existing backup
shutil.copy2(db_path, candidate)
```

The checkpoint is not decoration. `checkpoint()`'s own docstring states the failure it
exists to prevent:

> The store runs in WAL mode, so recent commits can still be sitting in
> `state.sqlite-wal` rather than in the database file itself. A plain file copy taken at
> that moment silently omits them.

`migrate_cli.py` calls it **zero** times:

```
$ git show origin/main:src/atdd/state/migrate_cli.py | grep -n "backup\|reconcile"
(no matches)
```

So the one command that mutates the only surviving source of truth in place is the one
command that takes no copy of it first.

## 2. There is no enclosing transaction, and the obvious fix does not compose

`store_migration.migrate_store` (`store_migration.py:238`) iterates work items and writes
per object:

- `store.objects.upsert(...)` — `ObjectStore.upsert` opens `with self._conn:` at `store.py:144`
- `store.objects.rekey(...)` — `ObjectStore.rekey` opens its own at `store.py:232`

Each is its own commit. Dying at object 400 of 1047 leaves 399 migrated and 648 not, which
is precisely the state the module docstring says must never exist:

> this mutates the store *in place*, so a partial run damages the only surviving source of
> truth rather than a derived tree — and a half-migrated store cannot be told apart from an
> unmigrated one, leaving the operator no way back.

`inspect_store`'s refuse-before-you-write guard does not help here: it judges the store
*before* the loop, so it prevents a lossy migration, not an interrupted one.

**The tempting repair is wrong.** Wrapping the loop in an outer `BEGIN` will not hold:
`sqlite3`'s `with conn:` commits the **outermost** transaction, so the per-call context
managers inside `upsert` and `rekey` commit the enclosing one out from under the loop. The
nesting does not compose, and the result would look atomic while being exactly as
non-atomic as today.

**The repair is not "migrate the backup" — that destroys the undo.** An earlier revision of
this document said to migrate against a `backup_store()` copy and swap. `backup_store()`
returns the **sole** copied file (`reconcile.py:381`), so migrating it migrates the backup.
Run to completion: the live store ends 30/30 contract-shaped **and so does the "backup"**,
`backup == pre-run` is **False**, and nothing on disk still holds the pre-migration store.
The repair had no undo in it even on success.

**The repo already ships the correct pattern**, and this work should reuse it rather than
invent one — `reconcile.py` does all three steps:

```
backup  = backup_store(db_path)            # reconcile.py:847  immutable undo, never written
scratch = _scratch_copy(db_path, workdir)  # reconcile.py:877  separate mutable copy
...mutate the scratch...
_replace_store(scratch, db_path)           # reconcile.py:936  unlink -wal/-shm, then move
```

Measured against that pattern — **without quiescing the store first**, which an earlier
revision of the probe did and which masked the real case: the scratch migrates 30/30 and
re-inspects clean, the live store ends fully migrated, and the backup still holds the pre-run
store. But it holds it as a **snapshot, not as bytes**:

```
backup == pre-run BYTES?    False   <- backup_store checkpointed the live file first
backup == pre-run SNAPSHOT? True    <- the property that actually holds
```

Byte-identity is not available here for the backup either, and demanding it was the same
contradiction this document criticises two paragraphs below. The assertion to require is
**logical snapshot preservation plus restorability**: restore the backup through the same
`_replace_store` path and the live store's snapshot equals the pre-run store's again. A backup
nobody can restore from is not an undo.

`_replace_store` also already unlinks the WAL sidecars. That matters: the naive
`write_bytes` swap over a live WAL store yields **`sqlite3.DatabaseError: database disk
image is malformed`**, where `_replace_store` reopens clean.

Leaving `upsert`/`rekey` untouched still matters: `rekey`'s transaction is load-bearing,
re-pointing `relationships`, `events`, `external_refs` and `overlay_events` **before**
deleting the old row against `ON DELETE CASCADE`.

### Two things no copy count fixes

**"Byte-identical" is not well-defined here — for the live file *or* the backup.**
`backup_store` checkpoints the *live* store before copying (`reconcile.py:389` → `:365`), so
`state.sqlite`'s bytes change merely by taking the backup, before any migration runs. A
success criterion demanding byte-identity would fail a correct implementation, and it can only
be made to pass by quiescing the store first — exactly the kindness that hides the defect.
Preservation has to be stated over the snapshot, the object set and their content, and paired
with a restore that is actually exercised.

**A concurrent writer is lost regardless.** The scratch is a snapshot at T0: three objects
committed to the live store during the migration, **zero** survived the swap, with one copy
or two. Only a fence fixes that. `BEGIN EXCLUSIVE` refuses another writer loudly
(`database is locked` after the 5s `busy_timeout`) and leaves **readers unaffected**
(0.00s) — but it refuses writers across every worktree sharing this store (122 registered,
61 sibling checkouts), and `db.py:9` configures WAL precisely for "concurrent readers + a
writer (sibling worktrees)". That is an operational trade to state, not a free fix.

Reproduce: `docs/spikes/labs/2024-migrate-store-durability/probe.py` (this branch, not `main`).

## 3. The cutover exit check reads the working tree

`cutover.py:121`:

```python
if not directory.is_dir() or not any(directory.glob("*.yaml")):
```

and it then hands that same `Path` to `check_canonicality`, which reads bytes off disk via
`_read_bytes` → `Path(projection_dir).glob(...)`.

The claim stamped on the verdict (`cutover.py:49-51`) says something else:

> the committed projection is the shared source of truth: project(hydrate(p)) == p, byte
> for byte, **over the projection at HEAD**

Nothing in the code path touches git. So `atdd state cutover` can report **3/3 — COMPLETE**
over files that have never been committed. The gate that exists to prove the cutover
happened will certify that it did when it did not.

### Which `projection_at`? — measured, and the first answer was wrong

Two functions carry that name:

| | returns | keyed by |
|---|---|---|
| `merge_authority.projection_at` (`merge_authority.py:170`) | `Dict[str, Dict[str, Any]]` — parsed YAML | uid |
| `gitstore.projection_at` (`gitstore.py:63`) | `Dict[str, str]` — text | filename |

This document originally concluded that `gitstore.projection_at` was "the byte-exact
reader" to reuse. **A probe over ten constructed git repositories refuted that**, and the
correction is recorded here rather than left to be rediscovered.

**What held.** On a repo with no projection at HEAD — never committed, committed then
deleted, or present in the working tree only — *both* functions return `{}`. The criterion
can report `unmet` without crashing. `gitstore.projection_at` achieves this with
`ls-tree ... check=False`; `merge_authority.projection_at` achieves it because a pathspec
matching nothing exits 0.

**What did not hold.** `gitstore._git` (`gitstore.py:36`) runs `subprocess.run(..., text=True)`,
which applies universal-newline translation and UTF-8 decoding to the blob:

| committed blob | `projection_at` returns | byte-exact? |
|---|---|---|
| `b'uid: wi_CRLF\r\nslug: windows\r\n'` | `b'uid: wi_CRLF\nslug: windows\n'` | **no** |
| `b'uid: wi_CR\rslug: oldmac\r'` | `b'uid: wi_CR\nslug: oldmac\n'` | **no** |
| `b'uid: wi_BAD\nslug: \xff\xfe\n'` | **raises `UnicodeDecodeError`** | n/a |

The CRLF row is a **false pass on the gate**, which is the same class of defect as the one
this document reports:

```
true committed blob == canonical LF output ?  False   <- the honest verdict: NOT canonical
text-read blob      == canonical LF output ?  True    <- what the criterion would conclude
```

A projection committed with CRLF endings is not what `project()` emits, so it is not
canonical — but normalised to LF before comparison it compares equal, and the criterion
reports `met`. Meanwhile the other half of the comparison (`_read_bytes` → `path.read_bytes()`)
reads true bytes, so the two sides are not measured the same way.

`merge_authority.projection_at` failed for two further reasons the probe surfaced: it
**raises** on a repo with no commits (a cold start `reconcile.resolve_head` explicitly calls
legitimate), and it **silently drops** a committed file carrying no `uid`.

**The reader that works** is neither, as written: the same two git calls on **binary** pipes,
returning `Dict[str, bytes]`. That cleared all ten repos and was byte-identical to the
committed blob in every case, CRLF and non-UTF-8 included — and it pairs correctly with
`check_canonicality`'s existing `read_bytes()` side.

Not free: `gitstore.projection_at` has existing callers whose return type would move from
`str` to `bytes`. Whether this lands as a `text=False` sibling or a change to the function
itself is an implementation call, and the caller survey belongs in the plan.

Reproduce: `docs/spikes/labs/2024-projection-at-byte-exactness/probe.py` (this branch, not `main`).

## 4. The path fix must name every reader, and `--from` must be closed

Two gaps in the obvious repairs, both verified:

**Only the writer moves — and that took measuring.** `reconcile.projection_path`
(`reconcile.py:361`) also resolves `<control-root>/.atdd/state/projection`, and a re-review
called it a second instance of this defect: move only `atdd state project` and ordinary
reconciliation would read the old parent path. **That state is not reachable.**

`assert_reconcilable` (#1580) refuses a Control Root that is not itself the git checkout, and
it gates *both* call sites — `hydrate` at `:442` before `:444`, `reconcile` at `:811` before
`:813`. Measured in a constructed sibling layout, both raise `SharedStoreReconcileRefused`;
neither reaches the path. In single-repo layout the Control Root **is** the worktree — `:440`
literally sets `repo = control_root` — so the path already equals `<repo>/.atdd/state/projection`
and agrees with the git readers. The only caller outside `reconcile.py` is a
`reconcile_local_store` test that passes the checkout itself.

Changing it would be a no-op in both layouts. The survey was worth doing and the instruction
behind it — name every default reader, do not assume — was right; it is the edit that was
wrong. A guard test now pins the reasoning, and fails if that refusal is ever relaxed.

Worth recording separately, and out of scope here: because of #1580, **sibling-worktree layout
cannot run `reconcile` or `hydrate` at all**. This repo's own layout therefore cannot exercise
the reconciliation half of the projection story, which makes "the cutover works here" a larger
claim than these three defects.

**Fixing the default cutover path is not sufficient.** `_cmd_cutover` forwards
`args.from_dir` straight into `cutover.check` (`migrate_cli.py:280`) and
`_projection_criterion` treats whatever it is handed as authoritative (`cutover.py:120`).
Measured: a canonical 3-file projection written **outside the repository**, never committed,
passed through `--from` → the criterion reports **met**, under a claim whose own text reads
"over the projection at HEAD".

**Containment is not the fix.** An implementation that merely constrained `--from` to paths
inside the worktree would satisfy that case while still reading an **uncommitted in-repo**
directory — the same bypass wearing a different hat. Both must fail, and the discriminating
test runs in the other direction too: commit a canonical projection, corrupt the working-tree
copy, and the criterion must still report **met**. The property is HEAD resolution, not
containment. `--from` must resolve at HEAD, or be removed.

## Why these travel together

They are one operation's safety envelope. Fixing the path without the HEAD read still lets
the gate certify an uncommitted cutover. Fixing either without the backup still stakes the
only surviving source of truth on the process not dying. The cutover itself — running the
migration, committing the first projection, flipping M8 — is a separate issue that depends
on this one.
