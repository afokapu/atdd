# Lab — #2043 contract `$id` spelling

Finding: `../../2043-contract-id-spelling.md`. Frozen sha `36ce055a`.

The harness is kept so the measurement is reproducible; the worlds it builds are
disposable and nothing here is imported by shipped code or run in CI.

## Run

```sh
PY=/path/to/atdd/.venv/bin/python        # any env with this checkout importable
W=/tmp/spike2043

$PY build_world.py      $W-1   # create_contract-authored $id (the reported case)
$PY build_ambiguous.py  $W-2   # theme named `contract`, bare 2-segment $id
$PY build_world3.py     $W-3   # theme named `contract`, bare 3-segment $id

# raw facts for any world
$PY measure.py $W-1

# candidate readers: none | c1 | c3 | c4 | r | c4r
$PY candidates.py $W-1 none;  echo "rc=$?"
$PY candidates.py $W-3 c4r;   echo "rc=$?"

# the same prefix-on-read idiom outside the graph module
ATDD_REPO_ROOT=$W-1 $PY measure_other_readers.py $W-1

# blast radius: candidates against real data (slow — full graph build)
ATDD_NO_CACHE=1 $PY candidates.py /path/to/atdd r
```

`rc` is the signal: 0 = no issues, 1 = issues found. Diff results **by name**,
never by count — two failure sets of equal size are not the same failure set.

## Worlds

| world | `$id` | theme | obeys the written convention? |
|---|---|---|---|
| 1 | `contract:match:result` (prefixed, from `create_contract`) | `match` | **no** |
| 2 | `contract:result` (bare, 2 segments) | `contract` | yes |
| 3 | `contract:match:result` (bare, 3 segments) | `contract` | yes |

World 3 is the one that matters: its bare `$id` is *itself* a syntactically valid
contract URN, so no string inspection can distinguish it from a prefixed one. It
was constructed by an adversarial reviewer to falsify this spike's first
conclusion, and did.

## Two defects this harness itself shipped with

Both were caught by reviewers re-running it, and both are the failure
`../../README.md` already names:

* `measure.py` hardcoded world1's paths and crashed on the other worlds — a
  measurement instrument that cannot measure most of its subjects.
* `candidates.py` always exited 0, so `rc` carried no signal while the README
  told readers to trust it.
