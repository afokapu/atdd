"""Shared real-substrate builders for the govern-providers wagon tests (#1425).

Every builder here writes REAL files a real reader consumes — a vendored workspace
provider whose ``cli/scan.py`` is the actual subprocess boundary, a real extension
package shipping a detector, and a real digest-pinned ``substrate.lock.yaml`` /
``binding.lock.yaml``. No mocks: the tests drive the real ``atdd.enforce`` /
``atdd.substrate.binding`` code over these trees.

Modelling note (E003): the real ``binding.lock.yaml`` keys each entry by
``implementation_id`` / ``convention_id``, NEVER by the extension PACKAGE identity.
``install_extension_impl`` therefore takes ``implementation_id`` independently of
``ext_id`` so a fixture faithfully reproduces that identity independence — the
package id must not leak into the generated lock.
"""
from __future__ import annotations

from pathlib import Path

# A stand-in provider CLI honouring the real v1.1 contract: discover the impl under
# --impls-root, and print one RAW v1.1 violation per scan root to stdout.
PROVIDER_CLI = '''\
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
    {"rule_id": os.environ.get("ATDD_IMPL_ID"), "file": f"{r}/bad.py", "line": 1, "col": 0,
     "evidence": "injected", "source_line": "x = 1"}
    for r in roots
]
json.dump(violations, sys.stdout)
'''


def install_provider(
    project_root: Path,
    ws_id: str = "atdd.workspace.python-pytest",
    *,
    contract_version: str = "1.0.0",
    with_cli: bool = True,
) -> Path:
    """Install a real workspace provider (manifest + cli/scan.py) + a lock entry."""
    from atdd.substrate import installer

    version = "0.1.0"
    dest = installer.install_path(project_root, "workspace", ws_id, version)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.workspace.yaml").write_text(
        f"schema_version: '1.0.0'\nworkspace_id: {ws_id}\nkind: workspace\n"
        f"version: '{version}'\ncontract_version: '{contract_version}'\n",
        encoding="utf-8",
    )
    if with_cli:
        (dest / "cli").mkdir(parents=True, exist_ok=True)
        (dest / "cli" / "scan.py").write_text(PROVIDER_CLI, encoding="utf-8")
    installer.upsert_lock_entry(
        project_root,
        {
            "id": ws_id, "kind": "workspace", "version": version,
            "digest": installer.compute_digest(dest),
            "installed_path": str(dest.relative_to(project_root)),
            "enabled": True,
        },
    )
    return dest


def install_extension_impl(
    project_root: Path,
    ext_id: str,
    *,
    convention: str,
    implementation_id: str,
    contract_version: str = "1.0.0",
    with_report: bool = True,
    enabled: bool = True,
) -> Path:
    """Install a real extension shipping one detector implementation + lock entry.

    ``implementation_id`` is independent of ``ext_id`` (as the real lock is), so the
    package identity never reaches the generated binding lock.
    """
    from atdd.substrate import installer

    version = "0.1.0"
    dest = installer.install_path(project_root, "extension", ext_id, version)
    impl_dir = dest / "implementations" / "gate"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (dest / "atdd.extension.yaml").write_text(
        f"schema_version: '1.0.0'\nextension_id: {ext_id}\nkind: extension\nversion: '{version}'\n",
        encoding="utf-8",
    )
    report_line = "report: test_gate_report.py\n" if with_report else ""
    (impl_dir / "atdd.implementation.yaml").write_text(
        "schema_version: '1.1.0'\nkind: implementation\n"
        f"implementation_id: {implementation_id}\n"
        "targets_workspace: atdd.workspace.python-pytest\n"
        f"contract_version: '{contract_version}'\n"
        f"realizes_convention: {convention}\nentrypoint: gate.py\n" + report_line,
        encoding="utf-8",
    )
    if with_report:
        (impl_dir / "test_gate_report.py").write_text("", encoding="utf-8")
    installer.upsert_lock_entry(
        project_root,
        {
            "id": ext_id, "kind": "extension", "version": version,
            "digest": installer.compute_digest(dest),
            "installed_path": str(dest.relative_to(project_root)),
            "enabled": enabled,
        },
    )
    return dest


def write_convention_node(project_root: Path, ext_id: str, convention: str) -> Path:
    """Write a real ``<convention>.convention.yaml`` node under the extension tree."""
    node_dir = project_root / ".atdd" / "extensions" / ext_id / "0.1.0" / "conventions"
    node_dir.mkdir(parents=True, exist_ok=True)
    node = node_dir / f"{convention}.convention.yaml"
    node.write_text(
        "schema_version: '1.0.0'\nkind: convention\n"
        f"convention_id: {convention}\nmetadata:\n  severity: 2\n  disposition: strict\n",
        encoding="utf-8",
    )
    return node


_CONVENTION_NODE = """\
schema_version: '1.0.0'
kind: convention
convention_id: acme.rule.owned
metadata:
  severity: 2
  disposition: strict
"""


def build_enforce_substrate(tmp_path: Path, *, detector_in_extension: bool) -> Path:
    """Vendor a real workspace provider + one detector (in the extension or the
    workspace tree), bind it in binding.lock, and drop a consumer tree to scan.

    Mirrors the #1359 real-substrate builder: the provider ``cli/scan.py`` is the
    actual subprocess boundary and the detector is discovered + subprocessed by the
    real runner — no mocks. ``enforce`` reads the binding lock and rglobs the vendored
    trees; it never verifies substrate digests, so the impl files may be dropped into
    the package after install.
    """
    atdd = tmp_path / ".atdd"
    ws = atdd / "workspaces" / "atdd.workspace.python-pytest" / "0.1.0"
    (ws / "cli").mkdir(parents=True)
    (ws / "cli" / "scan.py").write_text(PROVIDER_CLI, encoding="utf-8")
    (ws / "atdd.workspace.yaml").write_text(
        "schema_version: '1.0.0'\nkind: workspace\n"
        "workspace_id: atdd.workspace.python-pytest\ncontract_version: '1.1.0'\n",
        encoding="utf-8",
    )

    ext = atdd / "extensions" / "acme.extension.rules" / "0.1.0"
    (ext / "conventions").mkdir(parents=True)
    (ext / "conventions" / "acme.rule.owned.convention.yaml").write_text(
        _CONVENTION_NODE, encoding="utf-8"
    )

    home = ext if detector_in_extension else ws
    impl = home / "implementations" / "owned_detector"
    impl.mkdir(parents=True)
    (impl / "atdd.implementation.yaml").write_text(
        "schema_version: '1.1.0'\nkind: implementation\n"
        "implementation_id: acme.rule.owned\n"
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
        "  implementation_id: acme.rule.owned\n"
        "  workspace_id: atdd.workspace.python-pytest\n  contract_version: 1.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer").mkdir()
    (tmp_path / "consumer" / "bad.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def write_binding_lock(project_root: Path, conventions: list[dict]) -> Path:
    """Write a minimal ``.atdd/binding.lock.yaml`` with the given convention entries."""
    import yaml

    atdd = project_root / ".atdd"
    atdd.mkdir(parents=True, exist_ok=True)
    lock = {"schema_version": "1.0.0", "conventions": conventions}
    dest = atdd / "binding.lock.yaml"
    dest.write_text(yaml.safe_dump(lock, sort_keys=False), encoding="utf-8")
    return dest
