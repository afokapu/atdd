"""python-pytest detector for coder.presentation.i18n-config (+ .i18n-switcher).

Realizes two agnostic obligations (both disposition `strict`) for the web stack:
runtime localization code must derive its supported-locale list from the shared
locale manifest rather than hardcoding a locale array.

  * coder.presentation.i18n-config   — the i18n runtime config file imports the
    manifest instead of inlining `locales = ['en', ...]`.
  * coder.presentation.i18n-switcher — the language-switcher component sources its
    locale list from the shared `SUPPORTED_LOCALES`/manifest, not a literal array.

ONE run carries TWO distinct rule_ids — the v1.1 multi-rule output channel
(PROVIDER-CONTRACT-v1.1.md §3).

PROVENANCE — ported from core
    src/atdd/coder/validators/test_i18n_runtime.py
        :: scan_i18n_config / scan_language_switcher / _find_file /
           the hardcoded-array + manifest/shared regexes
    (origin/main @ 624d3afe, blob 3be3850675832d69). The regex detection and the
    candidate-path lists are copied verbatim; the ``atdd.coach.*`` couplings were
    REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_CONFIG`` / ``RULE_SWITCHER``
    constants. Authoritative metadata (severity 3; both strict) lives in the
    convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2).
  * ``find_repo_root`` + fixed ``web/`` root  -> REMOVED. Scan scope is supplied
    explicitly via ``ATDD_SCAN_ROOTS`` (§2); each scan root is treated as a
    ``web/``-equivalent directory (the same base ``_find_file`` resolved against).
  * ``locale_phase`` / ``locale_manifest`` fixture gating  -> NOT PORTED. "Is
    localization configured / enforced yet?" is a consumer scan-policy decision
    (whether to mount this detector at all), not detector logic. The detector
    always emits the RAW facts when a hardcoded array is present without a shared
    source.
  * ``assert_disposition_satisfied`` (ratchet baseline)  -> NOT PORTED; both
    rule_ids are strict, aggregated downstream by the consumer (§1).

Pure stdlib (``re``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

from pathlib import Path
import re

RULE_CONFIG = "coder.presentation.i18n-config"      # disposition: strict
RULE_SWITCHER = "coder.presentation.i18n-switcher"  # disposition: strict

# Candidate locations — copied verbatim from core (relative to a web/ root).
CONFIG_CANDIDATES = (
    "src/i18nConfig.ts", "src/i18n/config.ts", "src/i18n.ts",
    "src/lib/i18n.ts", "src/config/i18n.ts",
)
SWITCHER_CANDIDATES = (
    "src/components/LanguageSwitcher.tsx", "src/components/LocaleSwitcher.tsx",
    "src/components/ui/LanguageSwitcher.tsx", "src/components/common/LanguageSwitcher.tsx",
    "src/features/i18n/LanguageSwitcher.tsx",
)

# Hardcoded-array detectors + "uses the shared source" allow-lists (verbatim).
CONFIG_HARDCODED = re.compile(
    r"(?:locales|supportedLocales|SUPPORTED_LOCALES|languages)\s*[=:]\s*\[\s*['\"][a-z]{2}",
    re.IGNORECASE,
)
CONFIG_MANIFEST_PATTERNS = [
    r"from\s+['\"].*manifest", r"import.*manifest",
    r"require\s*\(\s*['\"].*manifest", r"SUPPORTED_LOCALES", r"getSupportedLocales",
]
SWITCHER_HARDCODED = re.compile(
    r"(?:locales|languages|options)\s*[=:]\s*\[\s*(?:\{[^}]*locale[^}]*['\"][a-z]{2}|['\"][a-z]{2})",
    re.IGNORECASE,
)
SWITCHER_SHARED_PATTERNS = [
    r"SUPPORTED_LOCALES", r"getSupportedLocales", r"from\s+['\"].*manifest",
    r"from\s+['\"].*i18n", r"from\s+['\"].*config", r"useLocales",
]


def _find_file(base_dir: Path, *candidates: str) -> Path | None:
    for rel in candidates:
        p = base_dir / rel
        if p.exists():
            return p
    return None


def _line_of(content: str, match: re.Match) -> int:
    return content.count("\n", 0, match.start()) + 1


def _line_text(content: str, line: int) -> str:
    lines = content.splitlines()
    return lines[line - 1] if 1 <= line <= len(lines) else ""


def scan_i18n_config(web_root: Path) -> list[dict]:
    """Emit a RULE_CONFIG violation if the i18n config hardcodes locales.

    Mirrors core ``scan_i18n_config``: locate the config file, flag a hardcoded
    locale array UNLESS the file also references the manifest / shared list.
    """
    config = _find_file(web_root, *CONFIG_CANDIDATES)
    if config is None:
        return []
    try:
        content = config.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    match = CONFIG_HARDCODED.search(content)
    if not match:
        return []
    if any(re.search(p, content, re.IGNORECASE) for p in CONFIG_MANIFEST_PATTERNS):
        return []
    line = _line_of(content, match)
    rel = config.relative_to(web_root)
    return [{
        "rule_id": RULE_CONFIG,
        "file": str(rel),
        "line": line,
        "col": 0,
        "evidence": f"{rel}: hardcoded locale array (should import from manifest)",
        "source_line": _line_text(content, line),
    }]


def scan_language_switcher(web_root: Path) -> list[dict]:
    """Emit a RULE_SWITCHER violation if the language switcher hardcodes locales.

    Mirrors core ``scan_language_switcher``: locate the switcher (named candidates,
    then a glob fallback), flag a hardcoded locale array UNLESS the file references
    the shared list / manifest / i18n config.
    """
    if not web_root.exists():
        return []
    switcher = _find_file(web_root, *SWITCHER_CANDIDATES)
    if switcher is None:
        candidates = list(web_root.rglob("*[Ll]anguage*[Ss]witcher*.tsx"))
        if not candidates:
            candidates = list(web_root.rglob("*[Ll]ocale*[Ss]witcher*.tsx"))
        if candidates:
            switcher = sorted(candidates)[0]
    if switcher is None:
        return []
    try:
        content = switcher.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    match = SWITCHER_HARDCODED.search(content)
    if not match:
        return []
    if any(re.search(p, content, re.IGNORECASE) for p in SWITCHER_SHARED_PATTERNS):
        return []
    line = _line_of(content, match)
    rel = switcher.relative_to(web_root)
    return [{
        "rule_id": RULE_SWITCHER,
        "file": str(rel),
        "line": line,
        "col": 0,
        "evidence": f"{rel}: hardcoded locale array (should use shared SUPPORTED_LOCALES)",
        "source_line": _line_text(content, line),
    }]


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one ``web/``-equivalent ``root`` and return RAW v1.1 violation dicts
    for both the i18n config and the language switcher."""
    root = Path(root)
    return scan_i18n_config(root) + scan_language_switcher(root)


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
