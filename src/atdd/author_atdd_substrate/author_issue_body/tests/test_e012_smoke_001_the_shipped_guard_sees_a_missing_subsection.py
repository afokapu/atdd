# URN: test:author-atdd-substrate:author-issue-body:E012-SMOKE-001-the-shipped-guard-sees-a-missing-subsection
# Acceptance: acc:author-atdd-substrate:E012-SMOKE-001-the-shipped-guard-sees-a-missing-subsection
# WMBT: wmbt:author-atdd-substrate:E012
# Phase: SMOKE
# Layer: integration
"""E012-SMOKE-001 — the derived constants and the new arm, over the SHIPPED artifacts.

Every unit acceptance under E012 drives temp schema/template pairs. That is the right
way to prove a MECHANISM, and it says nothing about the corpus this repo actually
ships: the fix could be correct in the abstract and wrong here. This is the only
acceptance that reads the live `issue.schema.json`, the live
`PARENT-ISSUE-TEMPLATE.md`, and the real guard as pytest collects it.

THE SECOND TEST IS THE DEFECT ITSELF, RE-RUN. Before #1978 the exact probe below —
a subsection the schema requires and the template does not show — passed both C011
tests in 0.15s. Running the real guard in a subprocess over a mutated copy of the
checkout is the only way to assert that from inside the suite: the in-process guard
reads module-level paths resolved at import, so a copy on disk is what a fresh
interpreter has to be pointed at.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from ._helpers import (
    ISSUE_SCHEMA_PATH,
    REPO_ROOT,
    TEMPLATE_PATH,
    optional_sections,
    required_subsections,
    template_missing_required_subsections,
)

_GUARD = "src/atdd/author_atdd_substrate/author_issue_body/tests/test_c011_unit_001_tri_directional_drift_guard.py"


@pytest.mark.smoke
def test_the_shipped_pair_reports_no_missing_subsection():
    """The arm lands green over the real artifacts — no backlog to clear."""
    missing = template_missing_required_subsections()
    assert missing == [], (
        f"schema-required subsections absent from the shipped "
        f"PARENT-ISSUE-TEMPLATE.md: {missing}"
    )


@pytest.mark.smoke
def test_the_derived_sets_match_the_shipped_artifacts():
    """No section heading is read from a literal; both sets follow the real files."""
    schema = json.loads(ISSUE_SCHEMA_PATH.read_text(encoding="utf-8"))
    required = set(schema.get("required", []))

    assert set(required_subsections()) == {h for h in required if h.startswith("### ")}

    template_h2 = {
        line.rstrip()
        for line in TEMPLATE_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ") and not line.startswith("### ")
    }
    assert set(optional_sections()) == {h for h in template_h2 if h not in required}


@pytest.mark.smoke
def test_the_real_guard_fails_when_the_template_hides_a_required_subsection(tmp_path):
    """The original defect, re-run against the real guard in a real interpreter.

    A mutated COPY of the checkout, so the shipped tree is never written to: the schema
    requires a subsection the template does not show, and the guard must now refuse it.
    """
    work = tmp_path / "checkout"
    for rel in ("src", "pyproject.toml"):
        src = REPO_ROOT / rel
        dst = work / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)

    schema_path = work / ISSUE_SCHEMA_PATH.relative_to(REPO_ROOT)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["required"].append("### Bogus Subsection")
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")

    # The generator must emit it too, or the guard fails on the generator arm instead
    # of the template arm — a pass for the wrong reason is what this test exists against.
    gen = work / "src/atdd/planner/commands/author_issue.py"
    text = gen.read_text(encoding="utf-8")
    anchor = '        "### Conceptual Model\\n\\n"'
    assert anchor in text, "generator anchor moved; re-point this probe"
    gen.write_text(
        text.replace(
            anchor,
            '        "### Bogus Subsection\\n\\nemitted, absent from the template\\n\\n"\n' + anchor,
            1,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _GUARD, "-q", "-p", "no:cacheprovider"],
        cwd=str(work), capture_output=True, text=True,
        env={"PYTHONPATH": str(work / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode != 0, (
        "the real C011 guard PASSED with a schema-required subsection missing from the "
        "template — the #1978 defect is back.\n"
        f"stdout:\n{proc.stdout[-2000:]}"
    )
    assert "Bogus Subsection" in proc.stdout, (
        "the guard failed, but not for the missing subsection — it must name it.\n"
        f"stdout:\n{proc.stdout[-2000:]}"
    )
