# URN: test:govern-lifecycle:govern-lifecycle:C025-SMOKE-001
# Acceptance: acc:govern-lifecycle:C025-SMOKE-001-a-real-init-writes-a-workflow-github-accepts
# WMBT: wmbt:govern-lifecycle:C025
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
# Smoke: true

"""C025-SMOKE-001 — a real init writes a workflow whose permissions resolve correctly.

The unit acceptances drive `_write_workflow` directly. This one runs the real
`ProjectInitializer` against a real `git init` repository on disk and reads the
file back the way a runner does — parse the YAML, resolve permissions per job —
because that is the gap the defect lived in. The generated workflow was always
well-formed YAML; it simply granted a scope its own filter could not work without,
and nothing ever read it back to find out.

No mocks: a real repo, the real initializer, the real file it wrote.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.initializer import ProjectInitializer

pytestmark = [pytest.mark.coach]

FILTER_ACTION = "dorny/paths-filter"


def _real_repo(tmp_path: Path) -> Path:
    root = tmp_path / "consumer"
    root.mkdir()
    for args in (["init", "-q", "-b", "main"],
                 ["config", "user.email", "t@example.com"],
                 ["config", "user.name", "T"]):
        r = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    (root / ".atdd").mkdir()
    (root / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    return root


def _effective(doc: dict, job: str) -> dict:
    """Per-job permissions, resolved as GitHub resolves them (job REPLACES workflow)."""
    body = doc["jobs"][job]
    return (body["permissions"] if "permissions" in body else doc.get("permissions")) or {}


def test_c025_smoke_001_a_real_init_writes_a_workflow_github_accepts(tmp_path):
    root = _real_repo(tmp_path)

    ProjectInitializer(target_dir=root)._write_workflow(repo="owner/repo")
    path = root / ".github" / "workflows" / "atdd-validate.yml"
    assert path.is_file(), "the real initializer wrote no validate workflow"

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict) and doc.get("jobs"), "the written workflow is not usable YAML"

    assert doc.get("permissions") == {"contents": "read", "pull-requests": "read"}, (
        f"workflow-level permissions are {doc.get('permissions')!r}; a repo whose "
        "default token is read-contents-only cannot list a PR's files, so "
        "detect-changes fails and every validate job skips"
    )

    filter_jobs = [
        name for name, body in doc["jobs"].items()
        if any(FILTER_ACTION in str(s.get("uses", "")) for s in (body.get("steps") or []))
    ]
    assert filter_jobs, f"no job in the written workflow runs {FILTER_ACTION}"
    for name in filter_jobs:
        assert _effective(doc, name).get("pull-requests") == "read", (
            f"job {name!r} calls the pull-request files API without the scope to do it"
        )

    # Least privilege is about what a job gets WITHOUT ASKING. `validate-gate`
    # posts a comment and declares `issues: write` for itself, which is the
    # system working: a job that writes says so. What must never happen is a job
    # inheriting write power it never named.
    inherited = doc.get("permissions") or {}
    assert not [k for k, v in inherited.items() if v == "write"], (
        f"the inherited default carries write scopes: {inherited!r}"
    )
    for name, body in doc["jobs"].items():
        if "permissions" in body:
            continue
        writes = [k for k, v in _effective(doc, name).items() if v == "write"]
        assert not writes, (
            f"job {name!r} declares no permissions of its own yet inherits "
            f"write scopes {writes}"
        )
