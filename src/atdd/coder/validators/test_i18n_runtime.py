"""
i18n runtime validation (Localization Manifest Spec v1).

Validates that runtime code uses the centralized locale manifest:
- LOCALE-CODE-2.1: i18nConfig.ts imports from manifest (not hardcoded arrays)
- LOCALE-CODE-2.2: LanguageSwitcher uses shared SUPPORTED_LOCALES
"""

import re
import pytest
from pathlib import Path
from typing import Optional

from atdd.coach.utils.locale_phase import (
    LocalePhase,
    should_enforce_locale,
    emit_locale_warning,
)
from atdd.coach.utils.repo import find_repo_root

# Path constants
REPO_ROOT = find_repo_root()
WEB_DIR = REPO_ROOT / "web"


def _find_file(base_dir: Path, *possible_paths: str) -> Optional[Path]:
    """Find first existing file from list of possible paths."""
    for rel_path in possible_paths:
        full_path = base_dir / rel_path
        if full_path.exists():
            return full_path
    return None


def _read_file_content(path: Path) -> Optional[str]:
    """Read file content, return None on error."""
    try:
        return path.read_text()
    except Exception:
        return None


def scan_i18n_config(repo_root: Path):
    """Scan for hardcoded locale arrays in i18n config. Used by ratchet baseline."""
    web_dir = repo_root / "web"
    i18n_config = _find_file(
        web_dir, "src/i18nConfig.ts", "src/i18n/config.ts",
        "src/i18n.ts", "src/lib/i18n.ts", "src/config/i18n.ts",
    )
    if i18n_config is None:
        return 0, []
    content = _read_file_content(i18n_config)
    if content is None:
        return 0, []
    hardcoded = re.compile(
        r"(?:locales|supportedLocales|SUPPORTED_LOCALES|languages)\s*[=:]\s*\[\s*['\"][a-z]{2}",
        re.IGNORECASE,
    )
    if not hardcoded.search(content):
        return 0, []
    manifest_patterns = [
        r"from\s+['\"].*manifest", r"import.*manifest",
        r"require\s*\(\s*['\"].*manifest", r"SUPPORTED_LOCALES", r"getSupportedLocales",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in manifest_patterns):
        return 0, []
    rel = i18n_config.relative_to(repo_root)
    return 1, [f"{rel}: hardcoded locale array (should import from manifest)"]


def scan_language_switcher(repo_root: Path):
    """Scan for hardcoded locales in LanguageSwitcher. Used by ratchet baseline."""
    web_dir = repo_root / "web"
    if not web_dir.exists():
        return 0, []
    switcher_file = _find_file(
        web_dir, "src/components/LanguageSwitcher.tsx",
        "src/components/LocaleSwitcher.tsx", "src/components/ui/LanguageSwitcher.tsx",
        "src/components/common/LanguageSwitcher.tsx", "src/features/i18n/LanguageSwitcher.tsx",
    )
    if switcher_file is None:
        candidates = list(web_dir.rglob("*[Ll]anguage*[Ss]witcher*.tsx"))
        if not candidates:
            candidates = list(web_dir.rglob("*[Ll]ocale*[Ss]witcher*.tsx"))
        if candidates:
            switcher_file = candidates[0]
    if switcher_file is None:
        return 0, []
    content = _read_file_content(switcher_file)
    if content is None:
        return 0, []
    hardcoded = re.compile(
        r"(?:locales|languages|options)\s*[=:]\s*\[\s*(?:\{[^}]*locale[^}]*['\"][a-z]{2}|['\"][a-z]{2})",
        re.IGNORECASE,
    )
    if not hardcoded.search(content):
        return 0, []
    shared_patterns = [
        r"SUPPORTED_LOCALES", r"getSupportedLocales", r"from\s+['\"].*manifest",
        r"from\s+['\"].*i18n", r"from\s+['\"].*config", r"useLocales",
    ]
    if any(re.search(p, content, re.IGNORECASE) for p in shared_patterns):
        return 0, []
    rel = switcher_file.relative_to(repo_root)
    return 1, [f"{rel}: hardcoded locale array (should use shared SUPPORTED_LOCALES)"]


@pytest.mark.locale
@pytest.mark.coder
def test_i18n_config_uses_manifest(ratchet_baseline, locale_manifest, locale_manifest_path):
    """
    LOCALE-CODE-2.1: i18nConfig.ts imports from manifest (not hardcoded arrays)

    Given: Web application with i18n configuration
    When: Checking i18nConfig.ts or i18n.ts
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    count, violations = scan_i18n_config(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="i18n_config_manifest",
        current_count=count,
        violations=violations,
    )


@pytest.mark.locale
@pytest.mark.coder
def test_language_switcher_uses_shared_locales(ratchet_baseline, locale_manifest, locale_manifest_path):
    """
    LOCALE-CODE-2.2: LanguageSwitcher uses shared SUPPORTED_LOCALES

    Given: Web application with language switcher component
    When: Checking LanguageSwitcher component
    Then: Violation count does not exceed baseline (ratchet pattern)
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    count, violations = scan_language_switcher(REPO_ROOT)
    ratchet_baseline.assert_no_regression(
        validator_id="i18n_language_switcher",
        current_count=count,
        violations=violations,
    )
