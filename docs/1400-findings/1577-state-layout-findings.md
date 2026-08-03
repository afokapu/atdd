# state-doctor findings — layout drift diagnostic (for #1577's critical-path detour)

> **Assignment note:** This pane's ORIGINAL task was **#1577 (store↔GitHub synchronicity
> token)** — a store→GitHub-*label* sync marker. It was **NEVER STARTED**; the operator
> redirected me to this state-doctor diagnostic before any #1577 design/code began. A prior
> READ-ONLY *exploration* of the token idea (different assignment) produced
> `sync-token-findings.md` + `explore-sync-token/HANDOFF-sync-token.md`; #1577 itself is
> unexplored. Do not mistake the exploration doc for #1577 having been worked.

## 1. Headline — this is operational-install drift, NOT store drift
`atdd state doctor` → **Status: INVALID**, **143 ERROR lines** (operator's "roughly 10" is a
large undercount): **71× `.atdd/extensions`** + **71× `.atdd/workspaces`** + **1× per-worktree
`state.sqlite`** (`main/.atdd/state/state.sqlite`, a **0-byte empty stub**). Errors span **71
sibling worktrees**.

These are **orphaned per-worktree operational dirs**. Runtime resolves all operational
reads/writes to the **Control Root** (`_substrate_root`→`resolve_operational_root`, `cli.py:162`),
so nothing reads the per-worktree copies — they are leftovers. **Zero errors touch the
control-root store**, which is already single, 588 work-items, 9.7 MB, and conformant.
**The #1622 projection reads that store → its data source is already clean → this drift does
NOT gate #1622.** migrate-layout here is hygiene, not a prerequisite.

## 2. Safety analysis of `atdd state migrate-layout` (`state/cli.py:348`)
- **Phase A (store consolidation):** only per-worktree store is `main`'s empty stub → folds
  **0 rows**, deletes the stub. Control-root store is the append-only merge TARGET, never
  overwritten. **No sqlite write-contention** (0 writes during the fold).
- **Phase B (operational fold):** copies each `extensions/<id>/<ver>` + `workspaces/<id>/<ver>`
  the Control Root lacks UP (control-root wins on conflict; ids diverge cleanly here —
  `coder.base` vs `coder`, a rename in flight — so it's an additive union), then `rmtree`s the
  per-worktree dirs + unlinks per-worktree `substrate.lock.yaml`.
- **Untouched:** all source, git, and scratch (`cache`/`runtime`/`diagnostics`),
  `orchestrate-state.json`, `worker-state-*.json`.
- **Live worktrees** (`feat-projection-contract-diverged-from-store`,
  `feat-outbox-stranded-no-sync-provider`): neither has its own store; today's writes are in
  `cache/`, `diagnostics/`, `__pycache__` — none in the dirs migrate-layout removes. **Nothing
  is yanked out from under them.**
- **Residual risk:** `shutil.rmtree` isn't atomic — a process mid-write into that exact
  per-worktree `extensions/`/`workspaces/` could error. **Theoretical only** (nothing writes
  there at runtime).

## 3. Suggested run protocol (NO built-in undo — no `--dry-run`, no backup; `.atdd/` is
git-ignored under a non-git Control Root, so not recoverable from git)
```bash
CR=/Users/alecfokapu/Github/atdd
BACKUP=/tmp/atdd-operational-backup-$(date +%Y%m%d-%H%M%S).tgz
find "$CR" -maxdepth 3 \( -path '*/.atdd/extensions' -o -path '*/.atdd/workspaces' \) -type d 2>/dev/null \
  | grep -v "^$CR/\.atdd/" | sed "s#^$CR/##" > /tmp/atdd-backup-list.txt
find "$CR" -maxdepth 4 -path '*/.atdd/state/state.sqlite' 2>/dev/null | sed "s#^$CR/##" >> /tmp/atdd-backup-list.txt
tar czf "$BACKUP" -C "$CR" -T /tmp/atdd-backup-list.txt      # ~182 MB (172 MB dirs + 10 MB store), read-only
# then, in a gap between agent `atdd` invocations:
atdd state migrate-layout && atdd state doctor               # expect Status: VALID
# restore only if needed:  tar xzf "$BACKUP" -C "$CR"
```

## 4. Stale help-text bug
`migrate-layout` subcommand help (`state/cli.py:73`) still reads *"Consolidate to a single
project-root State Store, rebuilt from main's manifest (#1315)"*. That describes the retired
#1315 manifest-rebuild. #1346 replaced it with a genuine per-worktree-store **merge + operational
fold**; the help never updated. Cosmetic, but misleads an operator about what it does.

## 5. Other unstated findings
- **Non-lossy but one edge:** fold preserves content by copying up before delete; the ONLY loss
  case — a per-worktree install sharing id+version with the Control Root but different bytes —
  is **unverified across all 71 worktrees** (no dry-run exists); ids I sampled diverge cleanly.
- **`atdd` upgrade pending:** doctor emits `upgraded 3.106.0 → 4.31.1; run atdd sync && atdd
  init`. Not applied (out of scope). A layout migration under a version mismatch is worth a
  second doctor pass after any sync.
- **Adjacent to #1577:** the worktree list includes
  `feat-auto-phase-project-token-shadows-github-token` — a *project*-vs-*GitHub* token concern
  overlapping #1577's problem space; whoever takes #1577 should reconcile with it.
