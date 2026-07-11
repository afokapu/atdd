# URN: test:project-shared-state:verify-projection-canonicality:C002-UNIT-001-roundtrip-mismatch-fails
# Acceptance: acc:project-shared-state:C002-UNIT-001-roundtrip-mismatch-fails
# WMBT: wmbt:project-shared-state:C002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A hand-edited projection whose bytes are not the canonical output of project(hydrate(...)) fails the canonicality check with a non-zero exit, naming the offending <uid>.yaml and showing the canonical-versus-committed diff. Refs #1433.
"""A hand-edited projection fails the canonicality check (C002-UNIT-001).

wagon: project-shared-state | feature: verify-projection-canonicality | phase: RED
WMBT: wmbt:project-shared-state:C002

I2: the projection is *derived and gated*, never hand-authored. The gate is the
round-trip identity — the only guarantee CI can honestly make, because it cannot
read a gitignored developer store. Refs #1433 / #1400.
"""
from __future__ import annotations

from atdd.state.projection_cli import _cmd_canonicality
from atdd.state.projection import check_canonicality, project
from atdd.state.work_item_writer import mint_work_item

from ._helpers import memory_store


class _Args:
    """The parsed-CLI shape `atdd state canonicality --from <dir>` produces."""

    def __init__(self, from_dir):
        self.op = "canonicality"
        self.from_dir = str(from_dir)
        self.root = None


def test_c002_unit_001_roundtrip_mismatch_fails(tmp_path, capsys) -> None:
    """A non-canonical key order is caught, named, and diffed; the check exits non-zero."""
    projection_dir = tmp_path / "projection"
    with memory_store() as (conn, store):
        obj = mint_work_item(conn, slug="feature-x", owner_actor="dev-a",
                             body="body", phase="PLANNED")
        project(store, projection_dir)

    offender = projection_dir / f"{obj.uid}.yaml"
    canonical_text = offender.read_text(encoding="utf-8")

    # Hand-edit ONE file into non-canonical key order: hoist `uid` to the top. The
    # content is unchanged and the YAML still parses — only the bytes are wrong.
    lines = canonical_text.splitlines(keepends=True)
    uid_line = next(line for line in lines if line.startswith("uid:"))
    offender.write_text(uid_line + "".join(l for l in lines if l is not uid_line),
                        encoding="utf-8")
    assert offender.read_text(encoding="utf-8") != canonical_text

    report = check_canonicality(projection_dir)

    # The report names the offending <uid>.yaml and shows the canonical-versus-
    # committed diff.
    assert not report.ok
    assert [m.filename for m in report.mismatches] == [f"{obj.uid}.yaml"]
    diff = report.mismatches[0].diff
    assert f"committed/{obj.uid}.yaml" in diff
    assert f"canonical/{obj.uid}.yaml" in diff
    assert "-uid:" in diff and "+uid:" not in diff.split("+++")[1][:40]
    assert f"{obj.uid}.yaml" in report.render()

    # The check fails with a non-zero exit code.
    assert _cmd_canonicality(_Args(projection_dir)) == 1
    assert f"{obj.uid}.yaml" in capsys.readouterr().out
