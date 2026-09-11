# URN: test:govern-lifecycle:release-state-is-observed-not-inferred:Y010-UNIT-002-could-not-ask-is-not-absent
# Acceptance: acc:govern-lifecycle:Y010-UNIT-002-could-not-ask-is-not-absent
# WMBT: wmbt:govern-lifecycle:Y010
# Phase: GREEN
# Layer: backend.unit
"""Y010-UNIT-002 — an unanswered question is not a negative answer (#1924).

Both observers return three values, not two. If a PyPI outage or a rate-limited
`gh` returned False, the gate would read "wheel absent" and publish a duplicate —
the same class of defect as the one being fixed, introduced by the fix. So the
failure path returns None, and it is asserted here rather than assumed.
"""
from __future__ import annotations

import json
import urllib.error
from types import SimpleNamespace

from atdd.state.version import github_release_exists, version_on_pypi


class _Resp:
    def __init__(self, payload): self._p = payload
    def read(self): return json.dumps(self._p).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _opener(payload):
    return lambda url, timeout=None: _Resp(payload)


def test_pypi_answers_present() -> None:
    got = version_on_pypi("4.73.1", opener=_opener({"releases": {"4.73.1": [{"x": 1}]}}))
    assert got is True


def test_pypi_answers_absent() -> None:
    got = version_on_pypi("4.73.9", opener=_opener({"releases": {"4.73.1": [{"x": 1}]}}))
    assert got is False


def test_a_release_key_with_no_files_is_not_a_wheel() -> None:
    """A deleted release leaves the key with an empty list."""
    got = version_on_pypi("4.73.1", opener=_opener({"releases": {"4.73.1": []}}))
    assert got is False


def test_pypi_unreachable_is_unknown_not_absent() -> None:
    def boom(url, timeout=None):
        raise urllib.error.URLError("network down")
    assert version_on_pypi("4.73.1", opener=boom) is None


def test_pypi_malformed_payload_is_unknown_not_absent() -> None:
    assert version_on_pypi("4.73.1", opener=_opener({"nope": {}})) is None


def test_github_answers_present() -> None:
    def runner(*a, **k):
        return SimpleNamespace(returncode=0, stdout="12345\n", stderr="")
    assert github_release_exists("v4.73.1", "o/r", runner=runner) is True


def test_github_404_is_a_real_absent() -> None:
    def runner(*a, **k):
        return SimpleNamespace(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")
    assert github_release_exists("v4.73.1", "o/r", runner=runner) is False


def test_github_rate_limited_is_unknown_not_absent() -> None:
    """THE ONE THAT MATTERS: this exact stderr is what produced the orphans."""
    def runner(*a, **k):
        return SimpleNamespace(
            returncode=1, stdout="",
            stderr="GraphQL: API rate limit already exceeded for site ID installation.")
    assert github_release_exists("v4.73.1", "o/r", runner=runner) is None


def test_github_uses_the_rest_endpoint_not_the_graphql_subcommand() -> None:
    """REST and GraphQL are separate buckets, and GraphQL is the one that failed."""
    seen = {}
    def runner(argv, **kwargs):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="1", stderr="")
    github_release_exists("v4.73.1", "o/r", runner=runner)
    assert seen["argv"][:2] == ["gh", "api"], seen["argv"]
    assert "repos/o/r/releases/tags/v4.73.1" in seen["argv"], seen["argv"]
    assert "release" not in seen["argv"][:3], (
        "`gh release view` resolves via GraphQL; this must stay on REST"
    )


def test_gh_missing_entirely_is_unknown() -> None:
    def boom(*a, **k):
        raise OSError("gh not found")
    assert github_release_exists("v4.73.1", "o/r", runner=boom) is None
