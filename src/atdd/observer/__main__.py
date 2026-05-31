"""``python -m atdd.observer`` — read-only event-stream view (§8)."""
from __future__ import annotations

import sys

from atdd.observer import run

if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
