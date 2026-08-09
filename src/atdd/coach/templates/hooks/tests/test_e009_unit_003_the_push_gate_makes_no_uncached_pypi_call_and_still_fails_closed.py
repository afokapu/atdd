# URN: test:integration-hardening:run-upgrade-unattended:E009-UNIT-003-the-push-gate-makes-no-uncached-pypi-call-and-still-fails-closed
# Acceptance: acc:integration-hardening:E009-UNIT-003-the-push-gate-makes-no-uncached-pypi-call-and-still-fails-closed
# WMBT: wmbt:integration-hardening:E009
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
"""E009-UNIT-003 — the push path stops paying for the network without going soft.

RED Test for acc:integration-hardening:E009-UNIT-003-the-push-gate-makes-no-uncached-pypi-call-and-still-fails-closed
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E009

``is_outdated()`` documented itself "(no cache)" and ``_gate_against_pypi``
called it on **every** ``git push`` — up to two seconds of network on the
critical path of an operation that had already been paid for, to answer a
question the 24 h cache at ``~/.atdd/version_cache.json`` was already answering
for ``print_update_notice``. #1762 points the gate at that cache.

The half of this that matters more is the half that did **not** change. Making
the gate cheaper must not make it permissive: an install behind the resolved
latest is still refused, the refusal still names the remedy, an unknowable
version still fails *open* rather than closed, and no environment variable is
honoured (E030 retired that class).
"""
from __future__ import annotations

import ast
import inspect
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

import atdd.version_check as version_check

