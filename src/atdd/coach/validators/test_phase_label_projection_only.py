# URN: component:govern-lifecycle:enforcement-substrate:test_phase_label_projection_only:backend:domain
# Runtime: python
# Purpose: Enforces coach.phase-label.projection-only — the atdd:<PHASE> label is a
#          projection of objects.state and may only be written by IssueManager.update.
"""
Validator for ``coach.phase-label.projection-only`` (issue #1452).

The ``atdd:<PHASE>`` label is a **projection** of ``objects.state``, not a
record. ``IssueManager.update`` is its sole authoritative writer: it writes the
store first (``_store_set_status``) and then renders the label from it, behind
the phase machine, the train gate and the COMPLETE gates.

Anything else that writes an ``atdd:*`` label inverts the model. The derived
artifact moves and the source of truth rots silently behind it, because every
CLI surface reads the label — so the drift is invisible without querying the DB.

That is not hypothetical. ``.github/workflows/post-merge-lifecycle.yml`` shelled
out to ``gh issue edit --add-label atdd:COMPLETE`` on every merged PR. Measured
2026-07-13: **236 of 421 issues (56%) carried a label their store never earned**,
217 of them the single signature ``label=COMPLETE`` with the store parked at the
last legitimately-driven phase (INIT 82, REFACTOR 61, SMOKE 34, GREEN 21,
PLANNED 19).

**This validator exists because deleting the writer was not enough once
before.** #1434 — "Implement the state→projection→git collaboration model", the
issue whose whole purpose was to end this desync — was itself stamped
``atdd:COMPLETE`` with its own store at ``SMOKE``. Its merge added three new
workflows and never touched ``post-merge-lifecycle.yml``; both raw ``gh issue
edit`` calls survived it. A guard, not a deletion, is what stops the regrowth.

Convention: ``src/atdd/coach/conventions/coach.convention.yaml``
            (rule ``coach.phase-label.projection-only``).

Run: ``atdd validate coach``
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Mapping

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

# Toolkit dogfood: asserts on toolkit-only repo content (#1475).
pytestmark = [pytest.mark.platform]

_RULE = bind_rule("coach.phase-label.projection-only")
_VALIDATOR_ID = "phase_label_projection_only"
_RULE_ID = "coach.phase-label.projection-only"
_SEVERITY = 4

REPO_ROOT = find_repo_root()

# The ONLY code path allowed to write an `atdd:<PHASE>` label. It is the
# store-first authoritative writer described in
# `issue_transition.apply_transition` step 3.
#
# The exemption is scoped to the METHOD, not the file. #1742: this rule has
# always been method-scoped in its prose — "IssueManager.update is its sole
# authoritative writer" — but the exemption was applied per path, so the whole
# of issue.py was unscanned. A second raw writer grew inside it
# (`_archive_github`'s remove-then-add swap), wrote `atdd:COMPLETE` a second
# time on every terminal transition, and the sweep stayed green the entire
# time. Granularity mismatch, not a missing pattern. Everything in this file
# outside `_write_phase_label` is now scanned like any other module.
AUTHORITATIVE_WRITER = "src/atdd/coach/commands/issue.py"
AUTHORITATIVE_WRITER_METHOD = "_write_phase_label"

# The `atdd:` token, in either a literal (`atdd:COMPLETE`) or an interpolated
# form (`atdd:${PHASE}`, `atdd:{status}`, `f"atdd:{status}"`). The interpolated
# form matters: the deleted post-merge-lifecycle loop wrote `atdd:${PHASE}`, so
# a literal-only regex would have missed the removal half of the swap.
_ATDD_LABEL_TOKEN = re.compile(r"atdd:(?:[A-Z]+|\$?\{)")

# A shell label write: `gh issue edit ... --add-label/--remove-label`.
_SHELL_LABEL_WRITE = re.compile(r"--(?:add|remove)-label\b")

# A Python label write. Deliberately NOT anchored on a leading dot: the second
# raw writer found by #1452 was `coach.py`'s module-level `_gh_add_label(...)`
# shim, which a `\.add_label\(` pattern sails straight past. Matches any callable
# whose name contains add/remove + `_label`, so wrappers cannot rename their way
# out: `add_label(`, `_gh_add_label(`, `_gh_remove_phase_labels(`.
_PY_LABEL_WRITE = re.compile(r"\b\w*(?:add|remove)\w*_labels?\w*\s*\(")


def _is_test_path(rel: str) -> bool:
    """Tests assert *about* label writes; they do not perform them."""
    parts = Path(rel).parts
    return (
        "tests" in parts
        or Path(rel).name.startswith("test_")
        or rel.startswith("tests/")
    )


def exempt_line_span(source: str) -> range:
    """The line span of `_write_phase_label`, or an empty span (#1742).

    Fails closed on purpose. If the source will not parse, or holds no method
    by that name, nothing is exempt and the whole text is scanned. A guard that
    resolves an ambiguous exemption in favour of the exemption is how the
    second writer survived.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return range(0)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == AUTHORITATIVE_WRITER_METHOD
        ):
            return range(node.lineno, (node.end_lineno or node.lineno) + 1)
    return range(0)


