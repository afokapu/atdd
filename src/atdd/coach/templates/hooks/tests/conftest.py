"""Shared fixtures for hook template tests."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def fake_atdd_failing_coder(tmp_path: Path) -> Path:
    """Return a directory containing a fake ``atdd`` binary that exits 1 for 'validate coder'.

    All other subcommands exit 0 so the hook can continue past them.
    The caller must prepend the returned directory to PATH.
    """
    bin_dir = tmp_path / "_fake_atdd_fail_coder"
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text(
        "#!/bin/sh\n"
        "# Fake atdd: fails 'validate coder', passes everything else\n"
        "if [ \"$1\" = 'validate' ] && [ \"$2\" = 'coder' ]; then\n"
        "  echo 'FAKE ATDD: validate coder FAILED' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


@pytest.fixture()
def fake_atdd_failing_coach(tmp_path: Path) -> Path:
    """Return a directory containing a fake ``atdd`` binary that exits 1 for 'validate coach'."""
    bin_dir = tmp_path / "_fake_atdd_fail_coach"
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text(
        "#!/bin/sh\n"
        "# Fake atdd: fails 'validate coach', passes everything else\n"
        "if [ \"$1\" = 'validate' ] && [ \"$2\" = 'coach' ]; then\n"
        "  echo 'FAKE ATDD: validate coach FAILED' >&2\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


@pytest.fixture()
def fake_atdd_passing(tmp_path: Path) -> Path:
    """Return a directory containing a fake ``atdd`` binary that always exits 0."""
    bin_dir = tmp_path / "_fake_atdd_pass"
    bin_dir.mkdir()
    script = bin_dir / "atdd"
    script.write_text(
        "#!/bin/sh\n"
        "# Fake atdd: always passes\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir
