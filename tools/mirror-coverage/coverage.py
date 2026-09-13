#!/usr/bin/env python3
"""Twin coverage of the core coder/tester convention surface (#1714 slice 1).

Answers the one number #1993 named as its ready-to-start condition: how many core
coder/tester rule_ids have an extension node mirroring them, how many were
adjudicated in the classification record, and how many have neither.

Every figure comes from :mod:`atdd.enforce.twin_coverage`, the shipped measure
pinned by wmbt:govern-registry:E003 — this script adds a report and an exit code,
and computes nothing of its own. A second implementation of the measurement would
be a second answer to drift from; that is the mistake this program is about.

    python3 tools/mirror-coverage/coverage.py
    python3 tools/mirror-coverage/coverage.py --json
    python3 tools/mirror-coverage/coverage.py --classification <record.md>

Exits 0 only when every core coder/tester rule is covered — the no-silent-drop
condition. Exits 1 otherwise, naming the shortfall by family.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from atdd.enforce.registry import find_mirror_incoherences, iter_extension_nodes  # noqa: E402
from atdd.enforce.twin_coverage import (  # noqa: E402
    CLASSIFICATION_RECORD,
    COVERED_BY_RECORD,
    COVERED_BY_TWIN,
    core_coder_tester_surface,
    measure_twin_coverage,
    twins_by_core_rule,
    why_not_verdicts,
)


def family(rule_id: str) -> str:
    return ".".join(rule_id.split(".")[:2])


def render(root: Path, record: Path) -> tuple[str, int]:
    """The report, and the exit code the shortfall implies."""
    surface = core_coder_tester_surface(root)
    coverage = measure_twin_coverage(
        surface, twins=twins_by_core_rule(root), why_not=why_not_verdicts(record)
    )
    by_source = Counter(record_.covered_by for record_ in coverage.covered)
    nodes = list(iter_extension_nodes(root))

    lines = [
        "core coder/tester twin coverage — via atdd.enforce.twin_coverage",
        "=" * 72,
        f"core coder/tester rule_ids          : {len(coverage.core_surface)}",
        f"  covered by an extension twin      : {by_source[COVERED_BY_TWIN]}",
        f"  covered by a why-not verdict      : {by_source[COVERED_BY_RECORD]}",
        f"  UNCOVERED (silent-drop risk)      : {len(coverage.uncovered)}",
        f"  move-ready                        : {coverage.move_ready}",
        "",
        f"extension nodes under .atdd/        : {len(nodes)}",
        f"  declaring source.legacy_rule_id   : {sum(1 for n in nodes if n.legacy_rule_id)}",
        f"  mirror-coherence failures         : {len(find_mirror_incoherences(root))}",
    ]

    if coverage.uncovered:
        by_family: dict[str, list[str]] = defaultdict(list)
        for rule_id in coverage.uncovered:
            by_family[family(rule_id)].append(rule_id)
        lines += ["", f"UNCOVERED by family ({len(by_family)} families):"]
        for fam, rules in sorted(by_family.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            kinds = Counter(surface[r].kind for r in rules)
            disp = Counter(surface[r].disposition for r in rules)
            lines.append(
                f"  {fam:<34} {len(rules):>3}   "
                f"[{','.join(f'{k}={v}' for k, v in sorted(kinds.items()))}]  "
                f"[{','.join(f'{k}={v}' for k, v in sorted(disp.items()))}]"
            )

    return "\n".join(lines), (0 if coverage.move_ready else 1)


def as_json(root: Path, record: Path) -> tuple[str, int]:
    coverage = measure_twin_coverage(
        core_coder_tester_surface(root),
        twins=twins_by_core_rule(root),
        why_not=why_not_verdicts(record),
    )
    payload = {
        "core_surface": list(coverage.core_surface),
        "covered": [
            {"rule_id": r.rule_id, "covered_by": r.covered_by, "twins": list(r.twins)}
            for r in coverage.covered
        ],
        "uncovered": list(coverage.uncovered),
        "move_ready": coverage.move_ready,
    }
    return json.dumps(payload, indent=2, sort_keys=True), (0 if coverage.move_ready else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--classification",
        type=Path,
        default=None,
        help=f"classification record (default: <root>/{CLASSIFICATION_RECORD})",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    root = args.root.resolve()
    record = args.classification if args.classification is not None else root / CLASSIFICATION_RECORD
    text, code = (as_json if args.as_json else render)(root, record)
    print(text)
    return code
if __name__ == "__main__":
    raise SystemExit(main())
