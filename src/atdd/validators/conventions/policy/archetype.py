"""Reusable graph-question archetype for the `policy` family (#1204).

Real-graph execution (#1212): the `policy/forbidden_construct_absence` template is
executed against the REAL composed convention graph. The graph carries `.root`
(the repo root) and real `Node` objects; each policy variant scopes onto a concrete
slice of the real repo — WMBT acceptance nodes, convention freedom-layer data, hook
source files, or the suppression-marker corpus — and scans it for a forbidden
construct. There are no dict fixtures in the execution path: every scan reads the
real composed graph + the real files it points at.

Variants implemented here (planner+coach legacy decommission, #1212):

  * smoke_synthetic_fixture_bypass  (planner) — SMOKE acceptance test files must not
    use synthetic-fixture anti-patterns (FakeMultiplexer / stub cat|sleep|python
    Popen agent command / `_SYNTHETIC_AGENT` constant).
    Legacy: src/atdd/planner/validators/test_smoke_synthetic_fixture_bypass.py
  * no_stale_suppressions          (coach) — no `# atdd:suppress(<id>) UNTIL=<date>`
    marker may be past its deadline.
    Legacy: src/atdd/coach/validators/test_no_stale_suppressions.py
  * freedom_layer_bash_scope       (coach, E032) — every `spawn_time.freedom_layer`
    `allowed_bash` entry must be tightly scoped `Bash(<cmd>:*)` and must not
    pre-authorize any `forbidden_bash` command.
    Legacy: src/atdd/coach/validators/test_e032_smoke_001_live_freedom_layer_passes_flipped_validator.py
  * bypass_inventory               (coach, E026) — no `ATDD_SKIP_*` enforcement-bypass
    flag may appear in the git hook source files (audited baseline = 0).
    Legacy: src/atdd/coach/validators/test_e026_bypass_inventory_guard.py

CLAUDE.md-document variants (e022/r003) are deliberately excluded — they police the
operator document, not the convention graph, and are deferred to a separate issue.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import List, Mapping, Optional

from .._support.template_contract import TemplateContract

TEMPLATES = [
    TemplateContract(
        family_id='policy',
        template_id='forbidden_construct_absence',
        question='Are forbidden constructs, fields, edge types, commands, or legacy shapes absent?',
        selector='graph nodes/artifacts matched by a policy scope',
        traversal='scope -> scan nodes/fields/edges/artifacts -> forbidden matcher',
        invariant='forbidden match set is empty',
        auto_capture='usually explicit; a new node is included if it falls inside a policy scope',
        failure_evidence=['matched_construct', 'policy_id', 'location', 'reason', 'suggested_replacement'],
    ),
]

TEMPLATE_IDS = [t.template_id for t in TEMPLATES]


# ---------------------------------------------------------------------------
# Shared file-scan helpers (operate on the real repo via graph.root).
# ---------------------------------------------------------------------------
_SCAN_EXTENSIONS = (".py", ".ts", ".tsx")
_SKIP_DIR_NAMES = frozenset({
    "node_modules", "__pycache__", ".venv", "venv", "site-packages",
    ".tox", ".git", "dist", "build", ".next", ".turbo",
})


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


def _iter_scan_files(root: Path):
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SCAN_EXTENSIONS:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


# ---------------------------------------------------------------------------
# Variant: smoke_synthetic_fixture_bypass (planner parity)
# ---------------------------------------------------------------------------
_SMOKE_URN_RE = re.compile(r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$")
_STUB_COMMANDS = ("cat", "sleep", "python")
_FAKE_MUX_PATTERN = re.compile(r"FakeMultiplexer")
_SYNTHETIC_AGENT_PATTERN = re.compile(r"_SYNTHETIC_AGENT\s*=")
_STUB_POPEN_PATTERN = re.compile(
    r"""[Pp]open\s*\(\s*[\[\(]["'](?:""" + "|".join(_STUB_COMMANDS) + r""")["']"""
)
_SMOKE_SUPPRESS_PATTERN = re.compile(
    r"#\s*atdd:suppress\(planner\.smoke\.synthetic-fixture-bypass\)"
)
_SMOKE_POLICY_ID = "planner.smoke.synthetic-fixture-bypass"


def _is_smoke_acceptance(identity: Mapping) -> bool:
    urn = identity.get("urn", "")
    return identity.get("phase", "") == "SMOKE" or bool(_SMOKE_URN_RE.match(urn))


def _resolve_test_file_from_urn(urn: str, root: Path) -> Optional[Path]:
    parts = urn.split(":")
    if len(parts) < 3:
        return None
    segments = parts[2].split("-")
    if len(segments) < 3:
        return None
    prefix = f"test_{segments[0].lower()}_{segments[1].lower()}_{segments[2]}"
    for candidate in root.rglob(f"{prefix}*.py"):
        if candidate.name.startswith(prefix):
            return candidate
    return None


def _scan_smoke_synthetic_fixture_bypass(graph, config=None) -> List[dict]:
    root = Path(graph.root)
    out: List[dict] = []
    seen_files: set = set()
    for wmbt in graph.by_kind("wmbt"):
        for acc in (wmbt.fields.get("acceptances") or []):
            if not isinstance(acc, dict):
                continue
            identity = acc.get("identity", {}) or {}
            if not _is_smoke_acceptance(identity):
                continue
            urn = identity.get("urn", "")
            if not urn:
                continue
            test_file = _resolve_test_file_from_urn(urn, root)
            if test_file is None or not test_file.exists():
                continue
            key = (str(test_file), urn)
            if key in seen_files:
                continue
            seen_files.add(key)
            content = test_file.read_text(encoding="utf-8", errors="replace")
            if _SMOKE_SUPPRESS_PATTERN.search(content):
                continue
            loc = f"{_rel(root, test_file)}:1"
            if _FAKE_MUX_PATTERN.search(content):
                out.append({
                    "matched_construct": "FakeMultiplexer",
                    "policy_id": _SMOKE_POLICY_ID, "location": loc,
                    "reason": f"FakeMultiplexer in SMOKE test for {urn}; "
                              "SMOKE tests must drive the real CLI entry point.",
                    "suggested_replacement": "drive `atdd spawn` (real entry point)",
                })
            stub_match = _STUB_POPEN_PATTERN.search(content)
            if stub_match:
                stub_name = next((c for c in _STUB_COMMANDS if c in stub_match.group()), "stub")
                out.append({
                    "matched_construct": f"Popen stub '{stub_name}'",
                    "policy_id": _SMOKE_POLICY_ID, "location": loc,
                    "reason": f"subprocess.Popen with stub '{stub_name}' in SMOKE test "
                              f"for {urn}; SMOKE must drive the real atdd spawn path.",
                    "suggested_replacement": "drive the real atdd spawn path",
                })
            if _SYNTHETIC_AGENT_PATTERN.search(content):
                out.append({
                    "matched_construct": "_SYNTHETIC_AGENT",
                    "policy_id": _SMOKE_POLICY_ID, "location": loc,
                    "reason": f"_SYNTHETIC_AGENT constant in SMOKE test for {urn}; "
                              "embedded scripts bypass real adapter command construction.",
                    "suggested_replacement": "write agent scripts to tmp_path files",
                })
    return out


# ---------------------------------------------------------------------------
# Variant: no_stale_suppressions (coach parity)
# ---------------------------------------------------------------------------
_MARKER_PATTERN = re.compile(
    r"atdd:suppress\(([^)]+)\)(?:\s+UNTIL=(\d{4}-\d{2}-\d{2}))?",
)
_STALE_SCAN_ROOTS = ("python", "web/src", "supabase", "packages", "e2e", "src/atdd")
_STALE_POLICY_ID = "coach.rule-id.stale-suppression"


def _parse_until(raw: Optional[str]) -> Optional[date]:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _scan_no_stale_suppressions(graph, config=None) -> List[dict]:
    root = Path(graph.root)
    today = (config or {}).get("today") or date.today()
    roots = [root / r for r in _STALE_SCAN_ROOTS]
    out: List[dict] = []
    seen_files: set = set()
    for scan_root in roots:
        for path in _iter_scan_files(scan_root):
            if path in seen_files:
                continue
            seen_files.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for match in _MARKER_PATTERN.finditer(line):
                    rid = match.group(1).strip()
                    until = _parse_until(match.group(2))
                    if not rid or until is None or not (until < today):
                        continue
                    out.append({
                        "matched_construct": f"atdd:suppress({rid}) UNTIL={until.isoformat()}",
                        "policy_id": _STALE_POLICY_ID,
                        "location": f"{_rel(root, path)}:{lineno}",
                        "reason": f"suppression deadline UNTIL={until.isoformat()} is past",
                        "suggested_replacement": "fix the underlying violation or extend UNTIL=",
                    })
    return out


# ---------------------------------------------------------------------------
# Variant: freedom_layer_bash_scope (coach E032 parity)
# ---------------------------------------------------------------------------
_SCOPED_RE = re.compile(r"^Bash\((?P<cmd>[^()]+):\*\)$")
_SESSION_CONVENTION = "src/atdd/coach/conventions/session.convention.yaml"
_FREEDOM_POLICY_ID = "coach.freedom-layer.scoped-bash"


def _read_freedom_layer(root: Path) -> Optional[Mapping]:
    import yaml
    conv = root / _SESSION_CONVENTION
    if not conv.is_file():
        return None
    try:
        data = yaml.safe_load(conv.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    spawn = data.get("spawn_time") or {}
    fl = spawn.get("freedom_layer") if isinstance(spawn, dict) else None
    return fl if isinstance(fl, Mapping) else None


def _scan_freedom_layer_bash_scope(graph, config=None) -> List[dict]:
    root = Path(graph.root)
    fl = _read_freedom_layer(root)
    if fl is None:
        return []
    allowed_bash = list(fl.get("allowed_bash") or [])
    forbidden = list(fl.get("forbidden_bash") or [])
    out: List[dict] = []
    for entry in allowed_bash:
        match = _SCOPED_RE.match(entry)
        if match is None:
            out.append({
                "matched_construct": entry, "policy_id": _FREEDOM_POLICY_ID,
                "location": _SESSION_CONVENTION,
                "reason": "unscoped/over-broad Bash entry; every allowed_bash entry "
                          "must be tightly scoped Bash(<cmd>:*) "
                          "(never bare Bash, Bash(*), or Bash(:*))",
                "suggested_replacement": "scope as Bash(<cmd>:*)",
            })
            continue
        inner = match.group("cmd")
        for bad in forbidden:
            if inner == bad or inner.startswith(bad + " "):
                out.append({
                    "matched_construct": entry, "policy_id": _FREEDOM_POLICY_ID,
                    "location": _SESSION_CONVENTION,
                    "reason": f"forbidden command {bad!r} present in allowed_bash entry; "
                              "destructive/outward commands must never be pre-authorized",
                    "suggested_replacement": f"remove {bad!r} from allowed_bash",
                })
    return out


# ---------------------------------------------------------------------------
# Variant: bypass_inventory (coach E026 parity)
# ---------------------------------------------------------------------------
_HOOK_DIR = "src/atdd/coach/templates/hooks"
_HOOK_FILES = ("pre-push", "pre-commit", "post-commit", "commit-msg", "pre-merge-commit")
_BYPASS_PATTERN = re.compile(r"ATDD_SKIP_\w+")
_ADVISORY_PATTERN = re.compile(r"ATDD_MAX_\w+")
_CI_ONLY_PATTERN = re.compile(r"ATDD_ALLOW_MAIN_\w+")
_BYPASS_POLICY_ID = "coach.bypass.inventory-baseline-zero"


def _scan_bypass_inventory(graph, config=None) -> List[dict]:
    root = Path(graph.root)
    hooks_dir = root / _HOOK_DIR
    out: List[dict] = []
    for name in _HOOK_FILES:
        p = hooks_dir / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        seen: set = set()
        for match in _BYPASS_PATTERN.finditer(text):
            flag = match.group(0)
            if _ADVISORY_PATTERN.match(flag) or _CI_ONLY_PATTERN.match(flag):
                continue
            if flag in seen:
                continue
            seen.add(flag)
            out.append({
                "matched_construct": flag, "policy_id": _BYPASS_POLICY_ID,
                "location": f"{_HOOK_DIR}/{name}",
                "reason": f"enforcement-bypass flag {flag} present in hook source; "
                          "audited baseline is zero (all ATDD_SKIP_* retired, E030)",
                "suggested_replacement": "remove the flag; for emergencies use "
                                         "`atdd emergency --reason '<reason>'`",
            })
    return out


# ---------------------------------------------------------------------------
# Config-driven dispatch over the real composed graph.
# ---------------------------------------------------------------------------
_VARIANT_SCANNERS = {
    "smoke_synthetic_fixture_bypass": _scan_smoke_synthetic_fixture_bypass,
    "no_stale_suppressions": _scan_no_stale_suppressions,
    "freedom_layer_bash_scope": _scan_freedom_layer_bash_scope,
    "bypass_inventory": _scan_bypass_inventory,
}


def forbidden_construct_absence(graph, config=None) -> List[dict]:
    """Execute the `policy/forbidden_construct_absence` template against the real
    composed graph. ``config['variant']`` selects the policy scope; each scanner
    returns failure-evidence dicts whose keys are a subset of the template's
    declared ``failure_evidence``."""
    config = config or {}
    variant = config.get("variant")
    scanner = _VARIANT_SCANNERS.get(variant)
    if scanner is None:
        raise NotImplementedError(
            f"policy/forbidden_construct_absence: no scanner for variant {variant!r}; "
            f"known variants: {sorted(_VARIANT_SCANNERS)}"
        )
    return scanner(graph, config)


REAL_EVALUATORS = {"forbidden_construct_absence": forbidden_construct_absence}
