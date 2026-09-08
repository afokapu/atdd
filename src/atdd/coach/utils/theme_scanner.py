"""
Pre-init theme scanner (issue #291, Decision #7).

Walks a consumer repo BEFORE `atdd init --themes custom` prompts, and
returns three buckets:

- detected       : distinct `theme:` values seen in `plan/**/*.yaml`
                   (primary, high-confidence — prompt pre-selects).
- low_confidence : candidate domain tokens from top-level directories
                   and package-manifest keywords (secondary — prompt
                   shows as suggestions, never auto-selects).
- force_fits     : wagons whose slug tokens do not overlap with their
                   assigned theme's synonym set (e.g. `authenticate-
                   users` tagged `theme: commons` — natural fit would
                   be `security`, which does not exist in built-ins).

URN: coach:utils:theme_scanner
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import yaml


# Theme → synonym set for the force-fit heuristic.
# A wagon whose slug has no token overlap with its assigned theme's
# synonyms is considered force-fit. Custom themes not in this dict are
# skipped (no ground truth to reason about).
_THEME_SYNONYMS: Dict[str, Set[str]] = {
    "commons": {
        "commons", "common", "shared", "base", "core",
        "util", "utility", "general",
    },
    "mechanic": {
        "mechanic", "mechanics", "rule", "rules", "engine",
        "action", "compute",
    },
    "scenario": {
        "scenario", "scenarios", "story", "storyline", "flow",
        "journey",
    },
    "match": {
        "match", "matches", "game", "session", "round", "turn",
    },
    "sensory": {
        "sensory", "sense", "audio", "sound", "haptic", "visual",
        "vfx", "sfx", "render",
    },
    "player": {
        "player", "players", "user", "users", "avatar", "account",
        "profile",
    },
    "league": {
        "league", "leagues", "tournament", "season", "ranking",
        "standings",
    },
    "audience": {
        "audience", "spectator", "viewer", "broadcast", "stream",
        "chat",
    },
    "monetization": {
        "monetization", "monetize", "pay", "payment", "billing",
        "subscription", "checkout", "invoice",
    },
    "partnership": {
        "partnership", "partner", "partners", "affiliate", "sponsor",
        "integration",
    },
}


_KEBAB_TOKEN_SPLIT = re.compile(r"-+")


@dataclass(frozen=True)
class ForceFit:
    """A wagon whose slug tokens do not overlap with its theme's synonym set."""

    wagon: str
    theme: str
    reason: str = ""


@dataclass
class ScanResult:
    detected: List[str] = field(default_factory=list)
    low_confidence: List[str] = field(default_factory=list)
    force_fits: List[ForceFit] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Primary source — plan/**/*.yaml
# ---------------------------------------------------------------------------


def _walk_plan_yaml(plan_dir: Path) -> Iterable[Path]:
    if not plan_dir.is_dir():
        return []
    return sorted(plan_dir.rglob("*.yaml"))


def _load_yaml_safely(path: Path) -> Optional[dict]:
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        return None
    return doc if isinstance(doc, dict) else None


def _collect_plan_themes(
    plan_dir: Path,
) -> tuple[List[str], List[ForceFit]]:
    """Return (detected_themes_in_order, force_fits) from plan/ tree."""
    detected_order: List[str] = []
    seen: Set[str] = set()
    force_fits: List[ForceFit] = []

    for path in _walk_plan_yaml(plan_dir):
        doc = _load_yaml_safely(path)
        if doc is None:
            continue

        theme = doc.get("theme")
        if not isinstance(theme, str) or not theme:
            continue

        if theme not in seen:
            seen.add(theme)
            detected_order.append(theme)

        wagon_slug = doc.get("wagon")
        if isinstance(wagon_slug, str) and wagon_slug:
            if _is_force_fit(wagon_slug, theme):
                force_fits.append(
                    ForceFit(
                        wagon=wagon_slug,
                        theme=theme,
                        reason=(
                            f"wagon slug tokens do not overlap with "
                            f"`{theme}` synonyms"
                        ),
                    )
                )

    return detected_order, force_fits


