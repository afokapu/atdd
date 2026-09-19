#!/usr/bin/env bash
# #2042 lab — read-only against the live store; every measurement runs on a copy.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"

# The Control Root is the nearest ancestor holding the store. Walking up rather than
# assuming the repo's parent keeps this working from a worktree, which in sibling
# layout sits at <control-root>/worktrees/<slug> — two levels down.
root="${ATDD_CONTROL_ROOT:-}"
if [[ -z "$root" ]]; then
  candidate="$repo"
  while [[ "$candidate" != "/" ]]; do
    if [[ -f "$candidate/.atdd/state/state.sqlite" ]]; then root="$candidate"; break; fi
    candidate="$(dirname "$candidate")"
  done
fi
[[ -n "$root" ]] || { echo "no Control Root above $repo holds .atdd/state/state.sqlite" >&2; exit 2; }

echo "Control Root: $root"
echo
echo "=== probe 1: the residual, object by object ==="
PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}" python3 "$here/residual.py" "$root"
echo
echo "=== probe 2: does a truncated projection survive every check? ==="
PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}" python3 "$here/truncation.py"
