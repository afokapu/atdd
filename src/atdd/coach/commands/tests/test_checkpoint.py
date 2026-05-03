"""
Unit tests for `atdd checkpoint <N>` (issue #378).

The checkpoint helper persists worker session state to
``.atdd/worker-state-<issue>.json`` so a `/clear`+reload cycle can be
restored via `atdd session-template <N> --from-checkpoint`.

Schema lives at ``src/atdd/coach/schemas/worker-state.schema.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.commands.checkpoint import (
    DEFAULT_TTL_SECONDS,
    checkpoint_path,
    read_worker_checkpoint,
    write_worker_checkpoint,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# checkpoint_path
# ---------------------------------------------------------------------------


def test_checkpoint_path_uses_atdd_dir(tmp_path: Path):
    p = checkpoint_path(378, root=tmp_path)
    assert p == tmp_path / ".atdd" / "worker-state-378.json"


# ---------------------------------------------------------------------------
# write_worker_checkpoint
# ---------------------------------------------------------------------------


def test_write_creates_atdd_dir_if_missing(tmp_path: Path):
    assert not (tmp_path / ".atdd").exists()
    write_worker_checkpoint(
        issue=378,
        phase="GREEN",
        summary="initial work",
        open_files=["src/foo.py"],
        root=tmp_path,
    )
    assert (tmp_path / ".atdd" / "worker-state-378.json").exists()


def test_write_persists_all_required_fields(tmp_path: Path):
    write_worker_checkpoint(
        issue=378,
        phase="GREEN",
        summary="RED tests landed",
        open_files=["src/atdd/coach/commands/checkpoint.py"],
        branch="feat/worker-context-window-management",
        last_commit="abc1234",
        root=tmp_path,
    )
    data = json.loads((tmp_path / ".atdd" / "worker-state-378.json").read_text())
    assert data["issue"] == 378
    assert data["phase"] == "GREEN"
    assert data["summary"] == "RED tests landed"
    assert data["open_files"] == ["src/atdd/coach/commands/checkpoint.py"]
    assert data["branch"] == "feat/worker-context-window-management"
    assert data["last_commit"] == "abc1234"
    assert "checkpointed_at" in data
    assert data["ttl_seconds"] == DEFAULT_TTL_SECONDS


def test_write_truncates_summary_to_500_chars(tmp_path: Path):
    long_summary = "x" * 700
    write_worker_checkpoint(
        issue=378,
        phase="GREEN",
        summary=long_summary,
        open_files=[],
        root=tmp_path,
    )
    data = json.loads((tmp_path / ".atdd" / "worker-state-378.json").read_text())
    assert len(data["summary"]) == 500


def test_write_validates_phase(tmp_path: Path):
    with pytest.raises(ValueError, match="phase"):
        write_worker_checkpoint(
            issue=378,
            phase="BOGUS",
            summary="x",
            open_files=[],
            root=tmp_path,
        )


def test_write_overwrites_previous_checkpoint(tmp_path: Path):
    write_worker_checkpoint(
        issue=378, phase="RED", summary="first", open_files=[], root=tmp_path,
    )
    write_worker_checkpoint(
        issue=378, phase="GREEN", summary="second", open_files=[], root=tmp_path,
    )
    data = json.loads((tmp_path / ".atdd" / "worker-state-378.json").read_text())
    assert data["phase"] == "GREEN"
    assert data["summary"] == "second"


def test_write_is_atomic_via_tmp_rename(tmp_path: Path, monkeypatch):
    """The write must go through a temp file then rename, so a partial write
    cannot leave a corrupt JSON document at the canonical path."""
    target = tmp_path / ".atdd" / "worker-state-378.json"
    target.parent.mkdir()
    target.write_text('{"issue": 0, "phase": "PRE-EXISTING"}')

    real_replace = Path.replace
    seen = {}

    def spy(self, dst):
        seen["src"] = str(self)
        seen["dst"] = str(dst)
        return real_replace(self, dst)

    monkeypatch.setattr(Path, "replace", spy)
    write_worker_checkpoint(
        issue=378, phase="GREEN", summary="x", open_files=[], root=tmp_path,
    )
    assert seen.get("src", "").endswith(".json.tmp")
    assert seen.get("dst", "").endswith("worker-state-378.json")


# ---------------------------------------------------------------------------
# read_worker_checkpoint
# ---------------------------------------------------------------------------


def test_read_returns_none_when_missing(tmp_path: Path):
    assert read_worker_checkpoint(378, root=tmp_path) is None


def test_read_round_trips_write(tmp_path: Path):
    write_worker_checkpoint(
        issue=378,
        phase="SMOKE",
        summary="smoke fixture in place",
        open_files=["a.py", "b.py"],
        root=tmp_path,
    )
    cp = read_worker_checkpoint(378, root=tmp_path)
    assert cp is not None
    assert cp["issue"] == 378
    assert cp["phase"] == "SMOKE"
    assert cp["open_files"] == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# Schema compliance
# ---------------------------------------------------------------------------


def test_written_checkpoint_validates_against_schema(tmp_path: Path):
    """Round-trip writer output through jsonschema against the canonical schema."""
    import jsonschema

    schema_path = (
        Path(__file__).resolve().parents[2] / "schemas" / "worker-state.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    write_worker_checkpoint(
        issue=378,
        phase="GREEN",
        summary="schema check",
        open_files=["src/foo.py"],
        branch="feat/x",
        last_commit="deadbee",
        root=tmp_path,
    )
    data = json.loads((tmp_path / ".atdd" / "worker-state-378.json").read_text())
    jsonschema.validate(data, schema)