def scan_for_raw_phase_label_writes(
    sources: Mapping[str, str],
) -> List[Violation]:
    """Pure evaluator: repo-relative path → text ⇒ violations.

    Pure so the fault-injection tests below can drive it from synthetic content
    without mutating the repo. A guard that is only ever run against a clean
    tree has never been shown to fail.
    """
    violations: List[Violation] = []
    for rel_path in sorted(sources):
        if _is_test_path(rel_path):
            continue
        # Method-scoped, not file-scoped (#1742): only the body of
        # `_write_phase_label` is exempt, and only inside the file that owns it.
        exempt_lines = (
            exempt_line_span(sources[rel_path])
            if rel_path == AUTHORITATIVE_WRITER
            else range(0)
        )
        for lineno, line in enumerate(sources[rel_path].splitlines(), start=1):
            if lineno in exempt_lines:
                continue
            if not _ATDD_LABEL_TOKEN.search(line):
                continue
            if _SHELL_LABEL_WRITE.search(line):
                kind = "shell (`gh issue edit --add-label/--remove-label`)"
            elif _PY_LABEL_WRITE.search(line):
                kind = "python (`add_label`/`remove_label`)"
            else:
                continue
            where = (
                f"outside {AUTHORITATIVE_WRITER_METHOD}, in the very file that "
                f"owns it — the exemption covers that one method, not this "
                f"module"
                if rel_path == AUTHORITATIVE_WRITER
                else f"outside IssueManager.update ({AUTHORITATIVE_WRITER})"
            )
            violations.append(
                Violation(
                    rule_id=_RULE_ID,
                    severity=_SEVERITY,
                    location=f"{rel_path}:{lineno}",
                    detail=(
                        f"raw {kind} write of an atdd:<PHASE> label {where}. The "
                        "label is a projection of objects.state; writing it "
                        "here bypasses the phase machine, the train gate, the "
                        "COMPLETE gates and the store write. Drive the phase "
                        "through `atdd coach transition <N> <PHASE>` instead."
                    ),
                )
            )
    return violations


def _scanned_sources() -> Dict[str, str]:
    """Every repo file that could plausibly author a phase label."""
    globs = (
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        "src/atdd/**/templates/workflows/*.yml",
        "src/atdd/**/templates/workflows/*.yaml",
        "scripts/**/*.sh",
        "scripts/**/*.py",
        "src/atdd/**/*.py",
    )
    sources: Dict[str, str] = {}
    for pattern in globs:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            try:
                sources[rel] = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
    return sources


# ---------------------------------------------------------------------------
# The repo assertion
# ---------------------------------------------------------------------------


def test_no_raw_atdd_phase_label_writes_outside_issue_manager():
    """No workflow, script or module writes an atdd:<PHASE> label directly."""
    violations = scan_for_raw_phase_label_writes(_scanned_sources())
    assert_disposition_satisfied(_VALIDATOR_ID, violations, repo_root=REPO_ROOT)


def test_post_merge_lifecycle_authors_no_phase_label():
    """The specific regression: post-merge-lifecycle.yml must stay label-free.

    Named explicitly rather than left to the repo-wide sweep because this is the
    file the bug lived in, and #1434 proved the sweep alone is not what people
    read when they add a step.
    """
    path = REPO_ROOT / ".github" / "workflows" / "post-merge-lifecycle.yml"
    if not path.exists():
        pytest.skip("post-merge-lifecycle.yml not present in this repo")
    violations = scan_for_raw_phase_label_writes(
        {".github/workflows/post-merge-lifecycle.yml": path.read_text()}
    )
    assert not violations, (
        "post-merge-lifecycle.yml writes an atdd:<PHASE> label again (#1452). "
        "The phase advance on merge belongs to atdd-auto-phase.yml → "
        "`atdd coach transition` → IssueManager.update, which writes the store "
        "first and projects the label from it. Sites: "
        + "; ".join(v.location for v in violations)
    )


# ---------------------------------------------------------------------------
# The allowlist's own integrity — a second, orthogonal assertion
# ---------------------------------------------------------------------------
#
# The repo assertion above is only as tight as its exemption. If
# AUTHORITATIVE_WRITER ever names a path that does not exist, or one that no
# longer performs a phase-label write, the exemption has quietly widened into a
# hole and the sweep still passes green. So the allowlist is constrained
# independently of the sweep that consumes it.


def test_authoritative_writer_exists_and_actually_writes_the_label():
    """The one exempt path must exist AND genuinely be the label writer."""
    path = REPO_ROOT / AUTHORITATIVE_WRITER
    assert path.exists(), (
        f"The phase-label allowlist exempts {AUTHORITATIVE_WRITER}, which does "
        "not exist. A stale exemption is a hole in the guard: point it at the "
        "module that now owns IssueManager.update, or drop it."
    )
    text = path.read_text()
    assert "_write_phase_label" in text and "add_label" in text, (
        f"{AUTHORITATIVE_WRITER} is exempt from the raw-label-write guard "
        "because it is the authoritative writer, but it no longer contains a "
        "phase-label write. The exemption is now unearned — move it to "
        "whichever module took over, so the guard keeps covering exactly one "
        "writer."
    )
    assert exempt_line_span(text), (
        f"{AUTHORITATIVE_WRITER} no longer defines "
        f"`{AUTHORITATIVE_WRITER_METHOD}`, so the method-scoped exemption "
        "resolves to nothing and every label write in the file will be "
        "flagged. Re-point AUTHORITATIVE_WRITER_METHOD at whatever renamed it."
    )


def test_authoritative_writer_holds_exactly_one_phase_label_write():
    """Exactly one. "Contains a writer" was never the property that mattered.

    The assertion above only ever checked that the exempt file *contains* a
    phase-label write. #1742: `_archive_github` grew a second one inside the
    same file, wrote `atdd:COMPLETE` over `atdd:COMPLETE` on every terminal
    transition for as long as it took to catch it on the wire, and this test
    passed throughout — because one writer and two writers both satisfy
    "contains". Count them, and require the survivor to sit inside the one
    method the exemption names.
    """
    text = (REPO_ROOT / AUTHORITATIVE_WRITER).read_text()
    span = exempt_line_span(text)
    writes = [
        lineno
        for lineno, line in enumerate(text.splitlines(), start=1)
        if _ATDD_LABEL_TOKEN.search(line)
        and (_SHELL_LABEL_WRITE.search(line) or _PY_LABEL_WRITE.search(line))
    ]
    assert len(writes) == 1, (
        f"{AUTHORITATIVE_WRITER} holds {len(writes)} raw atdd:<PHASE> label "
        f"writes at lines {writes}; the exemption sanctions exactly one, in "
        f"`{AUTHORITATIVE_WRITER_METHOD}`. A second writer in this file is the "
        "#1742 regrowth: it bypasses the phase machine, the train gate and the "
        "COMPLETE gates, and it double-delivers the label. Route it through "
        f"`{AUTHORITATIVE_WRITER_METHOD}` or delete it."
    )
    assert writes[0] in span, (
        f"The one label write in {AUTHORITATIVE_WRITER} is at line {writes[0]}, "
        f"outside `{AUTHORITATIVE_WRITER_METHOD}` (lines "
        f"{span.start}-{span.stop - 1}). The exemption covers that method, not "
        "the module: a write that has moved out of it is unsanctioned."
    )


def test_authoritative_writer_writes_the_store_before_the_label():
    """Store first, label as its projection — the ordering is the fix (#1452).

    An exemption for "the authoritative writer" is only justified while that
    writer is actually store-first. If the label write drifts back above the
    store write, the exempt path is authoring an unearned label too — just more
    politely than the workflow did.
    """
    text = (REPO_ROOT / AUTHORITATIVE_WRITER).read_text()
    store_write = text.find("self._update_manifest_status(issue_number, status)")
    label_write = text.find(
        "self._write_phase_label(client, issue_number, current_labels, status)"
    )
    assert store_write != -1 and label_write != -1, (
        "Could not locate the store write and the label projection in "
        f"{AUTHORITATIVE_WRITER}. If IssueManager.update was refactored, "
        "re-anchor this assertion on the new call sites — do not delete it."
    )
    assert store_write < label_write, (
        "IssueManager.update projects the atdd:<PHASE> label BEFORE writing "
        "objects.state. The order is load-bearing (#1452): the source of truth "
        "must move before the artifact derived from it, or a failure between "
        "the two leaves the label asserting a transition that never happened."
    )


# ---------------------------------------------------------------------------
# Fault injection — prove the guard can go red
# ---------------------------------------------------------------------------


