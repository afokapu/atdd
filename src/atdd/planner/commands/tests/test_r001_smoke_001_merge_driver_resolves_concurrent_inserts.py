# URN: test:author-atdd-substrate:author-merge-driver:R001-SMOKE-001-merge-driver-resolves-concurrent-inserts
# Acceptance: acc:author-atdd-substrate:R001-SMOKE-001-merge-driver-resolves-concurrent-inserts
# WMBT: wmbt:author-atdd-substrate:R001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""R001-SMOKE-001 — a real `git merge` of colliding registry inserts resolves clean.

Two branches each insert a distinct edge into the same registry file (a real
would-be conflict). With the re-sort/dedup driver registered via git config +
.gitattributes, the merge produces one canonically-sorted, conflict-marker-free
file.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from atdd.planner.commands.author_registry import insert_relationship

_SRC = Path(__file__).resolve().parents[4]


def _edge(src):
    return {
        "source_ref": src, "type": "enables", "target_ref": "coder.green.t",
        "foundation": "finish_to_start", "constraint": "mandatory",
        "control": "internal", "strength": "critical",
    }


def test_real_git_merge_resolves_via_driver(tmp_path):
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(_SRC),
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
    })

    def git(*args):
        r = subprocess.run(["git", *args], cwd=str(tmp_path), env=env,
                           capture_output=True, text=True, timeout=60)
        return r

    reg = tmp_path / "relationships.yaml"

    git("init", "-b", "main")
    # register the driver + attribute
    git("config", "merge.atdd-registry.driver",
        f"{sys.executable} -m atdd author merge-driver %O %A %B")
    (tmp_path / ".gitattributes").write_text("relationships.yaml merge=atdd-registry\n")

    # base: one edge, committed on main
    insert_relationship(_edge("coder.green.a"), reg)
    git("add", "-A"); git("commit", "-m", "base")

    # branch wa: add edge z
    git("checkout", "-b", "wa")
    insert_relationship(_edge("coder.green.z"), reg)
    git("add", "relationships.yaml"); git("commit", "-m", "z")

    # branch wb from main: add edge b
    git("checkout", "main"); git("checkout", "-b", "wb")
    insert_relationship(_edge("coder.green.b"), reg)
    git("add", "relationships.yaml"); git("commit", "-m", "b")

    # merge wb into wa — the colliding inserts must resolve via the driver
    git("checkout", "wa")
    merge = git("merge", "wb", "-m", "merge")
    assert merge.returncode == 0, f"merge did not resolve cleanly:\n{merge.stdout}\n{merge.stderr}"

    text = reg.read_text()
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    doc = yaml.safe_load(text)
    sources = [e["source_ref"] for e in doc["edges"]]
    assert sources == ["coder.green.a", "coder.green.b", "coder.green.z"], sources
