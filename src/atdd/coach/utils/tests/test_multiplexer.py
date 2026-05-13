"""
Unit tests for ``atdd.coach.utils.multiplexer``.

URN: urn:atdd:test:coach:utils:multiplexer
Issue: #396

Covers the cmux OK-line ref-token parser and ``CmuxBackend.new_surface``,
which previously fed the entire ``OK surface:N pane:M workspace:K`` line
back to ``cmux new-surface --pane <pane_ref>`` and got rejected with
"Invalid pane handle". The fix extracts ``pane:M`` (and ``surface:N``)
tokens by prefix.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from atdd.coach.utils.multiplexer import (
    CmuxBackend,
    MultiplexerError,
    _extract_ref_token,
)


# ─── _extract_ref_token ───────────────────────────────────────────────────────


class TestExtractRefToken:
    def test_extracts_pane_token_from_ok_line(self):
        line = "OK surface:120 pane:33 workspace:17"
        assert _extract_ref_token(line, "pane") == "pane:33"

    def test_extracts_surface_token_from_ok_line(self):
        line = "OK surface:120 pane:33 workspace:17"
        assert _extract_ref_token(line, "surface") == "surface:120"

    def test_extracts_workspace_token_from_ok_line(self):
        line = "OK surface:120 pane:33 workspace:17"
        assert _extract_ref_token(line, "workspace") == "workspace:17"

    def test_returns_first_match_when_multiple(self):
        line = "OK pane:1 pane:2"
        assert _extract_ref_token(line, "pane") == "pane:1"

    def test_handles_trailing_newline(self):
        line = "OK surface:5 pane:7 workspace:3\n"
        assert _extract_ref_token(line, "pane") == "pane:7"

    def test_handles_multiple_lines_returns_first_match(self):
        # Real cmux output is single-line, but be tolerant of stray prefixes.
        stdout = "some banner\nOK surface:5 pane:7 workspace:3\n"
        assert _extract_ref_token(stdout, "surface") == "surface:5"

    def test_returns_empty_when_prefix_absent(self):
        line = "OK workspace:17"
        assert _extract_ref_token(line, "pane") == ""

    def test_returns_empty_on_blank_input(self):
        assert _extract_ref_token("", "pane") == ""
        assert _extract_ref_token("   \n  ", "surface") == ""

    def test_does_not_match_partial_prefix(self):
        # "subpane:9" must NOT match prefix "pane".
        line = "OK subpane:9 workspace:1"
        assert _extract_ref_token(line, "pane") == ""

    def test_does_not_match_prefix_in_middle_of_token(self):
        line = "OK xpane:5 workspace:1"
        assert _extract_ref_token(line, "pane") == ""

    def test_requires_numeric_id(self):
        line = "OK pane:abc workspace:1"
        assert _extract_ref_token(line, "pane") == ""


# ─── CmuxBackend.new_surface integration ──────────────────────────────────────


def _ok(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class TestCmuxNewSurface:
    def test_passes_clean_pane_ref_to_new_surface(self):
        """new_surface must extract `pane:N` from `cmux new-pane` output and
        pass it (not the full OK-line) to `cmux new-surface --pane ...`.
        """
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            if cmd[:2] == ["cmux", "new-pane"]:
                return _ok("OK surface:120 pane:33 workspace:17\n")
            if cmd[:2] == ["cmux", "new-surface"]:
                return _ok("OK surface:121 workspace:17\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(workspace_ref="workspace:17", name="issue-396")

        assert ref == "surface:121"

        new_pane_call = calls[0]
        assert new_pane_call == ["cmux", "new-pane", "--workspace", "workspace:17"]

        new_surface_call = calls[1]
        assert "--pane" in new_surface_call
        pane_arg = new_surface_call[new_surface_call.index("--pane") + 1]
        assert pane_arg == "pane:33", (
            f"expected clean `pane:33`, got {pane_arg!r} "
            "(regression: full OK-line leaked through)"
        )
        assert "--name" in new_surface_call
        assert new_surface_call[new_surface_call.index("--name") + 1] == "issue-396"

    def test_uses_provided_pane_ref_without_creating_new_pane(self):
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            if cmd[:2] == ["cmux", "new-surface"]:
                return _ok("OK surface:99 workspace:1\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(pane_ref="pane:7")

        assert ref == "surface:99"
        assert calls[0][:2] == ["cmux", "new-surface"]
        assert "--pane" in calls[0]
        assert calls[0][calls[0].index("--pane") + 1] == "pane:7"

    def test_seeds_cwd_and_command_into_surface(self):
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            if cmd[:2] == ["cmux", "new-pane"]:
                return _ok("OK surface:1 pane:2 workspace:3\n")
            if cmd[:2] == ["cmux", "new-surface"]:
                return _ok("OK surface:4 workspace:3\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(
                workspace_ref="workspace:3",
                cwd="/tmp/wt",
                command="claude --dangerously-skip-permissions",
            )

        assert ref == "surface:4"
        seed_call = calls[-1]
        assert seed_call[:4] == ["cmux", "send", "--surface", "surface:4"]
        assert seed_call[4] == "cd /tmp/wt && claude --dangerously-skip-permissions\n"

    def test_raises_when_pane_ref_cannot_be_extracted(self):
        backend = CmuxBackend()

        def fake_run(cmd, capture=True):
            if cmd[:2] == ["cmux", "new-pane"]:
                return _ok("ERROR something went wrong\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            with pytest.raises(MultiplexerError, match="pane"):
                backend.new_surface(workspace_ref="workspace:1")

    def test_raises_when_surface_ref_cannot_be_extracted(self):
        backend = CmuxBackend()

        def fake_run(cmd, capture=True):
            if cmd[:2] == ["cmux", "new-pane"]:
                return _ok("OK surface:1 pane:2 workspace:3\n")
            if cmd[:2] == ["cmux", "new-surface"]:
                return _ok("ERROR\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            with pytest.raises(MultiplexerError, match="surface"):
                backend.new_surface(workspace_ref="workspace:3")