def test_guard_catches_the_deleted_post_merge_lifecycle_step():
    """The exact step deleted from post-merge-lifecycle.yml must be caught.

    This is the regrowth case verbatim, including the interpolated
    `atdd:${PHASE}` removal loop that a literal-only match would miss.
    """
    regrown = """
      - name: Swap labels to atdd:COMPLETE
        run: |
          for PHASE in INIT PLANNED RED GREEN SMOKE REFACTOR BLOCKED; do
            gh issue edit "$ISSUE" --repo "$REPO" --remove-label "atdd:${PHASE}"
          done
          gh issue edit "$ISSUE" --repo "$REPO" --add-label "atdd:COMPLETE"
"""
    violations = scan_for_raw_phase_label_writes(
        {".github/workflows/post-merge-lifecycle.yml": regrown}
    )
    locations = [v.location for v in violations]
    assert len(violations) == 2, (
        "The guard must catch BOTH halves of the swap — the interpolated "
        f"remove and the literal add. Caught: {locations}"
    )
    assert ".github/workflows/post-merge-lifecycle.yml:5" in locations
    assert ".github/workflows/post-merge-lifecycle.yml:7" in locations
    assert all(v.rule_id == _RULE_ID for v in violations)


def test_guard_catches_a_python_label_writer():
    """Regrowth in Python is the same defect wearing a different hat."""
    violations = scan_for_raw_phase_label_writes(
        {"src/atdd/coach/commands/somewhere.py": 'client.add_label(n, ["atdd:COMPLETE"])\n'}
    )
    assert len(violations) == 1, f"Expected 1 violation, got {violations}"
    assert violations[0].location == "src/atdd/coach/commands/somewhere.py:1"


def test_guard_catches_a_shell_script_label_writer():
    """`scripts/*.sh` is inside the blast radius too."""
    violations = scan_for_raw_phase_label_writes(
        {"scripts/close.sh": 'gh issue edit "$N" --add-label "atdd:COMPLETE"\n'}
    )
    assert len(violations) == 1, f"Expected 1 violation, got {violations}"


_SANCTIONED = '''
class IssueManager:
    @staticmethod
    def _write_phase_label(client, issue_number, current_labels, status):
        phase_labels = [l for l in current_labels if l.startswith("atdd:")]
        if phase_labels:
            client.remove_label(issue_number, phase_labels)
        client.add_label(issue_number, [f"atdd:{status}"])
        return True
'''


def test_guard_does_not_fire_on_the_authoritative_writer():
    """`_write_phase_label` is the sanctioned writer — it must stay green."""
    violations = scan_for_raw_phase_label_writes({AUTHORITATIVE_WRITER: _SANCTIONED})
    assert violations == [], f"False positives: {[v.location for v in violations]}"


def test_guard_catches_a_second_writer_inside_the_exempt_file():
    """The #1742 regrowth, verbatim: a raw swap in the authoritative file.

    This is the case the file-scoped exemption could not see. `_archive_github`
    lived in the exempt path, so its remove-then-add swap was never scanned —
    the guard was green while the label was being written twice on every
    terminal transition. Scoping the exemption to `_write_phase_label` is what
    makes this red.
    """
    regrown = _SANCTIONED + '''
    def _archive_github(self, issue_id):
        client.remove_label(issue_number, phase_labels)
        client.add_label(issue_number, ["atdd:COMPLETE"])
        return 0
'''
    violations = scan_for_raw_phase_label_writes({AUTHORITATIVE_WRITER: regrown})
    locations = [v.location for v in violations]
    assert len(violations) == 1, (
        "A raw atdd:<PHASE> write outside `_write_phase_label` must be caught "
        f"even inside {AUTHORITATIVE_WRITER}. Caught: {locations}"
    )
    assert violations[0].rule_id == _RULE_ID
    assert AUTHORITATIVE_WRITER_METHOD in violations[0].detail


def test_exempt_span_fails_closed_when_the_method_is_gone():
    """No `_write_phase_label` ⇒ nothing exempt, not everything exempt.

    A renamed or deleted method must not silently re-open the whole file. The
    integrity test above catches the rename loudly; this makes the scanner's
    own behaviour safe in the meantime.
    """
    assert exempt_line_span("def something_else():\n    pass\n") == range(0)
    assert exempt_line_span("this is not python ((") == range(0)

    violations = scan_for_raw_phase_label_writes(
        {AUTHORITATIVE_WRITER: 'client.add_label(n, [f"atdd:{status}"])\n'}
    )
    assert len(violations) == 1, (
        "With no `_write_phase_label` to anchor it, the exemption must resolve "
        "to nothing and the file must be scanned like any other."
    )


def test_guard_does_not_fire_on_tests_or_non_phase_labels():
    """Tests assert about label writes, and `atdd-issue` is not a phase label."""
    violations = scan_for_raw_phase_label_writes(
        {
            "src/atdd/coach/commands/tests/test_x.py": (
                'client.add_label.assert_called_once_with(384, ["atdd:GREEN"])\n'
            ),
            "src/atdd/coach/commands/y.py": (
                'client.add_label(issue_number, ["atdd-issue"])\n'
            ),
            "src/atdd/coach/commands/z.py": "# mentions atdd:COMPLETE in a comment\n",
        }
    )
    assert violations == [], f"False positives: {[v.location for v in violations]}"
