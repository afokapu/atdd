# URN: component:govern-lifecycle:enforcement:RouteTrainWagonAnalyzer:backend:application
# Runtime: python
# Purpose: Resolve <TrainView trainId="..."/> bindings against plan/_trains.yaml
#          and plan/_wagons.yaml; emit BOUNDARIES-ROUTE-COVERAGE-NNN Violations.

"""
Route → Train → Wagon coverage analyzer.

Layered shape (refactored under #333 Phase 4):

* DOMAIN       — ``TrainIdBinding`` dataclass, rule_id constants, severity
                 constants. No I/O, no framework imports.
* APPLICATION  — ``parse_trainview_bindings``, ``analyze_router_content``.
                 Pure functions over strings + dicts; no filesystem access.
* INTEGRATION  — ``load_registered_trains``, ``load_registered_wagons``,
                 ``analyze_router_file``. Reads YAML and TSX from disk.
* FAÇADE       — ``RouteTrainWagonAnalyzer``. Stateful binding for the
                 orchestration layer (``test_route_train_wagon_coverage.py``)
                 and SMOKE tests (``e2e/0001-self-compliance-validate``).

Phase 2 (GREEN) implemented the parser as regex per Decision #1. The
TypeScript AST rewrite is tracked as a follow-up to issue #333; not in
scope here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from atdd.coach.validators._violation import Violation


logger = logging.getLogger(__name__)


# ===========================================================================
# DOMAIN LAYER
# ===========================================================================

# Rule constants — single source of truth, re-exported by the validator file
# and mirrored in frontend.convention.yaml::route_train_wagon_coverage.
RULE_UNREGISTERED_TRAIN = "BOUNDARIES-ROUTE-COVERAGE-001"
RULE_UNREGISTERED_WAGON = "BOUNDARIES-ROUTE-COVERAGE-002"
RULE_DYNAMIC_TRAIN_ID = "BOUNDARIES-ROUTE-COVERAGE-003"

# Severities per rule-id.convention.yaml::severity_scale.
SEVERITY_ARCHITECTURAL = 3   # tier 3 — URN markers, layer boundaries
SEVERITY_ADVISORY = 1        # tier 1 — style nits, ordering preferences


@dataclass(frozen=True)
class TrainIdBinding:
    """A single ``<TrainView trainId={...}>`` occurrence inside a router file.

    ``raw`` is the original source text (literal contents or expression).
    ``resolved`` is the literal trainId after resolving same-file ``const``
    declarations; ``None`` means UNKNOWN (Decision #4: never hard-fail).
    """

    line: int
    raw: str
    resolved: Optional[str]


# ===========================================================================
# APPLICATION LAYER (pure — no I/O)
# ===========================================================================

# Regex catalogue for the lightweight TSX scanner (Decision #1).
_TRAINVIEW_TAG_RE = re.compile(
    r"<TrainView\b(?P<attrs>[^>]*?)/?>",
    re.DOTALL,
)
_TRAINID_LITERAL_RE = re.compile(r'trainId\s*=\s*"([^"]*)"')
_TRAINID_EXPR_RE = re.compile(r"trainId\s*=\s*\{([^}]+)\}")
_BARE_IDENT_RE = re.compile(r"^[A-Za-z_][\w]*$")
_CONST_STRING_RE = re.compile(r'\bconst\s+(\w+)\s*(?::\s*\w+)?\s*=\s*"([^"]*)"')

# Strip TS/JSX comments before scanning so a `// <TrainView ... />` example
# inside a doc comment isn't reported as a real route. Newlines are preserved
# so byte offsets still map to the original line numbers.
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _line_of(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


def _blank_keep_newlines(match: re.Match) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _strip_comments(content: str) -> str:
    """Replace TS/JSX line + block comments with spaces (newlines preserved).

    The replacement keeps every byte offset stable so ``_line_of(...)``
    continues to report the original source line.
    """
    content = _BLOCK_COMMENT_RE.sub(_blank_keep_newlines, content)
    content = _LINE_COMMENT_RE.sub(_blank_keep_newlines, content)
    return content


def _resolve_const_in_file(name: str, content: str) -> Optional[str]:
    for m in _CONST_STRING_RE.finditer(content):
        if m.group(1) == name:
            return m.group(2)
    return None


def parse_trainview_bindings(content: str) -> List[TrainIdBinding]:
    """Return one binding per ``<TrainView ...>`` occurrence in *content*.

    A ``trainId`` attribute is one of:

    * ``trainId="literal"`` → ``resolved=literal``
    * ``trainId={IDENT}`` where ``IDENT`` matches a same-file
      ``const IDENT[: T] = "literal"`` → ``resolved=literal``
    * any other ``trainId={...}`` (member access, prop drill, call,
      ternary, ...) → ``resolved=None`` (UNKNOWN)

    Tags without a ``trainId`` attribute are skipped — that case is
    governed by SPEC-CODER-PAGE-0004 (presence of ``<TrainView>``), not
    by this validator.
    """
    sanitized = _strip_comments(content)
    bindings: List[TrainIdBinding] = []
    for m in _TRAINVIEW_TAG_RE.finditer(sanitized):
        attrs = m.group("attrs")
        line = _line_of(sanitized, m.start())

        lit = _TRAINID_LITERAL_RE.search(attrs)
        if lit:
            value = lit.group(1)
            bindings.append(TrainIdBinding(line=line, raw=value, resolved=value))
            continue

        expr = _TRAINID_EXPR_RE.search(attrs)
        if expr:
            raw = expr.group(1).strip()
            resolved: Optional[str] = None
            if _BARE_IDENT_RE.match(raw):
                resolved = _resolve_const_in_file(raw, sanitized)
            bindings.append(TrainIdBinding(line=line, raw=raw, resolved=resolved))
            continue
    return bindings


def analyze_router_content(
    rel_path: str,
    content: str,
    registered_trains: Dict[str, List[str]],
    registered_wagons: Set[str],
) -> List[Violation]:
    """Pure analyzer: raw content + resolved plan → ``Violation`` list.

    Kept content-based (not path-based) so SMOKE tests can stand up
    synthetic tmp-tree routers without writing fixture files.
    """
    violations: List[Violation] = []
    for binding in parse_trainview_bindings(content):
        location = f"{rel_path}:{binding.line}"

        if binding.resolved is None:
            violations.append(Violation(
                rule_id=RULE_DYNAMIC_TRAIN_ID,
                severity=SEVERITY_ADVISORY,
                location=location,
                detail=(
                    f"trainId expression `{binding.raw}` cannot be statically "
                    f"resolved (UNKNOWN). Hard-fail suppressed by Decision #4; "
                    f"rendered verification belongs to issue #335."
                ),
            ))
            continue

        train_id = binding.resolved
        if train_id not in registered_trains:
            registered_list = ", ".join(sorted(registered_trains)) or "<none>"
            violations.append(Violation(
                rule_id=RULE_UNREGISTERED_TRAIN,
                severity=SEVERITY_ARCHITECTURAL,
                location=location,
                detail=(
                    f'trainId="{train_id}" is not registered in plan/_trains.yaml. '
                    f"Registered: [{registered_list}]"
                ),
            ))
            continue

        for wagon in registered_trains.get(train_id) or []:
            if wagon not in registered_wagons:
                violations.append(Violation(
                    rule_id=RULE_UNREGISTERED_WAGON,
                    severity=SEVERITY_ARCHITECTURAL,
                    location=location,
                    detail=(
                        f'train "{train_id}" lists wagon "{wagon}" which is '
                        f"not registered in plan/_wagons.yaml."
                    ),
                ))
    return violations


# ===========================================================================
# INTEGRATION LAYER (file I/O)
# ===========================================================================

def load_registered_trains(trains_file: Path) -> Dict[str, List[str]]:
    """Parse ``plan/_trains.yaml`` → ``{train_id: [wagon, ...]}``.

    Schema mirror of
    ``atdd.tester.validators.test_smoke_coverage.PlanTrainDiscovery.discover``
    but retains the per-train ``wagons:`` list which that loader discards.
    """
    if not trains_file.is_file():
        return {}
    try:
        data = yaml.safe_load(trains_file.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to load trains file %s: %s", trains_file, exc)
        return {}

    out: Dict[str, List[str]] = {}
    for theme in (data.get("trains") or {}).values():
        if not isinstance(theme, dict):
            continue
        for trains in theme.values():
            for train in trains or []:
                tid = train.get("train_id")
                if tid:
                    out[tid] = list(train.get("wagons") or [])
    return out


def load_registered_wagons(wagons_file: Path) -> Set[str]:
    """Parse ``plan/_wagons.yaml`` → ``{wagon_id, ...}``."""
    if not wagons_file.is_file():
        return set()
    try:
        data = yaml.safe_load(wagons_file.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to load wagons file %s: %s", wagons_file, exc)
        return set()

    out: Set[str] = set()
    for entry in data.get("wagons") or []:
        wid = entry.get("wagon")
        if wid:
            out.add(wid)
    return out


def analyze_router_file(
    router_path: Path,
    registered_trains: Dict[str, List[str]],
    registered_wagons: Set[str],
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """File-system entrypoint used by the validator and the inline RED tests.

    The location field on each Violation prefers ``router_path.relative_to(repo_root)``
    when *repo_root* is provided so failure messages stay short and stable
    across machines.
    """
    try:
        content = router_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read router %s: %s", router_path, exc)
        return []

    if repo_root is not None:
        try:
            rel_path = str(router_path.relative_to(repo_root))
        except ValueError:
            rel_path = str(router_path)
    else:
        rel_path = router_path.name

    return analyze_router_content(
        rel_path,
        content,
        registered_trains,
        registered_wagons,
    )


# ===========================================================================
# FAÇADE
# ===========================================================================

class RouteTrainWagonAnalyzer:
    """Stateful façade over the loaders + the pure analyzer.

    Used by orchestration tests and SMOKE tests that hit the real
    ``plan/_trains.yaml`` + ``plan/_wagons.yaml`` files. Loaders run once
    per instance via the cached properties so the per-router scan costs
    one YAML parse, not N.
    """

    def __init__(self, trains_file: Path, wagons_file: Path) -> None:
        self._trains_file = trains_file
        self._wagons_file = wagons_file
        self._trains: Optional[Dict[str, List[str]]] = None
        self._wagons: Optional[Set[str]] = None

    @property
    def registered_trains(self) -> Dict[str, List[str]]:
        if self._trains is None:
            self._trains = load_registered_trains(self._trains_file)
        return self._trains

    @property
    def registered_wagons(self) -> Set[str]:
        if self._wagons is None:
            self._wagons = load_registered_wagons(self._wagons_file)
        return self._wagons

    def analyze(self, router_path: Path, repo_root: Path) -> List[Violation]:
        return analyze_router_file(
            router_path,
            self.registered_trains,
            self.registered_wagons,
            repo_root=repo_root,
        )


__all__ = [
    "RULE_UNREGISTERED_TRAIN",
    "RULE_UNREGISTERED_WAGON",
    "RULE_DYNAMIC_TRAIN_ID",
    "SEVERITY_ARCHITECTURAL",
    "SEVERITY_ADVISORY",
    "TrainIdBinding",
    "RouteTrainWagonAnalyzer",
    "analyze_router_content",
    "analyze_router_file",
    "load_registered_trains",
    "load_registered_wagons",
    "parse_trainview_bindings",
]
