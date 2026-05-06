"""``atdd validate --diagnostics-only`` reader (issue #449).

Reads the most recent ``.atdd/diagnostics/validation/<phase>.yaml``
artifact and prints a stdout summary mirroring the format produced by the
diagnostics plugin's session-finish hook. Designed to complete in
<100 ms (no pytest invocation, no validator collection).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from atdd.coach.utils.repo import find_repo_root


def diagnostics_path(repo_root: Path, phase: str) -> Path:
    return repo_root / ".atdd" / "diagnostics" / "validation" / f"{phase}.yaml"


def print_latest_diagnostics(
    phase: str = "all",
    repo_root: Optional[Path] = None,
) -> int:
    """Read + print the diagnostics artifact for *phase*. Exit 0 on success.

    Returns 1 if the artifact does not exist (no prior run, or
    --no-diagnostics was used). Returns 2 on YAML parse error.
    """
    root = repo_root or find_repo_root()
    artifact = diagnostics_path(root, phase)

    if not artifact.exists():
        print(
            f"No diagnostics artifact at {artifact.relative_to(root)}.\n"
            f"Run: atdd validate {phase} --local"
        )
        return 1

    try:
        document = yaml.safe_load(artifact.read_text()) or {}
    except yaml.YAMLError as exc:
        print(f"Failed to parse diagnostics artifact at {artifact}: {exc}")
        return 2

    _print_summary(document, artifact, root)
    return 0


def _print_summary(document: Dict[str, Any], artifact_path: Path, repo_root: Path) -> None:
    schema_version = document.get("schema_version")
    if schema_version != 1:
        print(
            f"Warning: diagnostics artifact has schema_version={schema_version} "
            f"(this CLI understands v1). Output may be incomplete."
        )

    run = document.get("run") or {}
    findings: List[Dict[str, Any]] = list(document.get("findings") or [])
    toolkit_issues: List[Dict[str, Any]] = list(document.get("toolkit_packaging_issues") or [])
    outcome = run.get("outcome") or {}

    print(f"=== DIAGNOSTICS — {run.get('phase', '?')} (ran_at={run.get('ran_at', '?')}) ===")
    print(
        f"  outcome: passed={outcome.get('passed', 0)}, "
        f"failed={outcome.get('failed', 0)}, "
        f"skipped={outcome.get('skipped', 0)}, "
        f"deselected={outcome.get('deselected', 0)}"
    )
    print(f"  duration: {run.get('duration_seconds', 0)}s, atdd_version: {run.get('atdd_version', '?')}")

    if not findings:
        print("\nNo findings recorded.")
        try:
            rel = artifact_path.relative_to(repo_root)
        except ValueError:
            rel = artifact_path
        print(f"\nFull diagnostics: {rel}")
        return

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for f in findings:
        by_category.setdefault(f.get("category", "unmigrated"), []).append(f)

    print(f"\n{len(findings)} finding(s), {len(by_category)} categories:")
    for category in sorted(by_category):
        bucket = by_category[category]
        item_total = sum(max(len(f.get("items") or []), 1) for f in bucket)
        suffix_findings = "s" if len(bucket) != 1 else " "
        suffix_items = "s" if item_total != 1 else ""
        print(
            f"  [{category:<14}] {len(bucket):>2} finding{suffix_findings},"
            f" {item_total:>3} item{suffix_items}"
        )

    print("\nTop fixes (sorted by category, capped at 10):")
    printed = 0
    for category in sorted(by_category):
        for finding in by_category[category]:
            if printed >= 10:
                break
            items = finding.get("items") or []
            if items:
                item = items[0]
                location = item.get("file") or "(no file)"
                if item.get("line"):
                    location = f"{location}:{item['line']}"
                fix_text = item.get("fix") or finding.get("summary", "")
                print(f"  {location}\n    {fix_text}")
                printed += 1
            else:
                vp = finding.get("validator_path") or "unknown"
                print(f"  ({vp})\n    {finding.get('summary', '')}")
                printed += 1
        if printed >= 10:
            break

    try:
        rel = artifact_path.relative_to(repo_root)
    except ValueError:
        rel = artifact_path
    print(f"\nFull diagnostics: {rel} ({len(findings)} finding(s))")
    if toolkit_issues:
        print(f"Toolkit packaging issues: {len(toolkit_issues)} (see file)")


__all__ = ["diagnostics_path", "print_latest_diagnostics"]
