# URN: test:govern-documentation-obligation:delegate-content-judgement:C001-SMOKE-001-capability-raise-is-failure
# Acceptance: acc:govern-documentation-obligation:C001-SMOKE-001-capability-raise-is-failure
# WMBT: wmbt:govern-documentation-obligation:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — a really-installed capability that raises is FAIL, over real discovery.

Every unit test for this seam hands `judge_documentation` a capability object
directly. That proves the verdict logic and skips the part most likely to break in a
consumer's tree: **entry-point discovery**. `resolve_documentation_capability` reads
installed distribution metadata, and metadata is exactly the thing that is present in
a developer's checkout and absent in a wheel, or the reverse. #1658 is this repository
learning that lesson about a pytest plugin; the same mechanism carries this seam.

So this test installs a real distribution. It writes real `.dist-info` metadata with a
real `entry_points.txt` declaring the `atdd.documentation` group, puts it on
`sys.path`, and lets `importlib.metadata` find it the way it would find anything
`pip install` left behind. The capability it resolves is a real module on disk whose
`check` raises.

That is the shape of the guarantee: a broken capability that is genuinely INSTALLED
must read as FAIL and block, never as an absence that permits. Reading a fault as
"nothing to judge" is the failure this whole verdict vocabulary exists to prevent.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from atdd.coach.documentation import ENTRY_POINT_GROUP, judge_documentation, verdict

_WELL_FORMED = {"impact": "change", "artifacts": [{"action": "create", "path": "docs/x.adoc"}]}
_BOOM = "the asciidoctor toolchain is not on PATH"


@pytest.fixture(scope="module")
def installed_capability(tmp_path_factory) -> Path:
    """A real installed distribution exposing a raising capability."""
    site = tmp_path_factory.mktemp("site")

    (site / "raising_docs_capability.py").write_text(textwrap.dedent(f'''
        class RaisingCapability:
            def check(self, declaration, change_set, repo_root):
                raise RuntimeError({_BOOM!r})
    '''))

    dist = site / "raising_docs_capability-0.1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: raising-docs-capability\nVersion: 0.1.0\n"
    )
    (dist / "entry_points.txt").write_text(
        f"[{ENTRY_POINT_GROUP}]\n"
        "standard = raising_docs_capability:RaisingCapability\n"
    )
    return site


def _run_in_subprocess(site: Path, body: str) -> subprocess.CompletedProcess:
    """Real interpreter, real sys.path, real metadata scan — no in-process patching."""
    script = textwrap.dedent(body)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        env={"PYTHONPATH": f"{site}:src", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=120,
    )


def test_the_entry_point_is_really_discovered(installed_capability: Path) -> None:
    proc = _run_in_subprocess(installed_capability, f'''
        from atdd.coach.documentation import resolve_documentation_capability
        cap = resolve_documentation_capability()
        print(type(cap).__name__ if cap is not None else "NONE")
    ''')
    assert proc.returncode == 0, proc.stderr[-400:]
    assert proc.stdout.strip() == "RaisingCapability", (
        "the installed distribution was not discovered over the entry-point group"
    )


def test_a_really_installed_capability_that_raises_is_fail_and_blocks(installed_capability: Path) -> None:
    proc = _run_in_subprocess(installed_capability, f'''
        from atdd.coach.documentation import judge_documentation, verdict
        out = judge_documentation({_WELL_FORMED!r}, ["docs/x.adoc"], ".")
        print(out.verdict)
        print(verdict.blocks(out.verdict))
        print("|".join(f.message for f in out.findings))
    ''')
    assert proc.returncode == 0, proc.stderr[-400:]
    got_verdict, blocks, messages = proc.stdout.strip().split("\n", 2)

    assert got_verdict == verdict.FAIL, "a fault must not read as an absence"
    assert blocks == "True"
    assert _BOOM in messages, "the raised error must be named in the report, not swallowed"
