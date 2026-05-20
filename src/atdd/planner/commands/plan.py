"""atdd plan — CLI shell for the planning brief entry point (PLAN-1).

Parses sources and flags; dispatches to the brief renderer (PLAN-7).
This module owns no git, issue, or PR mechanics.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_FILE_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}


@dataclass
class SourceItem:
    type: str
    value: Optional[str] = None
    path: Optional[str] = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd plan",
        description=(
            "Render a deterministic planning brief from source material.\n\n"
            "Source detection:\n"
            "  --text STR      Raw text inlined directly.\n"
            "  file.md/.txt/.yaml/.yml/.json  File adapter (PLAN-6 reads content).\n"
            "  file.pdf/other  Rich document: path referenced, no extraction.\n"
            "  dir / .         Codebase evidence bundle (PLAN-6 traverses).\n\n"
            "Exit 2 if no sources are supplied."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "sources",
        nargs="*",
        metavar="source",
        help="Source paths to include in the brief.",
    )
    parser.add_argument(
        "--text",
        metavar="TEXT",
        help="Raw text to inline as a source.",
    )
    parser.add_argument(
        "--brief-out",
        metavar="PATH",
        help="Write the rendered brief to PATH (default: stdout).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON summary to stderr.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output.",
    )
    return parser


def _classify_path(raw: str) -> SourceItem:
    p = Path(raw)
    suffix = p.suffix.lower()
    if suffix in _FILE_EXTENSIONS:
        return SourceItem(type="file", path=raw)
    if suffix:
        return SourceItem(type="rich_doc", path=raw)
    return SourceItem(type="codebase", path=raw)


def classify_sources(args: argparse.Namespace) -> list[SourceItem]:
    items: list[SourceItem] = []
    for raw in (args.sources or []):
        items.append(_classify_path(raw))
    if args.text:
        items.append(SourceItem(type="text", value=args.text))
    return items


def run(args: argparse.Namespace) -> int:
    sources = classify_sources(args)

    if not sources:
        build_parser().print_help()
        return 2

    brief_out = args.brief_out or "-"

    if args.json:
        summary = {
            "sources": [
                {k: v for k, v in vars(s).items() if v is not None}
                for s in sources
            ],
            "brief_out": brief_out,
        }
        print(json.dumps(summary), file=sys.stderr)

    return 0
