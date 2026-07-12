# URN: test:author-atdd-substrate:author-issue-body:C012-UNIT-001-store-unreachable-fails-loud
# Acceptance: acc:author-atdd-substrate:C012-UNIT-001-store-unreachable-fails-loud
# WMBT: wmbt:author-atdd-substrate:C012
# Phase: RED
# Layer: application
"""C012-UNIT-001 — store unreachable ⇒ `atdd author issue` fails loud, no body-only.

The recurrence guard for the orphaned #1271: when the State Store cannot be
reached, the generate path must exit non-zero and emit NO schema-valid body to
stdout — it must NOT silently degrade to a body-only string. Today the generate
path ignores the store and always prints the body with exit 0, so this fails
until the store-first fail-loud publish lands (GREEN).
"""
from __future__ import annotations

from ._publish_helpers import run_author_issue


def test_c012_unit_001_store_unreachable_fails_loud(tmp_path, monkeypatch):
    # Point the Control Root at a regular FILE so the .atdd/state directory can
    # never be created — the store is genuinely unreachable.
    unreachable = tmp_path / "not-a-dir"
    unreachable.write_text("i am a file, not a control root")
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(unreachable))

    # No --slug: uses only flags that exist today, so a RED failure is
    # behavioural (exit 0 + body printed), not an argparse rejection.
    code, out = run_author_issue([
        "--title", "Store unreachable probe",
        "--type", "implementation",
        "--status", "INIT",
    ])

    assert code != 0, "author issue must FAIL LOUD when the store is unreachable, not exit 0"
    assert "### Graph Context" not in out, (
        "no schema-valid body may be emitted to stdout on a store failure "
        "(no body-only degrade — the #1271 orphan gap must not recur)"
    )
