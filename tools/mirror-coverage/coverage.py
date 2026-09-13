#!/usr/bin/env python3
"""Twin coverage of the core coder/tester convention surface (#1714 slice 1).

Answers the one number #1993 named as its ready-to-start condition: how many core
coder/tester rule_ids have an extension node that mirrors them, and how many have
none at all. Every figure is read through the shipped loader, never a hand-rolled
YAML reader:

  * core surface      — ``atdd.coach.utils.rule_binding.extract_rules``, which walks
    nested ``rules:`` lists (``canonical_rules.rules[]`` in coder/logging is invisible
    to a depth-1 reader; that omission is what understated the corpus in #1969).
  * twin provenance   — ``atdd.enforce.registry.iter_extension_nodes``, which reads
    ``source.legacy_rule_id`` off the raw node document. ``extract_rules`` cannot be
    used for this: ``single_node_rule_dict`` drops ``source`` entirely, so provenance
    keyed off its output reads as absent on every node.
  * mirror coherence  — ``atdd.enforce.registry.find_mirror_incoherences``.

A rule is COVERED when an extension node mirrors it, or when it carries a why-not row
in the classification record (``--classification``). Exits non-zero when any rule is
neither — the no-silent-drop condition #1714 must reach before #1993 may move a rule.

    python3 tools/mirror-coverage/coverage.py
    python3 tools/mirror-coverage/coverage.py --json
    python3 tools/mirror-coverage/coverage.py --classification docs/1714-agnostic-mirror-coverage.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from atdd.coach.utils.rule_binding import extract_rules  # noqa: E402
from atdd.enforce.registry import (  # noqa: E402
    find_mirror_incoherences,
    iter_extension_nodes,
)

# A why-not row names its rule in a leading backtick-quoted cell.
_WHY_NOT_ROW = re.compile(r"^\|\s*`((?:coder|tester)\.[a-z0-9.\-]+)`\s*\|")


def core_coder_tester_rules(root: Path) -> dict[str, dict]:
    """Every coder/tester rule_id declared under ``src/atdd/{coder,tester}/conventions``."""
    out: dict[str, dict] = {}
    for archetype in ("coder", "tester"):
        conventions = root / "src" / "atdd" / archetype / "conventions"
        for path in sorted(conventions.rglob("*.convention.yaml")):
            kind = "node" if f"{conventions.name}/nodes/" in str(path) else "monolith"
            for file_path, _yaml_path, rule in extract_rules(path):
                rule_id = rule.get("id")
                if isinstance(rule_id, str):
                    out[rule_id] = {
                        "kind": kind,
                        "disposition": rule.get("disposition") or "unset",
                        "severity": rule.get("severity"),
                        "source": str(file_path.relative_to(root)),
                    }
    return out


def twins_by_core_rule(root: Path) -> dict[str, list[str]]:
    """Core rule_id -> the extension node rule_ids declaring it as ``legacy_rule_id``."""
    twins: dict[str, list[str]] = defaultdict(list)
    for node in iter_extension_nodes(root):
        if node.legacy_rule_id:
            twins[node.legacy_rule_id].append(node.rule_id)
    return dict(twins)


def classified_rules(path: Path) -> set[str]:
    """Rule_ids carrying a why-not row in the classification record."""
    if not path.is_file():
        return set()
    return {
        m.group(1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := _WHY_NOT_ROW.match(line.strip()))
    }


def family(rule_id: str) -> str:
    return ".".join(rule_id.split(".")[:2])


def measure(root: Path, classification: Path | None) -> dict:
    core = core_coder_tester_rules(root)
    twins = twins_by_core_rule(root)
    classified = classified_rules(classification) if classification else set()

    twinned = sorted(r for r in core if r in twins)
    twinless = sorted(r for r in core if r not in twins)
    uncovered = sorted(r for r in twinless if r not in classified)

    nodes = list(iter_extension_nodes(root))
    incoherences = find_mirror_incoherences(root)
    return {
        "core_coder_tester_rule_ids": len(core),
        "twinned": twinned,
        "twinless": twinless,
        "classified_why_not": sorted(classified & set(twinless)),
        "uncovered": uncovered,
        "extension_nodes": len(nodes),
        "extension_nodes_with_provenance": sum(1 for n in nodes if n.legacy_rule_id),
        "mirror_incoherences": [
            {
                "extension_rule_id": m.extension_rule_id,
                "legacy_rule_id": m.legacy_rule_id,
                "extension": str(m.node_path).split("/.atdd/extensions/")[-1].split("/")[0],
            }
            for m in incoherences
        ],
        "twinless_by_family": {
            fam: sorted(rules)
            for fam, rules in sorted(
                ((f, [r for r in twinless if family(r) == f]) for f in {family(r) for r in twinless}),
                key=lambda kv: (-len(kv[1]), kv[0]),
            )
        },
        "core": core,
    }


def render(result: dict) -> str:
    core_n = result["core_coder_tester_rule_ids"]
    lines = [
        "core coder/tester twin coverage — measured through the shipped loader",
        "=" * 72,
        f"core coder/tester rule_ids          : {core_n}",
        f"  TWINNED (an extension mirrors it) : {len(result['twinned'])}",
        f"  TWINLESS (no mirror at all)       : {len(result['twinless'])}",
        f"    of those, why-not classified    : {len(result['classified_why_not'])}",
        f"    UNCOVERED (silent-drop risk)    : {len(result['uncovered'])}",
        "",
        f"extension nodes under .atdd/        : {result['extension_nodes']}",
        f"  declaring source.legacy_rule_id   : {result['extension_nodes_with_provenance']}",
        f"  mirror-coherence failures         : {len(result['mirror_incoherences'])}",
        "",
        f"TWINLESS by family ({len(result['twinless_by_family'])} families):",
    ]
    core = result["core"]
    for fam, rules in result["twinless_by_family"].items():
        kinds = Counter(core[r]["kind"] for r in rules)
        disp = Counter(core[r]["disposition"] for r in rules)
        lines.append(
            f"  {fam:<34} {len(rules):>3}   "
            f"[{','.join(f'{k}={v}' for k, v in sorted(kinds.items()))}]  "
            f"[{','.join(f'{k}={v}' for k, v in sorted(disp.items()))}]"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--classification",
        type=Path,
        default=None,
        help="classification record whose why-not rows cover a twinless rule",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = measure(args.root.resolve(), args.classification)
    if args.as_json:
        payload = {k: v for k, v in result.items() if k != "core"}
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render(result))
    return 1 if result["uncovered"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
