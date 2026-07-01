# URN: test:author-atdd-substrate:author-issue-body:E008-UNIT-002-links-exactly-one-github-ref
# Acceptance: acc:author-atdd-substrate:E008-UNIT-002-links-exactly-one-github-ref
# WMBT: wmbt:author-atdd-substrate:E008
# Phase: RED
# Layer: application
"""E008-UNIT-002 — the published work_item carries exactly one github external_ref.

One-per-issue (#1220): the store links a single ``github`` / ``issue`` ref at the
number the projection returned, and a re-author with the same slug is idempotent
— still exactly one ref (the external_refs ON CONFLICT unique key enforces it).
Fails until the store-publish path links the ref (GREEN).
"""
from __future__ import annotations

from ._publish_helpers import (
    STUB_ISSUE_NUMBER,
    open_store,
    run_author_issue,
    stub_github_create,
)


def _author_once(monkeypatch, tmp_path):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    stub_github_create(monkeypatch)
    code, _ = run_author_issue([
        "--title", "Ref probe",
        "--slug", "e008-ref-probe",
        "--type", "implementation",
        "--status", "INIT",
    ])
    return code


def test_e008_unit_002_links_exactly_one_github_ref(tmp_path, monkeypatch):
    assert _author_once(monkeypatch, tmp_path) == 0

    store, conn = open_store(tmp_path)
    try:
        refs = store.external_refs.for_object("e008-ref-probe")
    finally:
        conn.close()

    assert len(refs) == 1, f"expected exactly one external_ref (one-per-issue, #1220), got {len(refs)}"
    ref = refs[0]
    assert ref.provider == "github"
    assert ref.ref_kind == "issue"
    assert ref.ref_value == str(STUB_ISSUE_NUMBER)


def test_e008_unit_002_reauthor_is_idempotent_single_ref(tmp_path, monkeypatch):
    assert _author_once(monkeypatch, tmp_path) == 0
    # Re-author the same slug — must not accumulate a second ref.
    assert _author_once(monkeypatch, tmp_path) == 0

    store, conn = open_store(tmp_path)
    try:
        refs = store.external_refs.for_object("e008-ref-probe")
    finally:
        conn.close()

    assert len(refs) == 1, f"re-author must stay one-per-issue, got {len(refs)} refs"
