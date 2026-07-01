"""Generated production sample with a print() — should be DROPPED when the caller
passes ATDD_SCAN_EXCLUDES=["*/generated/*"].

This is the file that proves the bug fix: before honoring excludes, scanning this
tree always flagged this print(); now an exclude glob matching its path drops it.
"""
from __future__ import annotations


def boot() -> None:
    print("generated boot diagnostic")  # violation UNLESS */generated/* is excluded
