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
from unittest.mock import MagicMock, patch

import pytest
import yaml

from atdd.version_check import (
    _is_pep668_error,
    _run_with_pep668_retry,
    _verify_installed_version,
    auto_upgrade,
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
    """Six-cell matrix for the cache-bust + verify behavior."""

    def test_cell1_clean_happy_path(self):
        """returncode=0 on attempt 1 + verify passes → True, single pip call."""
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("atdd.version_check._verify_installed_version", return_value=True), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
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
            assert auto_upgrade() is True
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
            assert auto_upgrade() is True
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
            assert auto_upgrade() is True
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
            assert auto_upgrade() is False
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
            assert auto_upgrade() is False
            assert mock_run.call_count == 2

    def test_cell6_expected_none_returncode_decides(self):
        """PyPI unreachable (target=None) → returncode alone decides; no verify-fail path."""
        with patch("atdd.version_check._fetch_latest_version", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            assert auto_upgrade() is True
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
            assert auto_upgrade() is False
            assert mock_run.call_count == 1

    def test_returns_false_on_subprocess_exception(self):
        with patch("atdd.version_check._fetch_latest_version", return_value="3.7.2"), \
             patch("subprocess.run", side_effect=OSError("boom")):
            assert auto_upgrade() is False

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
            assert auto_upgrade() is True
            # Verify was called with "3.7.2" both times.
            for call in mock_verify.call_args_list:
                assert call.args[0] == "3.7.2"
            # Pinned attempt fired with the correct version.
            assert "atdd==3.7.2" in mock_run.call_args_list[1].args[0]


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


# ---------------------------------------------------------------------------
# #1527: update_toolkit_version must not round-trip the document.
#
# The bug was a whole-document PyYAML load/dump to change one scalar, which
# silently destroyed every comment in .atdd/config.yaml. These pin the
# surgical write: if the round-trip is ever reintroduced, the comment
# assertions below fail.
# ---------------------------------------------------------------------------

# A config carrying the three comment shapes the real file uses: a block
# comment above a mapping, an inline trailing comment, and a comment that is
# the last line of the file.
_COMMENTED_CONFIG = """\
version: '1.0'
# Theme taxonomy (#1317). get_theme_map MERGES and cannot remove digits, so
# digits 5-9 keep the game-domain defaults but are unused here.
themes:
  '0': commons
  '5': player   # unused, do not delete
toolkit:
  last_version: 1.0.0
github:
  repo: afokapu/atdd
# Trailing note that must survive the bump.
"""


def _comment_lines(text: str) -> list:
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]


class TestUpdateToolkitVersionPreservesComments:
    """#1527 — the version bump is a one-line write, not a re-serialisation."""

    def _bump(self, tmp_path, source: str, version: str = "4.12.4"):
        from atdd import version_check
        config = tmp_path / "config.yaml"
        config.write_text(source, encoding="utf-8")
        with patch.object(version_check, "__version__", version):
            assert version_check.update_toolkit_version(config) is True
        return config.read_text(encoding="utf-8")

    def test_every_comment_survives_the_bump(self, tmp_path):
        """The regression pin. A round-trip through PyYAML drops all of these."""
        result = self._bump(tmp_path, _COMMENTED_CONFIG)
        assert _comment_lines(result) == _comment_lines(_COMMENTED_CONFIG)

    def test_last_version_is_actually_updated(self, tmp_path):
        result = self._bump(tmp_path, _COMMENTED_CONFIG)
        assert yaml.safe_load(result)["toolkit"]["last_version"] == "4.12.4"

    def test_only_the_last_version_line_changes(self, tmp_path):
        """Key order, quoting and indentation stay byte-identical."""
        result = self._bump(tmp_path, _COMMENTED_CONFIG)
        before = _COMMENTED_CONFIG.splitlines()
        after = result.splitlines()
        assert len(before) == len(after)
        differing = [i for i, (b, a) in enumerate(zip(before, after)) if b != a]
        assert differing == [before.index("  last_version: 1.0.0")]
        assert after[differing[0]] == "  last_version: 4.12.4"

    def test_inline_comment_on_the_bumped_line_survives(self, tmp_path):
        source = "toolkit:\n  last_version: 1.0.0  # stamped by atdd sync\n"
        result = self._bump(tmp_path, source)
        assert result == "toolkit:\n  last_version: 4.12.4  # stamped by atdd sync\n"

    def test_key_absent_from_existing_toolkit_block(self, tmp_path):
        source = "# lead\ntoolkit:\n  other: keep\nafter: 1\n"
        result = self._bump(tmp_path, source)
        assert yaml.safe_load(result)["toolkit"] == {"last_version": "4.12.4", "other": "keep"}
        assert _comment_lines(result) == ["# lead"]

    def test_toolkit_block_absent_entirely(self, tmp_path):
        source = "# lead\nversion: '1.0'\n"
        result = self._bump(tmp_path, source)
        assert yaml.safe_load(result)["toolkit"] == {"last_version": "4.12.4"}
        assert _comment_lines(result) == ["# lead"]

    def test_missing_file_returns_false(self, tmp_path):
        from atdd.version_check import update_toolkit_version
        assert update_toolkit_version(tmp_path / "absent.yaml") is False

    def test_nested_last_version_is_not_mistaken_for_the_real_key(self, tmp_path):
        """Only a direct child of `toolkit:` is the version stamp."""
        source = "toolkit:\n  nested:\n    last_version: 0.0.1\n  last_version: 1.0.0\n"
        result = self._bump(tmp_path, source)
        parsed = yaml.safe_load(result)
        assert parsed["toolkit"]["last_version"] == "4.12.4"
        assert parsed["toolkit"]["nested"]["last_version"] == "0.0.1"

    def test_toolkit_key_nested_under_another_block_is_not_matched(self, tmp_path):
        """`code.toolkit` is a path, not the version block — the real config has both."""
        source = "code:\n  toolkit: src/atdd\ntoolkit:\n  last_version: 1.0.0\n"
        result = self._bump(tmp_path, source)
        assert yaml.safe_load(result)["code"]["toolkit"] == "src/atdd"
        assert yaml.safe_load(result)["toolkit"]["last_version"] == "4.12.4"

    def test_unwritable_shape_is_refused_rather_than_corrupted(self, tmp_path):
        """A flow-style block cannot be edited by line; refuse, do not duplicate the key."""
        from atdd import version_check
        source = "toolkit: {}\n"
        config = tmp_path / "config.yaml"
        config.write_text(source, encoding="utf-8")
        with patch.object(version_check, "__version__", "4.12.4"):
            assert version_check.update_toolkit_version(config) is False
        assert config.read_text(encoding="utf-8") == source
