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

**What does work** is to migrate against a `backup_store()` copy, re-run `inspect_store` on
the result, and swap the copy into place only if it is clean. One change buys the backup,
the atomicity and the operator's undo together — and it leaves `upsert`/`rekey` alone,
which matters, because `rekey`'s transaction is load-bearing: it re-points
`relationships`, `events`, `external_refs` and `overlay_events` **before** deleting the old
row, against `ON DELETE CASCADE`. Breaking that would silently take each object's entire
history with it.

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

### Reuse the right `projection_at`

Two functions carry that name, and the difference decides the fix:

| | returns | keyed by |
|---|---|---|
| `merge_authority.projection_at` (`merge_authority.py:170`) | `Dict[str, Dict[str, Any]]` — parsed YAML | uid |
| `gitstore.projection_at` (`gitstore.py:63`) | `Dict[str, str]` — raw text | filename |

The criterion's claim is *byte for byte*. Parsing discards exactly the bytes the claim is
about, so the byte-exact reader — `gitstore.projection_at` — is the one to reuse.
`gitstore.projection_at`'s docstring already states the property the criterion needs:

> Read straight out of git object storage, so it reports what that commit *committed* —
> never what the working tree happens to hold right now.

Secondary consequence for whoever implements it: `check_canonicality` takes a `Path` and
reads from disk, so reading HEAD needs either a bytes-accepting entry point or HEAD's
projection materialised into a temp directory first. That is a design choice, not a detail.

## Why these travel together

They are one operation's safety envelope. Fixing the path without the HEAD read still lets
the gate certify an uncommitted cutover. Fixing either without the backup still stakes the
only surviving source of truth on the process not dying. The cutover itself — running the
migration, committing the first projection, flipping M8 — is a separate issue that depends
on this one.
