# URN: test:govern-lifecycle:govern-lifecycle:C026-UNIT-001
# Acceptance: acc:govern-lifecycle:C026-UNIT-001-a-toolkit-self-validator-declines-to-run-elsewhere
# WMBT: wmbt:govern-lifecycle:C026
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""C026-UNIT-001 — a validator that reads the toolkit's own tree must not run elsewhere.

Validators ship inside the installed package and run against whatever repo invokes
them. `test_r005_smoke_001_real_validate_coach_enforces_projection_only` reaches for

    <find_repo_root()>/src/atdd/coach/validators/test_phase_label_projection_only.py

which exists only in the atdd source checkout. In a consumer repo it fails:

    ERROR: file or directory not found:
      src/atdd/coach/validators/test_phase_label_projection_only.py

That was the single red test in a 1043-validator consumer run, and because
`validate-gate` fans in `validate-coach`, it makes the gate permanently red in
every consumer repo with nothing the consumer can do about it.

It is not that the validator had no guard. It had one, and the guard is the defect:

    for rel in ("src", ".github"):
        if not (REPO_ROOT / rel).exists():
            pytest.skip(f"{rel}/ absent — not a toolkit checkout")

"Has a `src/` and a `.github/`" describes most modern repositories, not this one.
The repo where this was found is a Bun app with `src/server.ts` and a generated
`.github/workflows/atdd-validate.yml` — so the guard passed, the validator copied
that consumer's `src/` tree into a scratch dir, and then failed looking for a
toolkit path inside it. A guard keyed on ordinary directory names fails open
precisely where it was needed.

`is_atdd_source_repo` is the identity check that already exists for this, and its
own docstring asks for it: dogfood tests "must call this and `pytest.skip(...)`
when it returns False. Otherwise those tests leak into consumer runs" (#272, #276).
The layout convention does not apply — it exempts test files outright — so this
guard IS the rule.

Two mechanisms, deliberately, because they fail in different runners: the
`platform` marker is what `atdd validate` filters on (it passes `-m 'not platform'`
when `is_atdd_source_repo()` is False), and the module-level skip is what protects
a bare `pytest` run that applies no marker filter at all.

Phase RED: the module carries neither.
Phase GREEN: it carries both.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

TARGET = Path(__file__).with_name(
    "test_r005_smoke_001_real_validate_coach_enforces_projection_only.py"
)


def _module_source() -> str:
    assert TARGET.is_file(), f"{TARGET.name} is missing"
    return TARGET.read_text(encoding="utf-8")


def test_c026_unit_001_reads_the_toolkit_source_tree(tmp_path):
    """Precondition: this really is a toolkit-self validator, not a general one."""
    src = _module_source()
    assert "src/atdd/" in src, (
        "this acceptance assumes the target reads the toolkit's own source tree; "
        "if that is no longer true the guard requirement no longer applies"
    )


def test_c026_unit_001_declares_itself_toolkit_self(tmp_path):
    """`atdd validate` filters on the platform marker when outside the source repo."""
    src = _module_source()
    tree = ast.parse(src)

    marks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if getattr(node.value.value, "id", None) == "pytest" and node.value.attr == "mark":
                marks.append(node.attr)

    assert "platform" in marks, (
        f"{TARGET.name} reads the toolkit's own source tree but is not marked "
        f"pytest.mark.platform (marks found: {sorted(set(marks)) or 'none'}), so "
        "`atdd validate`'s `-m 'not platform'` filter does not exclude it in a "
        "consumer repo"
    )


def test_c026_unit_001_declines_to_run_outside_the_source_repo(tmp_path):
    """A bare `pytest` applies no marker filter, so the module must skip itself."""
    src = _module_source()
    assert "is_atdd_source_repo" in src, (
        f"{TARGET.name} does not consult is_atdd_source_repo, so under a bare "
        "pytest run in a consumer repo it executes and fails on a path that repo "
        "has no reason to have — the leak #272 and #276 already named"
    )
    assert "skip" in src, (
        f"{TARGET.name} consults is_atdd_source_repo but never skips on it"
    )
