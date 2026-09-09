# fixtures/ — interlocking-infrastructure

Golden consumer trees for the five `coder.train.interlocking-*` conventions
(afokapu/atdd-extensions#25). Each is a miniature consumer repo rooted at
`<fixture>/python/...`, mirroring the scope selectors `python_runtime`
(`python/trains/**/*.py`) + `station_master` (`python/app.py`).

- `clean/` — a correctly wired interlocking-enabled consumer. **No violations.**

Per-rule isolation fixtures — each trips **exactly one** rule_id, proving the five
conventions are enforced independently:

| Fixture | Sole rule_id |
|---|---|
| `dirty_no_resolve_train/` | `coder.train.interlocking-runner-exists` (runner with no `resolve_train`) |
| `dirty_bare_resolution/` | `coder.train.interlocking-resolution-model-exists` |
| `dirty_station_unlinked/` | `coder.train.station-master-interlocking-routing` |
| `dirty_direct_wagon/` | `coder.train.interlocking-delegates-to-trainrunner` |
| `dirty_cargo/` | `coder.train.interlocking-does-not-carry-cargo` |

Broader fixtures:

- `dirty/` — a present-but-broken runner tripping four rule_ids at once
  (resolution-model + station-routing + delegates + no-cargo).
- `dirty_missing_runner/` — interlocking route declared but no `InterlockingRunner`
  class ships (runner-exists + the resulting station-routing defect).

The union across all dirty fixtures covers all five rule_ids; `clean/` has none
(see `../tests/`).