pytestmark = [pytest.mark.coach, pytest.mark.platform]


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the version cache at a throwaway file and stand in a bare directory.

    ``chdir`` matters: ``_gate_main`` consults ``.atdd/config.yaml`` for a
    ``release.minimum_version`` floor first, and a floor would route past the
    PyPI comparison this test is about.
    """
    cache = tmp_path / "version_cache.json"
    monkeypatch.setattr(version_check, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(version_check, "CACHE_FILE", cache)
    monkeypatch.chdir(tmp_path)
    return cache


def _write_cache(cache: Path, latest: str, age_seconds: float) -> None:
    cache.write_text(json.dumps({
        "last_check": time.time() - age_seconds,
        "latest_version": latest,
    }))


def _run_gate(installed: str):
    """Run the gate with a pinned installed version and a urlopen tripwire.

    Returns the SystemExit raised, or None when the gate allowed the push, plus
    the number of times the network was reached.
    """
    calls = []

    def tripwire(*args, **kwargs):
        calls.append(args)
        raise AssertionError("the gate reached the network")

    with patch.object(version_check, "_gate_version", return_value=installed), \
         patch.object(version_check, "urlopen", side_effect=tripwire):
        try:
            version_check._gate_main()
        except SystemExit as exc:
            return exc, len(calls)
    return None, len(calls)


def test_e009_unit_003_a_fresh_cache_costs_no_network(isolated_cache, capsys):
    """The common case: a warm cache, and the push pays nothing to the network."""
    _write_cache(isolated_cache, "4.0.0", age_seconds=60)

    raised, network_calls = _run_gate(installed="4.0.0")

    assert network_calls == 0, "the push gate performed an uncached PyPI fetch"
    assert raised is None, "an up-to-date install must not be refused"
    assert "up to date" in capsys.readouterr().out.lower(), (
        "the gate must still reach and report a verdict, not merely stay silent"
    )


def test_e009_unit_003_a_fresh_cache_still_refuses_an_outdated_install(isolated_cache, capsys):
    """Cheaper, not softer: still exit 1, still naming the remedy, still no bypass."""
    _write_cache(isolated_cache, "4.38.10", age_seconds=60)

    raised, network_calls = _run_gate(installed="4.38.9")

    assert network_calls == 0
    assert raised is not None and raised.code == 1, "an outdated install must still be refused"
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "atdd upgrade" in combined, f"the refusal must still name the remedy:\n{combined}"
    assert "4.38.10" in combined, f"the refusal must still name the latest version:\n{combined}"


@pytest.mark.parametrize("bypass", [
    "ATDD_NO_UPDATE_CHECK", "ATDD_NO_UPGRADE_NOTICE", "ATDD_ALLOW_OUTDATED",
    "ATDD_PREPUSH_FULL", "ATDD_MAX_UNCOMMITTED",
])
def test_e009_unit_003_no_environment_variable_lets_an_outdated_install_through(
    isolated_cache, bypass, monkeypatch,
):
    """E030 retired the bypass class, and moving to the cache does not smuggle one back."""
    _write_cache(isolated_cache, "4.38.10", age_seconds=60)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv(bypass, "1")

    raised, _ = _run_gate(installed="4.38.9")

    assert raised is not None and raised.code == 1, (
        f"{bypass}=1 let an outdated install past the gate"
    )


def test_e009_unit_003_a_stale_cache_is_refreshed_once_and_written_back(isolated_cache):
    """The cost is bounded to one fetch per interval, not abolished.

    A gate that never refreshed would let a machine that only ever pushes drift
    forever behind a cache nobody rewrites. One fetch per
    :data:`~atdd.version_check.CHECK_INTERVAL` is the trade.
    """
    _write_cache(isolated_cache, "4.0.0", age_seconds=version_check.CHECK_INTERVAL + 60)

    fetches = []

    def fetch():
        fetches.append(1)
        return "4.38.10"

    with patch.object(version_check, "_gate_version", return_value="4.38.9"), \
         patch.object(version_check, "_fetch_latest_version", side_effect=fetch):
        with pytest.raises(SystemExit) as exc:
            version_check._gate_main()

    assert exc.value.code == 1
    assert len(fetches) == 1, f"a stale cache must cost exactly one fetch, cost {len(fetches)}"
    assert json.loads(isolated_cache.read_text())["latest_version"] == "4.38.10", (
        "the refreshed value must be written back, or every push pays again"
    )


def test_e009_unit_003_an_absent_cache_and_an_unreachable_pypi_fail_open(isolated_cache, capsys):
    """Nothing to compare against is never a reason to refuse a push."""
    assert not isolated_cache.exists()

    with patch.object(version_check, "_gate_version", return_value="4.38.9"), \
         patch.object(version_check, "_fetch_latest_version", return_value=None):
        version_check._gate_main()  # must not raise

    combined = capsys.readouterr()
    assert "WARNING" in (combined.out + combined.err), (
        "failing open must be stated, not silent"
    )


def test_e009_unit_003_an_unknowable_installed_version_fails_open(isolated_cache):
    """A dev/editable checkout reporting 0.0.0 has nothing to be judged against."""
    _write_cache(isolated_cache, "4.38.10", age_seconds=60)

    with patch.object(version_check, "_gate_version", return_value=None), \
         patch.object(version_check, "urlopen", side_effect=AssertionError("network reached")):
        version_check._gate_main()  # must not raise


def test_e009_unit_003_the_operator_invoked_upgrade_stays_uncached():
    """``atdd upgrade`` must still see PyPI as it is this second.

    The two callers want different answers and #1762 gives them different
    answers: the gate reads the cache because it runs on every push; the command
    an operator deliberately ran does not, because a cached "you are current" in
    response to `atdd upgrade` would be a lie the operator cannot see through.
    """
    with patch.object(version_check, "_gate_version", return_value="4.38.9"), \
         patch.object(version_check, "_fetch_latest_version", return_value="4.38.10") as fetch, \
         patch.object(version_check, "_resolve_latest_version",
                      side_effect=AssertionError("atdd upgrade must not read the cache")):
        outdated, current, latest = version_check.is_outdated()

    assert (outdated, current, latest) == (True, "4.38.9", "4.38.10")
    fetch.assert_called_once()


def test_e009_unit_003_the_gate_asks_for_the_cached_answer_explicitly():
    """Pin the call site itself, so a future edit cannot silently restore the fetch.

    The behavioural tests above would keep passing if someone reverted
    ``_gate_against_pypi`` to the uncached call *and* the cache happened to be
    warm — the fetch would simply cost time nobody measured. This reads the
    source and requires the intent to be stated.
    """
    source = inspect.getsource(version_check._gate_against_pypi)
    tree = ast.parse(source.lstrip())
    cached_kwargs = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "is_outdated"
        for kw in node.keywords
        if kw.arg == "cached" and isinstance(kw.value, ast.Constant)
    ]
    assert cached_kwargs == [True], (
        "_gate_against_pypi must call is_outdated(cached=True); found "
        f"{cached_kwargs or 'no cached= keyword at all'}"
    )
