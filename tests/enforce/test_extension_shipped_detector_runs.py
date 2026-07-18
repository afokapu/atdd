"""An EXTENSION-shipped detector must be runnable by `atdd enforce` (#1359).

A workspace package ships the detectors for its own runtime, but an extension may
ship its own detectors targeting that workspace's provider contract. Before this
guard the runner discovered implementations only under ``.atdd/workspaces``, so
every extension-shipped detector was reported ``unrunnable`` while the aggregate
verdict still printed PASS — a false green.

These tests build a minimal real substrate in a tmp_path (a workspace provider
whose ``cli/scan.py`` is the real subprocess boundary, plus an extension shipping
one detector) and drive the real ``enforce`` runner over it. No mocks: the
detector is discovered, subprocessed, and its RAW v1.1 records become a verdict.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.runner import _resolve_impls_root, enforce

# A stand-in provider CLI honouring the real contract: discover the impl under
# --impls-root, run its report channel, print RAW v1.1 JSON to stdout.
_PROVIDER_CLI = '''\
import argparse, json, os, sys
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument("--impl", default=os.environ.get("ATDD_IMPL_ID"))
ap.add_argument("--impls-root", default=str(Path(__file__).resolve().parent.parent / "implementations"))
ap.add_argument("scan_roots", nargs="*")
args = ap.parse_args()
root = Path(args.impls_root)
manifest = next((m for m in root.rglob("atdd.implementation.yaml")
                 if args.impl in m.read_text()), None)
if manifest is None:
    print(f"provider-cli: impl {args.impl!r} not discoverable under {root}", file=sys.stderr)
    sys.exit(2)
roots = json.loads(os.environ.get("ATDD_SCAN_ROOTS", "[]"))
violations = [
    {"rule_id": "acme.rule.owned", "file": f"{r}/bad.py", "line": 1, "col": 0,
     "evidence": "injected", "source_line": "x = 1"}
    for r in roots
]
json.dump(violations, sys.stdout)
'''

_CONVENTION = """\
schema_version: '1.0.0'
kind: convention
convention_id: acme.rule.owned
metadata:
  severity: 2
  disposition: strict
"""


def _build_substrate(tmp_path: Path, *, detector_in_extension: bool) -> Path:
    """Vendor a workspace provider + one detector, then bind it in binding.lock."""
    atdd = tmp_path / ".atdd"
    ws = atdd / "workspaces" / "atdd.workspace.python-pytest" / "0.1.0"
    (ws / "cli").mkdir(parents=True)
    (ws / "cli" / "scan.py").write_text(_PROVIDER_CLI, encoding="utf-8")
    (ws / "atdd.workspace.yaml").write_text(
        "schema_version: '1.0.0'\nkind: workspace\n"
        "workspace_id: atdd.workspace.python-pytest\ncontract_version: '1.1.0'\n",
        encoding="utf-8",
    )

    ext = atdd / "extensions" / "acme.extension.rules" / "0.1.0"
    (ext / "conventions").mkdir(parents=True)
    (ext / "conventions" / "acme.rule.owned.convention.yaml").write_text(_CONVENTION, encoding="utf-8")

    home = ext if detector_in_extension else ws
    impl = home / "implementations" / "owned_detector"
    impl.mkdir(parents=True)
    (impl / "atdd.implementation.yaml").write_text(
        "schema_version: '1.1.0'\nkind: implementation\n"
        "implementation_id: acme.rule.owned.impl\n"
        "targets_workspace: atdd.workspace.python-pytest\n"
        "contract_version: '1.1.0'\n"
        "realizes_convention: acme.rule.owned\n"
        "entrypoint: detect.py\nreport: test_owned_report.py\n",
        encoding="utf-8",
    )
    (impl / "test_owned_report.py").write_text("", encoding="utf-8")

    (atdd / "binding.lock.yaml").write_text(
        "schema_version: 1.0.0\nconventions:\n"
        "- convention_id: acme.rule.owned\n  disposition: bound\n"
        "  implementation_id: acme.rule.owned.impl\n"
        "  workspace_id: atdd.workspace.python-pytest\n  contract_version: 1.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer").mkdir()
    (tmp_path / "consumer" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_extension_shipped_detector_resolves_to_its_own_impls_root(tmp_path: Path) -> None:
    root = _build_substrate(tmp_path, detector_in_extension=True)

    impls_root = _resolve_impls_root(root, "acme.rule.owned.impl")

    assert impls_root is not None, "an extension-shipped detector must be discoverable"
    assert impls_root == root / ".atdd" / "extensions" / "acme.extension.rules" / "0.1.0" / "implementations"


def test_extension_shipped_detector_produces_a_real_fail_not_a_false_green(tmp_path: Path) -> None:
    root = _build_substrate(tmp_path, detector_in_extension=True)

    result = enforce(root, path_override=["consumer"])

    statuses = {v.rule_id: v.status for v in result.verdicts}
    assert statuses == {"acme.rule.owned": "fail"}, "the injected violation must surface as FAIL"
    assert result.exit_code == 1
    assert not result.passed


def test_workspace_shipped_detector_still_resolves(tmp_path: Path) -> None:
    """Regression: forwarding --impls-root must not break the workspace's own detectors."""
    root = _build_substrate(tmp_path, detector_in_extension=False)

    result = enforce(root, path_override=["consumer"])

    assert [v.status for v in result.verdicts] == ["fail"]


def test_absent_implementation_is_unrunnable_not_silently_passing(tmp_path: Path) -> None:
    root = _build_substrate(tmp_path, detector_in_extension=True)
    (root / ".atdd" / "binding.lock.yaml").write_text(
        "schema_version: 1.0.0\nconventions:\n"
        "- convention_id: acme.rule.owned\n  disposition: bound\n"
        "  implementation_id: acme.rule.ghost.impl\n"
        "  workspace_id: atdd.workspace.python-pytest\n  contract_version: 1.1.0\n",
        encoding="utf-8",
    )

    result = enforce(root, path_override=["consumer"])

    assert [v.status for v in result.verdicts] == ["unrunnable"]
