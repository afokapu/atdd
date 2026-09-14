#!/usr/bin/env bash
# #2025 lab — read-only against the live store; every measurement runs on a copy.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "$here" rev-parse --show-toplevel)"

# The Control Root is the nearest ancestor holding the store. Walking up rather
# than assuming the repo's parent keeps this working from a worktree, which in
# sibling layout sits at <control-root>/worktrees/<slug> — two levels down.
root="${ATDD_CONTROL_ROOT:-}"
if [[ -z "$root" ]]; then
  candidate="$repo"
  while [[ "$candidate" != "/" ]]; do
    if [[ -f "$candidate/.atdd/state/state.sqlite" ]]; then
      root="$candidate"
      break
    fi
    candidate="$(dirname "$candidate")"
  done
fi
if [[ -z "$root" ]]; then
  echo "no Control Root above $repo holds .atdd/state/state.sqlite" >&2
  exit 2
fi

echo "Control Root: $root"
PYTHONPATH="$repo/src${PYTHONPATH:+:$PYTHONPATH}" python3 "$here/measure.py" "$root"
