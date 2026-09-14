# #1622 — dry run: the live corpus, with every disposition applied

Measured 2026-09-13 against a read-only copy of the Control Root store. Simulates the
end state — all 20 dispositions applied, `owner_actor` supplied as `migrate_store` does,
identity minted — and asks whether `atdd state project` would write.

## Result

| | |
|---|---|
| projectable objects (non-`COMPLETE`) | **737** |
| documents that fail `assert_deterministic` or `validate_document` | **0** |
| digest stable under input reordering | yes |
| written → read back → re-digested, byte-identical | yes |
| `check_canonicality` | OK |

**The projection would be written, and it round-trips.** Nothing in the corpus blocks the
cutover once the dispositions are applied.

## Correction: the "51 host-path bodies" were never a blocker

An earlier reading of this session claimed 51 projectable objects carried absolute host
paths in `body` and would refuse the whole projection. That was wrong, and the error was
scanning `_HOST_PATH_RE` directly rather than going through the rule that actually runs.

`assert_deterministic` exempts free text by design:

    FREE_TEXT_FIELDS = frozenset({"body"})

with the reason stated in its own docstring — body content is *authored, not generated*,
so it is deterministic by preservation. The exemption is top-level only: a `body` key
nested inside a structured field (`external_refs.body`) is machine-written and still
scanned. Verified both ways.

The original `NondeterministicProjectionError` on the live store named `worktree_path`,
which is a structured field, correctly scanned — and which is DROP. That leak goes with
the disposition, and there is no second one behind it.

## The one subtlety worth carrying into implementation

`type` must be grown as **nullable**. Typed as plain `str`, 22 of the 737 objects refuse
with `field 'type' has type NoneType`. The findings already specified `["string","null"]`;
this is a note for whoever writes `FIELD_TYPES`, because the failure is quiet until the
whole projection refuses on the first one.

`wagon` is nullable for the same reason.

## What this does and does not prove

Proves: the corpus is clean under the agreed dispositions, the documents are
deterministic, and the round trip holds at full scale — not on a synthetic fixture.

Does not prove: that `store_migration` applies the dispositions correctly. It applies none
today; the dry run removes the keys itself. Phase 2 still has to write that, and this
measurement is the target it should hit.
