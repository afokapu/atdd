"""Synthetic substrate builder for the bound-realization fault matrix (#1773).

Builds ONE complete, digest-coherent bound realization on disk, then offers a
mutator per link of the proof chain. Every fault test therefore reads as "an
otherwise complete realization, with exactly one link broken" — which is the
claim the fault matrix has to make. Building each broken case from scratch would
let a second, accidental difference creep in and let an arm pass for the wrong
reason.

Nothing here is executed as a provider: the ``cli/scan.py`` and the report test
are inert files whose PRESENCE is what the chain resolves. Core never runs them,
and neither does this harness.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

RULE_ID = "coder.fixture.bound-rule"
OTHER_RULE_ID = "coder.fixture.sibling-rule"
IMPL_ID = "coder.fixture.bound-impl"
WORKSPACE_ID = "atdd.workspace.fixture"
CONTRACT = "1.1.0"
REPORT = "test_fixture_report.py"

_IMPL_DIRNAME = "bound_impl"


def _workspace_dir(root: Path) -> Path:
    return root / ".atdd" / "workspaces" / WORKSPACE_ID / "0.1.0"


def _impl_dir(root: Path) -> Path:
    return _workspace_dir(root) / "implementations" / _IMPL_DIRNAME


def manifest_path(root: Path) -> Path:
    return _impl_dir(root) / "atdd.implementation.yaml"


def lock_path(root: Path) -> Path:
    return root / ".atdd" / "binding.lock.yaml"


def workflow_path(root: Path) -> Path:
    return root / ".github" / "workflows" / "atdd-validate.yml"


# --------------------------------------------------------------------------- #
# read / write helpers                                                        #
# --------------------------------------------------------------------------- #
def read_lock(root: Path) -> dict:
    return yaml.safe_load(lock_path(root).read_text(encoding="utf-8"))


def write_lock(root: Path, lock: dict) -> None:
    lock_path(root).write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")


def read_manifest(root: Path, path: Path | None = None) -> dict:
    return yaml.safe_load((path or manifest_path(root)).read_text(encoding="utf-8"))


def write_manifest(root: Path, data: dict, path: Path | None = None) -> None:
    (path or manifest_path(root)).write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def _digest_of(root: Path) -> str:
    lock = root / ".atdd" / "substrate.lock.yaml"
    return "sha256:" + hashlib.sha256(lock.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# the complete realization                                                    #
# --------------------------------------------------------------------------- #
def build_complete(root: Path) -> Path:
    """Write a complete bound realization for :data:`RULE_ID` under ``root``.

    Every link of the chain resolves: digest-coherent lock, exactly one bound
    entry whose ``convention_id`` is exactly the rule id, exactly one manifest
    for the selected implementation, ownership and emission both naming the rule,
    a present report channel, a resolvable provider CLI, and a blocking Path B.
    """
    atdd = root / ".atdd"
    (atdd).mkdir(parents=True, exist_ok=True)

    # The substrate lock the plan is keyed to. Its CONTENT is irrelevant to the
    # proof — only its digest is — so it stays minimal on purpose.
    (atdd / "substrate.lock.yaml").write_text(
        yaml.safe_dump({"artifacts": [{"id": WORKSPACE_ID, "enabled": True}]}),
        encoding="utf-8",
    )

    ws = _workspace_dir(root)
    (ws / "cli").mkdir(parents=True, exist_ok=True)
    (ws / "atdd.workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "kind": "workspace",
                "workspace_id": WORKSPACE_ID,
                "contract_version": CONTRACT,
            }
        ),
        encoding="utf-8",
    )
    # Present, never invoked — the chain proves the CLI resolves, not that it runs.
    (ws / "cli" / "scan.py").write_text("", encoding="utf-8")

    impl = _impl_dir(root)
    impl.mkdir(parents=True, exist_ok=True)
    write_manifest(
        root,
        {
            "schema_version": "1.1.0",
            "kind": "implementation",
            "implementation_id": IMPL_ID,
            "targets_workspace": WORKSPACE_ID,
            "contract_version": CONTRACT,
            "realizes_convention": [RULE_ID],
            "emits_rule_ids": [RULE_ID],
            "entrypoint": "detector.py",
            "report": REPORT,
        },
    )
    (impl / REPORT).write_text("", encoding="utf-8")

    write_lock(
        root,
        {
            "schema_version": "1.0.0",
            "substrate_lock_digest": _digest_of(root),
            "conventions": [
                {
                    "convention_id": RULE_ID,
                    "disposition": "bound",
                    "implementation_id": IMPL_ID,
                    "workspace_id": WORKSPACE_ID,
                    "contract_version": CONTRACT,
                }
            ],
        },
    )

    set_path_b_blocking(root)
    return root


# --------------------------------------------------------------------------- #
# one mutator per link — each breaks EXACTLY one thing                        #
# --------------------------------------------------------------------------- #
def set_path_b_blocking(root: Path, *, blocking: bool = True) -> None:
    """Write the CI workflow whose ``enforce-extensions`` job decides Path B."""
    step: dict = {"name": "convention verdict", "run": "atdd enforce --repo-root ."}
    if not blocking:
        step["continue-on-error"] = True
    wf = workflow_path(root)
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(
        yaml.safe_dump({"jobs": {"enforce-extensions": {"steps": [step]}}}),
        encoding="utf-8",
    )


def break_digest(root: Path) -> None:
    """Leave the lock claiming a substrate digest that is no longer on disk."""
    lock = read_lock(root)
    lock["substrate_lock_digest"] = "sha256:" + "0" * 64
    write_lock(root, lock)


def drop_lock_entry(root: Path) -> None:
    lock = read_lock(root)
    lock["conventions"] = []
    write_lock(root, lock)


def set_disposition(root: Path, disposition: str = "legacy-fallback") -> None:
    lock = read_lock(root)
    lock["conventions"][0]["disposition"] = disposition
    write_lock(root, lock)


def duplicate_lock_entry(root: Path) -> None:
    lock = read_lock(root)
    lock["conventions"].append(dict(lock["conventions"][0]))
    write_lock(root, lock)


def drop_manifest(root: Path) -> None:
    manifest_path(root).unlink()


def duplicate_manifest(root: Path) -> None:
    """A SECOND manifest declaring the same implementation_id — ambiguous selection."""
    twin = _impl_dir(root).parent / "twin_impl"
    twin.mkdir(parents=True, exist_ok=True)
    data = read_manifest(root)
    write_manifest(root, data, path=twin / "atdd.implementation.yaml")
    (twin / REPORT).write_text("", encoding="utf-8")


def add_second_owner(root: Path) -> None:
    """A DIFFERENT implementation also realizing the rule — ambiguous ownership."""
    rival = _impl_dir(root).parent / "rival_impl"
    rival.mkdir(parents=True, exist_ok=True)
    data = read_manifest(root)
    data["implementation_id"] = IMPL_ID + ".rival"
    write_manifest(root, data, path=rival / "atdd.implementation.yaml")
    (rival / REPORT).write_text("", encoding="utf-8")


def drop_realizes(root: Path) -> None:
    """The manifest no longer claims to own the rule the lock selected it for."""
    data = read_manifest(root)
    data["realizes_convention"] = [OTHER_RULE_ID]
    data["emits_rule_ids"] = [RULE_ID, OTHER_RULE_ID]
    write_manifest(root, data)


def drop_emits(root: Path) -> None:
    """Owned but never emitted — ownership is not emission."""
    data = read_manifest(root)
    data["emits_rule_ids"] = [OTHER_RULE_ID]
    write_manifest(root, data)


def realizes_not_emitted(root: Path) -> None:
    """The author-time subset invariant, bypassed by a hand edit.

    The rule itself IS owned and emitted; a SIBLING convention is owned without
    being emitted. Only the read-time re-assertion of
    ``realizes_convention ⊆ emits_rule_ids`` catches this.
    """
    data = read_manifest(root)
    data["realizes_convention"] = [RULE_ID, OTHER_RULE_ID]
    data["emits_rule_ids"] = [RULE_ID]
    write_manifest(root, data)


def drop_report_field(root: Path) -> None:
    data = read_manifest(root)
    del data["report"]
    write_manifest(root, data)


def unlink_report_file(root: Path) -> None:
    """The channel stays declared; the file it names is gone."""
    (_impl_dir(root) / REPORT).unlink()


def drop_provider_cli(root: Path) -> None:
    (_workspace_dir(root) / "cli" / "scan.py").unlink()


def corrupt_lock(root: Path) -> None:
    lock_path(root).write_text("conventions: [oops\n  - :\n", encoding="utf-8")


def corrupt_manifest(root: Path) -> None:
    manifest_path(root).write_text("kind: [implementation\n  - :\n", encoding="utf-8")
