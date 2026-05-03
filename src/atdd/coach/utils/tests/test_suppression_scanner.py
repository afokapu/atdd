# URN: component:govern-lifecycle:enforcement-substrate:suppression_scanner:backend:tests
# Runtime: python
# Purpose: Cover marker discovery + stale detection + legacy is_suppressed contract.

"""Unit tests for ``atdd.coach.utils.suppression_scanner``."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from atdd.coach.utils.suppression_scanner import (
    find_stale_suppressions,
    find_suppressions,
    is_suppressed,
)


def _write(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# is_suppressed (legacy substring contract from #357)
# ---------------------------------------------------------------------------

def test_is_suppressed_bare_marker():
    assert is_suppressed(
        "print('x')  # atdd:suppress(LOG-PRINT-001)",
        "LOG-PRINT-001",
    )


def test_is_suppressed_marker_with_until():
    assert is_suppressed(
        "print('x')  # atdd:suppress(LOG-PRINT-001) UNTIL=2099-01-01",
        "LOG-PRINT-001",
    )


def test_is_suppressed_wrong_rule_id():
    assert not is_suppressed(
        "print('x')  # atdd:suppress(OTHER-RULE-001)",
        "LOG-PRINT-001",
    )


# ---------------------------------------------------------------------------
# find_suppressions
# ---------------------------------------------------------------------------

def test_find_suppressions_python_and_typescript(tmp_path):
    py = _write(
        tmp_path / "a.py",
        "print('x')  # atdd:suppress(LOG-001)\n",
    )
    ts = _write(
        tmp_path / "b.ts",
        "console.log('y')  // atdd:suppress(LOG-002) UNTIL=2099-12-31\n",
    )
    tsx = _write(
        tmp_path / "c.tsx",
        "// atdd:suppress(JSX-001)\n",
    )
    found = find_suppressions([tmp_path])
    by_id = {m.rule_id: m for m in found}
    assert set(by_id) == {"LOG-001", "LOG-002", "JSX-001"}
    assert by_id["LOG-002"].until == date(2099, 12, 31)
    assert by_id["LOG-001"].until is None


def test_find_suppressions_skips_vendored_dirs(tmp_path):
    _write(
        tmp_path / "node_modules" / "pkg" / "x.ts",
        "// atdd:suppress(SHOULD-NOT-FIND)\n",
    )
    _write(
        tmp_path / ".venv" / "lib" / "x.py",
        "# atdd:suppress(ALSO-NOT-FOUND)\n",
    )
    _write(
        tmp_path / "src" / "x.py",
        "# atdd:suppress(FOUND)\n",
    )
    found = {m.rule_id for m in find_suppressions([tmp_path])}
    assert found == {"FOUND"}


def test_find_suppressions_skips_other_extensions(tmp_path):
    _write(
        tmp_path / "x.md",
        "# atdd:suppress(IGNORE-DOCS)\n",
    )
    _write(
        tmp_path / "x.py",
        "# atdd:suppress(KEEP)\n",
    )
    found = {m.rule_id for m in find_suppressions([tmp_path])}
    assert found == {"KEEP"}


# ---------------------------------------------------------------------------
# find_stale_suppressions
# ---------------------------------------------------------------------------

def test_find_stale_suppressions_only_past_dates(tmp_path):
    today = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    _write(
        tmp_path / "a.py",
        f"# atdd:suppress(STALE) UNTIL={yesterday.isoformat()}\n",
    )
    _write(
        tmp_path / "b.py",
        f"# atdd:suppress(FRESH) UNTIL={tomorrow.isoformat()}\n",
    )
    _write(
        tmp_path / "c.py",
        "# atdd:suppress(NO-DEADLINE)\n",
    )
    stale = find_stale_suppressions([tmp_path])
    assert {m.rule_id for m in stale} == {"STALE"}


def test_find_stale_suppressions_today_is_not_stale(tmp_path):
    today = date.today()
    _write(
        tmp_path / "a.py",
        f"# atdd:suppress(EDGE) UNTIL={today.isoformat()}\n",
    )
    stale = find_stale_suppressions([tmp_path])
    assert stale == []


def test_find_stale_malformed_until_ignored(tmp_path):
    _write(
        tmp_path / "a.py",
        "# atdd:suppress(MALFORMED) UNTIL=not-a-date\n",
    )
    stale = find_stale_suppressions([tmp_path])
    assert stale == []
