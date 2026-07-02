# URN: test:govern-lifecycle:state:reconcile-release-base-integration-resolved-base-bumps-above-pypi
# Issue: #1326 (#1172 CI publication path)
# Phase: RED
# Layer: application
# Assertion: behavioral
"""#1326 — the resolved base flows through set -> bump above the PyPI latest.

This is exactly the sequence the rewired ``publish.yml`` runs in one CI job over
an ephemeral store: resolve the base from ``semver_max(pypi_latest, git_tag)``,
reconcile the store's current to it, then bump by the merge commit's change class.
The acceptance: given PyPI ``3.152.0`` and a git tag ``3.151.4``, the base is
``3.152.0`` and a PATCH bump yields ``3.152.1`` — NEVER ``3.151.5`` — and the
result is provably above the PyPI latest. The PyPI-unreachable path falls back to
the git tag and still completes.
"""
from __future__ import annotations

import contextlib
import io
import json
import urllib.error

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state import version as ver


def _fake_opener(payload):
    @contextlib.contextmanager
    def _open(url, timeout=None):
        yield io.BytesIO(json.dumps(payload).encode("utf-8"))
    return _open


def _raising_opener(url, timeout=None):
    raise urllib.error.URLError("PyPI unreachable")


@pytest.fixture()
def conn(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    c = connect(db)
    try:
        yield c
    finally:
        c.close()


def test_resolved_base_from_pypi_bumps_to_3_152_1_not_3_151_5(conn):
    pypi = ver.latest_on_pypi(opener=_fake_opener({"info": {"version": "3.152.0"}}))
    base = ver.resolve_release_base("3.151.4", pypi)     # 3.152.0, not the tag
    assert base == "3.152.0"

    ver.set_version(conn, base)
    ver.bump(conn, "PATCH")                              # a fix merge -> PATCH

    resolved = ver.emit(conn)
    assert resolved == "3.152.1"                          # NOT 3.151.5
    assert ver.parse(resolved) > ver.parse("3.152.0")     # strictly above PyPI


def test_resolved_base_never_regresses_below_pypi_for_any_change_class(conn):
    pypi = "3.152.0"
    base = ver.resolve_release_base("3.151.4", pypi)
    ver.set_version(conn, base)
    ver.bump(conn, "MINOR")                               # even a feat merge
    assert ver.parse(ver.emit(conn)) > ver.parse(pypi)    # 3.153.0 > 3.152.0


def test_pypi_unreachable_falls_back_to_git_tag_and_still_bumps(conn):
    pypi = ver.latest_on_pypi(opener=_raising_opener)     # None — outage
    base = ver.resolve_release_base("3.151.4", pypi)      # fall back to the tag
    assert base == "3.151.4"

    ver.set_version(conn, base)
    ver.bump(conn, "PATCH")
    assert ver.emit(conn) == "3.151.5"                    # release still completes
