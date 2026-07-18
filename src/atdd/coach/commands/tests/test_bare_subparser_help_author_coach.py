# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1325 item 1 — bare `atdd author -h` / `atdd coach -h` must render the
subcommand's own help, not error `unrecognized arguments: -h`.

Root cause: the `author` and `coach` subparsers are registered with
`add_help=False` and a single `nargs=argparse.REMAINDER` positional that forwards
argv to a sub-CLI. argparse's REMAINDER does not capture a *leading* `-h`/`--help`
— it bubbles back to the top parser, which reports `unrecognized arguments: -h`.
The fix intercepts `author`/`coach` argv before `parse_args` (the same way `plan`
and `enforce` already are), so a leading `-h` reaches the sub-CLI's own help.

Failing-first: before the fix, bare `-h`/`--help` exits 2 with
`unrecognized arguments`; after, it exits 0 with the sub-CLI's own help. The
kind-first forms (`author issue -h`, `coach status -h`) already worked and must
keep working — they are pinned here so the fix cannot regress them.

HERMETIC (feedback_transition_tests_must_be_hermetic): temp cwd + temp
ATDD_CONTROL_ROOT. argparse help is emitted before any store/gh/git access, so
nothing real is read or mutated.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so no real store/manifest is touched."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _run_main(argv, capsys):
    """Invoke cli.main() with a patched argv; return (exit_code, stdout, stderr).

    argparse `-h` prints help then raises SystemExit(0); a parse error raises
    SystemExit(2). A plain return (no SystemExit) is reported as its return code.
    """
    import atdd.cli as cli

    monkey_argv = list(argv)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("sys.argv", monkey_argv)
        try:
            rc = cli.main()
        except SystemExit as exc:  # argparse help/errors exit through here
            rc = exc.code if exc.code is not None else 0
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# =============================================================================
# The bug: bare `-h`/`--help` on the forwarding subparsers
# =============================================================================
@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_bare_author_help_renders_author_help(flag, hermetic, capsys):
    rc, out, err = _run_main(["atdd", "author", flag], capsys)
    assert rc == 0, f"`atdd author {flag}` must exit 0, got {rc}\nSTDERR:\n{err}"
    combined = out + err
    assert "unrecognized arguments" not in combined, combined
    # It must be the AUTHOR surface, not the top-level usage.
    assert "atdd author" in combined
    assert "Author schema-valid ATDD substrate artifacts" in combined


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_bare_coach_help_renders_coach_help(flag, hermetic, capsys):
    rc, out, err = _run_main(["atdd", "coach", flag], capsys)
    assert rc == 0, f"`atdd coach {flag}` must exit 0, got {rc}\nSTDERR:\n{err}"
    combined = out + err
    assert "unrecognized arguments" not in combined, combined
    assert "atdd coach" in combined


# =============================================================================
# Regression guard: kind-first forwarding must keep working
# =============================================================================
def test_author_kind_first_help_still_works(hermetic, capsys):
    rc, out, err = _run_main(["atdd", "author", "issue", "-h"], capsys)
    assert rc == 0, (out + err)
    assert "unrecognized arguments" not in (out + err)
    assert "issue" in (out + err)


def test_coach_verb_first_help_still_works(hermetic, capsys):
    rc, out, err = _run_main(["atdd", "coach", "enter", "-h"], capsys)
    assert rc == 0, (out + err)
    assert "unrecognized arguments" not in (out + err)
