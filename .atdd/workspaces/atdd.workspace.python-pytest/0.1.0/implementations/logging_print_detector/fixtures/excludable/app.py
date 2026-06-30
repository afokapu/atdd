"""In-scope production sample with a print() — flagged UNLESS its path is excluded.

Used by test_logging_print.py to prove ATDD_SCAN_EXCLUDES is honored: scanning
fixtures/excludable with no excludes flags this AND generated/legacy.py; scanning
with the glob "*/generated/*" must still flag THIS file (it is not excluded).
"""
from __future__ import annotations


def render(name: str) -> None:
    print(f"hello {name}")  # violation: bare print() in production code
