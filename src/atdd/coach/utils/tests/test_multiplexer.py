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
    def test_reuses_default_surface_from_new_pane(self):
        """Bug #5 (#697): new_surface must REUSE the auto-default surface that
        `cmux new-pane` creates, rather than calling `cmux new-surface` and
        orphaning the default.

        #655: the surface ref is taken straight from the `cmux new-pane`
        output (`OK surface:N pane:M workspace:K`) — NO `list-pane-surfaces`
        round-trip (that call needs --workspace and stranded the pane on
        failure). rename-tab is scoped with --workspace.
        """
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            if cmd[:2] == ["cmux", "new-pane"]:
                return _ok("OK surface:120 pane:33 workspace:17\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(workspace_ref="workspace:17", name="issue-396")

        assert ref == "surface:120", (
            "expected the auto-default surface from new-pane to be reused, "
            f"got {ref!r}"
        )

        new_pane_call = calls[0]
        assert new_pane_call == ["cmux", "new-pane", "--workspace", "workspace:17"]

        # #655: no `list-pane-surfaces` round-trip — the surface ref comes
        # directly from the new-pane output.
        assert not any(c[:2] == ["cmux", "list-pane-surfaces"] for c in calls), (
            "#655 regression: new_surface still calls `cmux list-pane-surfaces` "
            "— the surface ref must be read from the new-pane output instead"
        )

        rename_call = calls[1]
        assert rename_call[:2] == ["cmux", "rename-tab"]
        assert "--surface" in rename_call
        assert rename_call[rename_call.index("--surface") + 1] == "surface:120"
        # #655: rename-tab is scoped to the owning workspace.
        assert "--workspace" in rename_call
        assert rename_call[rename_call.index("--workspace") + 1] == "workspace:17"
        assert "issue-396" in rename_call

        assert not any(c[:2] == ["cmux", "new-surface"] for c in calls), (
            "Bug #5 regression: cmux new-surface was called for a fresh pane "
            "(default surface should have been reused)"
        )

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
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(
                workspace_ref="workspace:3",
                cwd="/tmp/wt",
                command="claude --dangerously-skip-permissions",
            )

        assert ref == "surface:1"
        seed_call = calls[-1]
        assert seed_call[:4] == ["cmux", "send", "--surface", "surface:1"]
        # #655: the seed `cmux send` is scoped to the owning workspace; the
        # seed text is the trailing positional argument.
        assert "--workspace" in seed_call
        assert seed_call[seed_call.index("--workspace") + 1] == "workspace:3"
        assert seed_call[-1] == "cd /tmp/wt && claude --dangerously-skip-permissions\n"

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
                return _ok("OK pane:2 workspace:3\n")
            if cmd[:2] == ["cmux", "list-pane-surfaces"]:
                return _ok("ERROR\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            with pytest.raises(MultiplexerError, match="surface"):
                backend.new_surface(workspace_ref="workspace:3")

    def test_existing_pane_ref_still_adds_new_surface(self):
        """When given an existing pane_ref (e.g. observer cospawn via
        new_surface_in_pane), continue to add a tab via cmux new-surface.
        The Bug #5 fix only applies to fresh-pane creation.
        """
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            if cmd[:2] == ["cmux", "new-surface"]:
                return _ok("OK surface:42 workspace:3\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_surface(pane_ref="pane:7", name="ATDD999-red:obs")

        assert ref == "surface:42"
        assert calls[0][:2] == ["cmux", "new-surface"]
        assert "--pane" in calls[0]
        assert calls[0][calls[0].index("--pane") + 1] == "pane:7"
        assert "--name" in calls[0]
        assert calls[0][calls[0].index("--name") + 1] == "ATDD999-red:obs"
        # Should NOT call new-pane or list-pane-surfaces in this path
        assert not any(c[:2] == ["cmux", "new-pane"] for c in calls)
        assert not any(c[:2] == ["cmux", "list-pane-surfaces"] for c in calls)


class TestPasteText:
    """#702 — paste_text injects multi-line text as one bracketed-paste
    block so an interactive TUI receives it without per-line submit."""

    def test_cmux_paste_text_stages_buffer_then_pastes_to_surface(self):
        backend = CmuxBackend()
        calls: list[list[str]] = []

        def fake_run(cmd, capture=True):
            calls.append(cmd)
            return _ok("")

        prompt = "line one\nline two\nline three"
        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            backend.paste_text("surface:5", prompt)

        # set-buffer stages the (multi-line) text verbatim ...
        assert calls[0][:2] == ["cmux", "set-buffer"]
        assert calls[0][2] == prompt
        # ... then paste-buffer targets the surface.
        assert calls[1][:2] == ["cmux", "paste-buffer"]
        assert "--surface" in calls[1]
        assert calls[1][calls[1].index("--surface") + 1] == "surface:5"

    def test_cmux_paste_text_workspace_ref(self):
        backend = CmuxBackend()
        calls: list[list[str]] = []

        with patch(
            "atdd.coach.utils.multiplexer._run",
            side_effect=lambda cmd, capture=True: calls.append(cmd) or _ok(""),
        ):
            backend.paste_text("workspace:2", "hello")

        assert calls[1][:2] == ["cmux", "paste-buffer"]
        assert "--workspace" in calls[1]

    def test_tmux_paste_text_uses_set_buffer_and_bracketed_paste(self):
        from atdd.coach.utils.multiplexer import TmuxBackend

        backend = TmuxBackend()
        calls: list[list[str]] = []

        with patch(
            "atdd.coach.utils.multiplexer._run",
            side_effect=lambda cmd, capture=True: calls.append(cmd) or _ok(""),
        ):
            backend.paste_text("sess:0", "a\nb")

        assert calls[0][:2] == ["tmux", "set-buffer"]
        assert calls[0][2] == "a\nb"
        assert calls[1][:2] == ["tmux", "paste-buffer"]
        # -p = bracketed paste (one block); -t targets the pane.
        assert "-p" in calls[1]
        assert "-t" in calls[1]
        assert calls[1][calls[1].index("-t") + 1] == "sess:0"

    def test_every_backend_implements_paste_text(self):
        """paste_text is an abstract method — all concrete backends + the
        FakeMultiplexer must implement it (ratchet for #699 Wave-A adapters
        and any future backend)."""
        from atdd.coach.utils.multiplexer import (
            CmuxBackend,
            TmuxBackend,
            ZellijBackend,
            FakeMultiplexer,
        )

        for cls in (CmuxBackend, TmuxBackend, ZellijBackend, FakeMultiplexer):
            assert "paste_text" in cls.__dict__ or any(
                "paste_text" in base.__dict__
                for base in cls.__mro__
                if base.__name__ != "MultiplexerBackend"
            ), f"{cls.__name__} does not implement paste_text"

    def test_fake_multiplexer_records_paste_text(self):
        from atdd.coach.utils.multiplexer import FakeMultiplexer

        fake = FakeMultiplexer()
        fake.paste_text("surface:1", "multi\nline")
        paste_calls = [c for c in fake.calls if c["op"] == "paste_text"]
        assert len(paste_calls) == 1
        assert paste_calls[0]["text"] == "multi\nline"


# ─── CmuxBackend.new_workspace integration ────────────────────────────────────


class TestCmuxNewWorkspace:
    """Regression for the new_workspace ref-parsing bug (#717).

    new_workspace previously parsed cmux stdout with _last_nonempty_line(),
    which returned the whole ``OK workspace:33`` line including the ``OK``
    prefix. Every other CmuxBackend method uses _extract_ref_token() to strip
    it. Feeding ``OK workspace:33`` back to ``cmux --workspace`` is rejected,
    which broke /rename + launch-prompt injection and stalled coach dispatch.
    """

    def test_returns_bare_workspace_ref_not_ok_line(self):
        backend = CmuxBackend()

        def fake_run(cmd, capture=True):
            if cmd[:2] == ["cmux", "new-workspace"]:
                return _ok("OK workspace:33\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            ref = backend.new_workspace(cwd="/tmp/wt", command="claude")

        assert ref == "workspace:33", (
            f"new_workspace must strip the OK prefix; got {ref!r}"
        )

    def test_raises_when_workspace_ref_cannot_be_extracted(self):
        backend = CmuxBackend()

        def fake_run(cmd, capture=True):
            if cmd[:2] == ["cmux", "new-workspace"]:
                return _ok("ERROR could not create workspace\n")
            return _ok("")

        with patch("atdd.coach.utils.multiplexer._run", side_effect=fake_run):
            with pytest.raises(MultiplexerError, match="workspace"):
                backend.new_workspace(cwd="/tmp/wt", command="claude")
