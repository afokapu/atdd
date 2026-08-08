"""Tests for src/atdd/version_check.py — auto_upgrade PEP 668 fallback +
PyPI propagation-window cache-bust.

Six-cell matrix for ``auto_upgrade``:
  1. Clean happy path (pip succeeds + verify passes).
  2. PEP 668 first-attempt refusal + retry-with-flag success + verify pass.
  3. Stale-cache: returncode=0 + verify fails on attempt 1 → pinned retry → verify passes.
  4. PEP 668 + stale-cache combined (both retry dimensions on each attempt).
  5. Pinned retry also fails → False.
  6. ``expected=None`` (PyPI unreachable) → returncode alone decides.

Plus a dedicated ``_verify_installed_version`` timeout test.
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.version_check import (
    _is_pep668_error,
    _run_with_pep668_retry,
    _verify_installed_version,
    auto_upgrade,
    upgrade_command,
)


class TestIsPep668Error:
    def test_detects_homebrew_message(self):
        msg = "error: externally-managed-environment\n"
        assert _is_pep668_error(msg) is True

    def test_detects_debian_message(self):
        msg = "error: externally-managed\n"
        assert _is_pep668_error(msg) is True

    def test_returns_false_for_unrelated_error(self):
        msg = "ERROR: Could not find a version that satisfies the requirement atdd"
        assert _is_pep668_error(msg) is False

    def test_returns_false_for_empty(self):
        assert _is_pep668_error("") is False


class TestVerifyInstalledVersion:
    def test_returns_true_when_expected_is_none(self):
        # No target → no check.
        assert _verify_installed_version(None) is True

    def test_returns_true_when_expected_is_empty(self):
        assert _verify_installed_version("") is True

    def test_returns_true_on_subprocess_match(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.2\n")
            assert _verify_installed_version("3.7.2") is True

    def test_returns_false_on_subprocess_mismatch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.1\n")
            assert _verify_installed_version("3.7.2") is False

    def test_returns_false_on_subprocess_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert _verify_installed_version("3.7.2") is False

    def test_returns_false_on_subprocess_timeout(self):
        # TimeoutExpired must not crash auto_upgrade — it must surface as False.
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
            assert _verify_installed_version("3.7.2") is False

    def test_passes_timeout_kwarg(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3.7.2\n")
            _verify_installed_version("3.7.2")
            assert mock_run.call_args.kwargs.get("timeout") == 10


class TestRunWithPep668Retry:
    def test_success_first_try(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is True
            assert mock_run.call_count == 1

    def test_retries_on_pep668(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
            ]
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is True
            assert mock_run.call_count == 2
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]

    def test_no_retry_on_unrelated_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="other error")
            ok, _stderr = _run_with_pep668_retry(["pip", "install", "x"])
            assert ok is False
            assert mock_run.call_count == 1


class TestAutoUpgrade:
    """Six-cell matrix for the cache-bust + verify behavior, on the pip branch."""

    @pytest.fixture(autouse=True)
    def _detected_as_pip(self):
        """Pin the detected install method for this whole matrix.

        These cells exercise the pip branch. Without the pin the result depends
        on how the machine running the suite installed atdd — on a pipx install
        ``auto_upgrade()`` now correctly takes the pipx branch and never touches
        pip at all (#1671).
        """
        with patch("atdd.version_check.detect_install_method", return_value="pip"):
            yield

    def test_cell1_clean_happy_path(self):
        """returncode=0 on attempt 1 + verify passes → True, single pip call."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade()[0] is True
            assert mock_run.call_count == 1
            # --no-cache-dir always present.
            assert "--no-cache-dir" in mock_run.call_args_list[0].args[0]

    def test_cell2_pep668_retry_first_attempt(self):
        """PEP 668 refusal → --break-system-packages retry → verify passes."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
            ]
            assert auto_upgrade()[0] is True
            assert mock_run.call_count == 2
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]
            # No pinned attempt fired.
            for call in mock_run.call_args_list:
                assert "atdd==3.7.2" not in call.args[0]

    def test_cell3_stale_cache_triggers_pinned_retry(self):
        """returncode=0 but verify fails → pinned attempt → verify passes."""
        verify_results = [False, True]  # attempt 1 verify fails; attempt 2 verify passes
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade()[0] is True
            # Two pip calls: name-only, then pinned.
            assert mock_run.call_count == 2
            assert "atdd" in mock_run.call_args_list[0].args[0]
            assert "atdd==3.7.2" in mock_run.call_args_list[1].args[0]

    def test_cell4_pep668_plus_stale_cache_combined(self):
        """Both retry dimensions on attempt 1, then pinned attempt also clean."""
        verify_results = [False, True]
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Attempt 1: PEP 668 refusal then BSP success (verify still fails).
                MagicMock(returncode=1, stderr="error: externally-managed-environment"),
                MagicMock(returncode=0, stderr=""),
                # Attempt 2 (pinned): clean.
                MagicMock(returncode=0, stderr=""),
            ]
            assert auto_upgrade()[0] is True
            assert mock_run.call_count == 3
            assert "--break-system-packages" in mock_run.call_args_list[1].args[0]
            assert "atdd==3.7.2" in mock_run.call_args_list[2].args[0]

    def test_cell5_pinned_retry_also_fails(self):
        """First attempt verify-fails, pinned attempt also verify-fails → False."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=[False, False]), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade()[0] is False
            assert mock_run.call_count == 2

    def test_cell5b_pinned_attempt_pip_failure(self):
        """First attempt verify-fails, pinned attempt pip-fails (e.g., 404) → False."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=[False]), \
             patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stderr=""),
                MagicMock(returncode=1, stderr="ERROR: No matching distribution"),
            ]
            assert auto_upgrade()[0] is False
            assert mock_run.call_count == 2

    def test_cell6_expected_none_returncode_decides(self):
        """PyPI unreachable (target=None) → returncode alone decides; no verify-fail path."""
        with patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade()[0] is True
            assert mock_run.call_count == 1
            # No pinned attempt — we have nothing to pin to.
            for call in mock_run.call_args_list:
                assert not any("atdd==" in str(arg) for arg in call.args[0])

    def test_cell6b_expected_none_pip_fails(self):
        """target=None and pip fails (no PEP 668) → False, no pinned retry."""
        with patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="ERROR: Could not find a version that satisfies the requirement atdd",
            )
            assert auto_upgrade()[0] is False
            assert mock_run.call_count == 1

    def test_returns_false_on_subprocess_exception(self):
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("subprocess.run", side_effect=OSError("boom")):
            assert auto_upgrade()[0] is False

    def test_no_cache_dir_always_present(self):
        """Regression: --no-cache-dir on every pip invocation."""
        verify_results = [False, True]
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            auto_upgrade()
            for call in mock_run.call_args_list:
                assert "--no-cache-dir" in call.args[0], \
                    f"--no-cache-dir missing from {call.args[0]}"

    def test_lived_3_7_1_to_3_7_2_regression(self):
        """Regression test reproducing the lived case (issue #455).

        PyPI's JSON API reports 3.7.2 but pip's resolver serves stale 3.7.1
        on the name-only attempt (returncode=0, "Requirement already satisfied").
        Verify catches the mismatch; pinned retry installs 3.7.2.
        """
        verify_results = [False, True]  # name-only got 3.7.1; pinned got 3.7.2
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version",
                   side_effect=verify_results) as mock_verify, \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stderr="",
                stdout="Requirement already satisfied: atdd 3.7.1",
            )
            assert auto_upgrade()[0] is True
            # Verify was called with "3.7.2" both times.
            for call in mock_verify.call_args_list:
                assert call.args[0] == "3.7.2"
            # Pinned attempt fired with the correct version.
            assert "atdd==3.7.2" in mock_run.call_args_list[1].args[0]


# ---------------------------------------------------------------------------
# #1671 — the command advised must be the command run.
#
# `upgrade_command()` answers "how is this installed"; `auto_upgrade()` answers
# "how do I upgrade it". They were two independent code paths written to agree
# and never checked against each other, so the advice said `pipx upgrade atdd`
# while the execution always shelled `sys.executable -m pip` — and a pipx venv
# ships no pip, which made the upgrade structurally unreachable on the standard
# install method rather than merely flaky.
#
# The guard cannot be literal string equality: for pip the advice is the short
# human form (`pip install --upgrade atdd`) while the execution deliberately
# adds `--no-cache-dir` and runs `sys.executable -m pip`. What must not drift is
# the ENGINE — pipx / pip / git — so that is what is pinned here.
# ---------------------------------------------------------------------------


def _engine_of_advice(advice: str) -> str:
    """The tool `upgrade_command()` names, taken from its first token."""
    return advice.split()[0]


def _engine_of_argv(argv: list) -> str:
    """The tool an executed argv actually invokes."""
    if len(argv) >= 3 and argv[1] == "-m":
        return argv[2]          # [python, -m, pip, ...] → "pip"
    return Path(argv[0]).name   # [/usr/bin/pipx, upgrade, atdd] → "pipx"


class TestAdviceMatchesExecution:
    """#1671 regression guard. No network, no real install."""

    def test_pipx_install_runs_pipx_and_never_pip(self):
        """The defect itself: a pipx-detected install must not shell pip."""
        with patch("atdd.version_check.detect_install_method", return_value="pipx"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("shutil.which", return_value="/opt/homebrew/bin/pipx"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            ok, detail = auto_upgrade()

        assert ok is True, detail
        argv = mock_run.call_args_list[0].args[0]
        assert argv[1:3] == ["upgrade", "atdd"]
        assert _engine_of_argv(argv) == "pipx"
        # The exact shape of the bug: no invocation may reach for pip.
        for call in mock_run.call_args_list:
            assert "pip" not in call.args[0], f"pip invoked under pipx: {call.args[0]}"

    def test_engine_advised_equals_engine_executed(self):
        """Per install method, advice and execution must name the same tool."""
        for method, engine in (("pipx", "pipx"), ("pip", "pip")):
            with patch("atdd.version_check.detect_install_method", return_value=method), \
                 patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
                 patch("atdd.version_check._verify_installed_version", return_value=True), \
                 patch("shutil.which", return_value=f"/usr/local/bin/{engine}"), \
                 patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
                advice = upgrade_command()
                auto_upgrade()

            argv = mock_run.call_args_list[0].args[0]
            assert _engine_of_advice(advice) == engine
            assert _engine_of_argv(argv) == engine, (
                f"{method}: advised {advice!r} but executed {argv!r}"
            )

    def test_pipx_upgrade_busts_the_cache(self):
        """The cache-bust must survive the engine switch.

        Bare `pipx upgrade atdd` reported "already at latest version 4.37.0"
        while 4.37.1 was live on both PyPI surfaces; the same command with
        --pip-args="--no-cache-dir" upgraded. The pip branch has always passed
        --no-cache-dir for this reason, and dispatching to pipx must not drop it.
        """
        with patch("atdd.version_check.detect_install_method", return_value="pipx"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.37.1"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("shutil.which", return_value="/opt/homebrew/bin/pipx"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")
            auto_upgrade()

        argv = mock_run.call_args_list[0].args[0]
        assert any("--no-cache-dir" in a for a in argv), \
            f"pipx invocation drops the cache-bust: {argv}"

    def test_pipx_claiming_already_latest_is_not_accepted(self):
        """pipx exiting 0 while the version did not move must not read as success.

        This is the stale-resolution case: returncode 0, reassuring stdout, and
        nothing installed. Verify is what catches it.
        """
        with patch("atdd.version_check.detect_install_method", return_value="pipx"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.37.1"), \
             patch("atdd.version_check._verify_installed_version", return_value=False), \
             patch("shutil.which", return_value="/opt/homebrew/bin/pipx"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stderr="", stdout="already at latest version 4.37.0",
            )
            ok, detail = auto_upgrade()

        assert ok is False
        assert "4.37.1" in detail

    def test_editable_install_is_reported_not_performed(self):
        """An editable install names the command and mutates nothing."""
        direct_url = {"url": "file:///Users/dev/atdd", "dir_info": {"editable": True}}
        with patch("atdd.version_check.detect_install_method", return_value="editable"), \
             patch("atdd.version_check._read_direct_url", return_value=direct_url), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
             patch("subprocess.run") as mock_run:
            ok, detail = auto_upgrade()

        assert ok is False
        assert mock_run.call_count == 0, "an editable install must not be upgraded for the operator"
        assert "git -C /Users/dev/atdd pull" in detail


class TestFailureDetailReachesCaller:
    """#1671 — the reason must survive the return boundary."""

    def test_pipx_failure_carries_stderr(self):
        with patch("atdd.version_check.detect_install_method", return_value="pipx"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
             patch("shutil.which", return_value="/opt/homebrew/bin/pipx"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="No module named pip", stdout="",
            )
            ok, detail = auto_upgrade()

        assert ok is False
        assert "No module named pip" in detail

    def test_missing_pipx_on_path_says_so(self):
        with patch("atdd.version_check.detect_install_method", return_value="pipx"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
             patch("shutil.which", return_value=None), \
             patch("subprocess.run") as mock_run:
            ok, detail = auto_upgrade()

        assert ok is False
        assert mock_run.call_count == 0
        assert "pipx" in detail and "PATH" in detail

    def test_pip_failure_carries_stderr(self):
        with patch("atdd.version_check.detect_install_method", return_value="pip"), \
             patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stderr="ERROR: No matching distribution found for atdd",
            )
            ok, detail = auto_upgrade()

        assert ok is False
        assert "No matching distribution" in detail

    def test_exception_detail_is_returned_not_swallowed(self):
        """The suppression this replaced returned a bare False (#1671, #1680)."""
        with patch("atdd.version_check.detect_install_method", return_value="pip"), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.34.0"), \
             patch("subprocess.run", side_effect=OSError("boom")):
            ok, detail = auto_upgrade()

        assert ok is False
        assert "boom" in detail


# ---------------------------------------------------------------------------
# #1449 — the push gate must judge the INSTALLED CLI, never the working tree.
#
# `atdd/__init__.py` resolves `importlib.metadata.version("atdd")`. In a source
# checkout that resolves against `src/atdd.egg-info/PKG-INFO` — a GITIGNORED
# build artifact any `pip install -e .` (CI does this) leaves behind, frozen at
# whatever version the tree was last built at. The pre-push hook exports
# PYTHONPATH=src, so the gate imported that ghost and blocked developers whose
# installed CLI was perfectly current.
#
# The gate MEANS "is the CLI you are running outdated?" — so it must ask the
# `atdd` executable on PATH, and fail OPEN when that is unknowable.
# ---------------------------------------------------------------------------

from contextlib import contextmanager

from atdd.version_check import is_outdated, _gate_main


@contextmanager
def _gate_env(*, tree, cli, pypi, which="/Users/dev/.local/bin/atdd"):
    """Pin the three versions the gate could possibly consult.

    ``tree``  — the ghost: what `from atdd import __version__` yields in a
                source checkout (a stale egg-info, or 0.0.0 on a clean tree).
    ``cli``   — what the `atdd` executable on PATH actually reports.
    ``pypi``  — the published latest.
    """
    run = MagicMock(return_value=subprocess.CompletedProcess(
        args=[], returncode=0, stdout=f"atdd {cli}\n", stderr=""))
    with patch("atdd.version_check.__version__", tree), \
         patch("shutil.which", return_value=which), \
         patch("subprocess.run", run), \
         patch("atdd.version_check._fetch_latest_version", return_value=pypi):
        yield run


class TestGateJudgesTheInstalledCli:
    """#1449 acceptance (i) + (ii): the gate follows the CLI, not the tree."""

    def test_stale_egg_info_does_not_block_a_current_cli(self):
        """(i) Ghost tree 3.117.0 + installed CLI 4.5.2 (== latest) → NOT blocked.

        This is the lived bug: a gitignored egg-info blocked every push.
        """
        with _gate_env(tree="3.117.0", cli="4.5.2", pypi="4.5.2"):
            outdated, current, latest = is_outdated()
        assert not outdated, "a stale egg-info must never block a current CLI"
        assert current == "4.5.2", "the gate must report the INSTALLED version"

    def test_stale_egg_info_does_not_exit_the_push_gate(self):
        """(i) end-to-end through _gate_main: the hook must exit 0."""
        with _gate_env(tree="3.117.0", cli="4.5.2", pypi="4.5.2"):
            _gate_main()  # must not raise SystemExit

    def test_genuinely_outdated_cli_is_blocked(self):
        """(ii) Installed CLI 4.0.0 < latest 4.5.2 → blocked, even though the
        tree's ghost (4.5.2) looks current. The gate must not be fooled either way.
        """
        with _gate_env(tree="4.5.2", cli="4.0.0", pypi="4.5.2"):
            outdated, current, latest = is_outdated()
        assert outdated, "an outdated installed CLI must be blocked"
        assert current == "4.0.0"

    def test_genuinely_outdated_cli_exits_1(self):
        """(ii) end-to-end: the push gate exits 1 for a stale CLI."""
        with _gate_env(tree="4.5.2", cli="4.0.0", pypi="4.5.2"):
            with pytest.raises(SystemExit) as exc:
                _gate_main()
        assert exc.value.code == 1


class TestGateFailsOpenOnUnknowableVersion:
    """#1449 scope (b): never block on garbage."""

    def test_no_atdd_on_path_fails_open(self):
        with _gate_env(tree="3.117.0", cli="4.5.2", pypi="4.5.2", which=None):
            outdated, _, _ = is_outdated()
        assert not outdated, "unresolvable CLI must fail OPEN, not block"

    def test_dev_install_0_0_0_fails_open(self):
        with _gate_env(tree="0.0.0", cli="0.0.0", pypi="4.5.2"):
            outdated, _, _ = is_outdated()
        assert not outdated, "a 0.0.0 dev CLI must fail OPEN"

    def test_unparseable_cli_output_fails_open(self):
        from atdd.version_check import installed_cli_version
        run = MagicMock(return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="who knows\n", stderr=""))
        with patch("shutil.which", return_value="/usr/bin/atdd"), \
             patch("subprocess.run", run), \
             patch("atdd.version_check._fetch_latest_version", return_value="4.5.2"):
            assert installed_cli_version() is None
            outdated, _, _ = is_outdated()
        assert not outdated


class TestInstalledCliVersionResolution:
    """The resolver itself: it must be immune to the working tree."""

    def test_reads_the_version_from_the_executable_on_path(self):
        from atdd.version_check import installed_cli_version
        run = MagicMock(return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="atdd 4.5.2\n", stderr=""))
        with patch("shutil.which", return_value="/Users/dev/.local/bin/atdd"), \
             patch("subprocess.run", run):
            assert installed_cli_version() == "4.5.2"
        assert run.call_args.args[0][0] == "/Users/dev/.local/bin/atdd"

    def test_scrubs_pythonpath_so_the_source_tree_cannot_leak_in(self):
        """The pre-push hook exports PYTHONPATH=src. If that leaked into the
        subprocess, a pip-generated shim without `-E` would import the tree's
        atdd and re-resolve the very egg-info ghost we are escaping.
        """
        from atdd.version_check import installed_cli_version
        run = MagicMock(return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="atdd 4.5.2\n", stderr=""))
        with patch("shutil.which", return_value="/usr/bin/atdd"), \
             patch("subprocess.run", run), \
             patch.dict("os.environ", {"PYTHONPATH": "/repo/src"}):
            installed_cli_version()
        assert "PYTHONPATH" not in run.call_args.kwargs["env"]

    def test_subprocess_failure_returns_none(self):
        from atdd.version_check import installed_cli_version
        run = MagicMock(return_value=subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom"))
        with patch("shutil.which", return_value="/usr/bin/atdd"), \
             patch("subprocess.run", run):
            assert installed_cli_version() is None

    def test_timeout_returns_none(self):
        from atdd.version_check import installed_cli_version
        with patch("shutil.which", return_value="/usr/bin/atdd"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("atdd", 10)):
            assert installed_cli_version() is None
