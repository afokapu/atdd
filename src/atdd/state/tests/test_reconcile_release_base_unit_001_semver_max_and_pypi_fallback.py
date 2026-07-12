# URN: test:govern-lifecycle:state:reconcile-release-base-unit-semver-max-and-pypi-fallback
# Issue: #1326 (#1172 CI publication path)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1326 — reconcile the release base from PyPI, not just the git tag.

The publish pipeline bases the next version on ``git describe`` (the nearest git
tag), which drifts BELOW the real published latest (manual publishes skip tagging,
orphan tags from failed runs, and the git-ignored State Store never reaches CI).
The fix anchors the reconcile base on ``semver_max(pypi_latest, git_tag)`` so the
next version is ALWAYS above what is already published.

These unit tests pin the pure, testable core:

- :func:`semver_max` — greatest by semver *core* (numeric, not lexical), ignoring
  ``None``/unparseable, preserving the winner's original string.
- :func:`latest_on_pypi` — a stdlib PyPI JSON query that returns ``None`` on ANY
  failure (unreachable / malformed) so the release never hard-fails.
- :func:`resolve_release_base` — ``semver_max(git_tag, pypi_latest)``; the base is
  provably ``>= pypi_latest`` so a subsequent bump is strictly above the published
  latest, and it falls back to the git tag when PyPI is unreachable.
"""
from __future__ import annotations

import contextlib
import io
import json
import urllib.error

import pytest

from atdd.state import version as ver


def _fake_opener(payload):
    """A drop-in for ``urllib.request.urlopen`` returning ``payload`` as JSON."""
    @contextlib.contextmanager
    def _open(url, timeout=None):
        yield io.BytesIO(json.dumps(payload).encode("utf-8"))
    return _open


def _raising_opener(url, timeout=None):
    raise urllib.error.URLError("PyPI unreachable")


# ---- semver_max -----------------------------------------------------------

@pytest.mark.parametrize(
    "versions, expected",
    [
        (("3.151.4", "3.152.0"), "3.152.0"),   # pypi ahead of tag
        (("3.153.0", "3.152.0"), "3.153.0"),   # tag ahead of pypi
        (("3.152.0", None), "3.152.0"),        # ignore None
        ((None, "3.152.0"), "3.152.0"),
        (("3.9.0", "3.10.0"), "3.10.0"),       # numeric, not lexical
        (("3.152.0", "3.152.0"), "3.152.0"),   # equal
    ],
)
def test_semver_max_picks_the_greatest_core(versions, expected):
    assert ver.semver_max(*versions) == expected


def test_semver_max_returns_none_when_nothing_parseable():
    assert ver.semver_max(None, "", "not-a-version") is None


def test_semver_max_preserves_the_winners_original_string():
    # PEP 440 local/pre-release suffixes parse to the same core; the ORIGINAL
    # string of the greatest core is returned unchanged.
    assert ver.semver_max("3.152.0", "3.151.4+local") == "3.152.0"


# ---- latest_on_pypi -------------------------------------------------------

def test_latest_on_pypi_reads_info_version():
    latest = ver.latest_on_pypi(opener=_fake_opener({"info": {"version": "3.152.0"}}))
    assert latest == "3.152.0"


def test_latest_on_pypi_returns_none_when_unreachable():
    # A transient PyPI outage must NOT hard-fail the release — callers fall back.
    assert ver.latest_on_pypi(opener=_raising_opener) is None


def test_latest_on_pypi_returns_none_on_malformed_payload():
    assert ver.latest_on_pypi(opener=_fake_opener({"nope": {}})) is None


# ---- resolve_release_base -------------------------------------------------

def test_resolve_release_base_prefers_pypi_when_tag_drifts_below():
    # THE bug: tag 3.151.4 below the published 3.152.0 -> base is 3.152.0.
    assert ver.resolve_release_base("3.151.4", "3.152.0") == "3.152.0"


def test_resolve_release_base_prefers_the_tag_when_it_is_ahead():
    assert ver.resolve_release_base("3.153.0", "3.152.0") == "3.153.0"


def test_resolve_release_base_falls_back_to_tag_when_pypi_unreachable():
    assert ver.resolve_release_base("3.151.4", None) == "3.151.4"


def test_resolve_release_base_is_never_below_the_pypi_latest():
    # The core guarantee: base >= pypi_latest for any tag, so a subsequent bump
    # can never regress below what's already published.
    for tag in ("3.0.0", "3.151.4", "3.152.0", "3.9.99"):
        base = ver.resolve_release_base(tag, "3.152.0")
        assert ver.parse(base) >= ver.parse("3.152.0")


def test_resolve_release_base_raises_when_no_candidate():
    with pytest.raises(ver.VersionError):
        ver.resolve_release_base(None, None)