def _is_force_fit(wagon_slug: str, theme: str) -> bool:
    """True when wagon slug tokens do not overlap with theme synonyms."""
    synonyms = _THEME_SYNONYMS.get(theme)
    if synonyms is None:
        # Custom theme — no ground truth for overlap check.
        return False
    tokens = set(_KEBAB_TOKEN_SPLIT.split(wagon_slug))
    return not tokens.intersection(synonyms)


# ---------------------------------------------------------------------------
# Secondary source — low-confidence candidates from repo metadata
# ---------------------------------------------------------------------------


_IGNORED_TOP_LEVEL_DIRS: Set[str] = {
    ".git", ".github", ".atdd", ".venv", ".idea", ".vscode",
    "node_modules", "__pycache__", "dist", "build", "target",
    "venv", "env", "tests", "test", "docs", "src", "web",
    "plan",  # plan is the primary source, not a candidate
}


def _collect_top_level_dir_candidates(repo_root: Path) -> List[str]:
    out: List[str] = []
    if not repo_root.is_dir():
        return out
    for child in sorted(repo_root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name in _IGNORED_TOP_LEVEL_DIRS:
            continue
        if re.match(r"^[a-z][a-z0-9-]*$", name):
            out.append(name)
        elif re.match(r"^[a-z][a-z0-9_]*$", name):
            out.append(name.replace("_", "-"))
    return out


def _collect_pyproject_keywords(repo_root: Path) -> List[str]:
    path = repo_root / "pyproject.toml"
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        return []

    # Minimal keyword extraction: parse the `keywords = [...]` array.
    # Avoids hard-depending on tomllib / tomli to keep this helper
    # dependency-free.
    match = re.search(
        r"^\s*keywords\s*=\s*\[(?P<body>[^\]]*)\]",
        text,
        re.MULTILINE,
    )
    if not match:
        return []
    tokens = re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group("body"))
    return [a or b for a, b in tokens if (a or b)]


def _collect_package_json_keywords(repo_root: Path) -> List[str]:
    path = repo_root / "package.json"
    if not path.exists():
        return []
    try:
        import json

        data = json.loads(path.read_text())
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        return []
    keywords = data.get("keywords") if isinstance(data, dict) else None
    if not isinstance(keywords, list):
        return []
    return [str(k) for k in keywords if isinstance(k, str) and k]


def _collect_low_confidence(repo_root: Path) -> List[str]:
    candidates: List[str] = []
    candidates.extend(_collect_top_level_dir_candidates(repo_root))
    candidates.extend(_collect_pyproject_keywords(repo_root))
    candidates.extend(_collect_package_json_keywords(repo_root))

    # Dedupe while preserving order and kebab-case shape.
    seen: Set[str] = set()
    out: List[str] = []
    for c in candidates:
        norm = str(c).strip().lower()
        if not norm or not re.match(r"^[a-z][a-z0-9-]*$", norm):
            continue
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def scan_existing_themes(repo_root: Path) -> ScanResult:
    """
    Scan `repo_root` for theme signals.

    Primary source  : `plan/**/*.yaml` → detected + force_fits
    Secondary source: top-level dir names + pyproject/package manifests
                      → low_confidence (only when primary is empty or
                      as supplementary suggestions).

    Tolerates missing directories, malformed YAML, and repos with no
    package manifest — always returns a well-formed ScanResult.
    """
    repo_root = Path(repo_root)

    detected, force_fits = _collect_plan_themes(repo_root / "plan")
    low_confidence = _collect_low_confidence(repo_root)

    # Exclude low-confidence tokens that duplicate detected entries so
    # the prompt does not show the same token twice.
    detected_set = set(detected)
    low_confidence = [lc for lc in low_confidence if lc not in detected_set]

    return ScanResult(
        detected=detected,
        low_confidence=low_confidence,
        force_fits=force_fits,
    )
