"""Repo-root + retired on-disk-injection helpers for the `policy` family (#1212, #1458).

The policy variants no longer inject their faults here: every one of them stages its
fault under ``tmp_path`` and re-points a copied graph at it (#1458, E035), so nothing
writes the real checkout. What survives is ``repo_root`` (used to locate the real bytes
a staged tree mirrors) and ``overwrite_file``, which is RETAINED DELIBERATELY as the
E035-RED-001 characterization oracle: ``test_e035_root_reader_fault_in_staged_root``
drives it to prove the retired on-disk mechanism really did rewrite a tracked file, which
is the hazard the staged root removes. Delete it and that RED characterization goes
vacuous.

``temp_new_file`` was dropped with #1458 — its only caller, the stale-suppression probe,
now stages its marker file under ``tmp_path`` instead of dropping it into ``src/atdd/``.

Not a test module (no ``test_`` prefix → not collected).
"""
from __future__ import annotations

import contextlib
from pathlib import Path


def repo_root() -> Path:
    # .../src/atdd/validators/conventions/policy/_parity.py
    return Path(__file__).resolve().parents[5]


@contextlib.contextmanager
def overwrite_file(path: Path, new_content: str):
    """Back up *path*, replace its content, restore the exact original bytes on exit.

    RETAINED as the E035-RED-001 characterization oracle only — no policy variant injects
    through it any more. Do not reintroduce it into a fault test.
    """
    original = path.read_bytes()
    try:
        path.write_text(new_content, encoding="utf-8")
        yield
    finally:
        path.write_bytes(original)
