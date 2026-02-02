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


@pytest.mark.locale
@pytest.mark.coder
def test_i18n_config_uses_manifest(locale_manifest, locale_manifest_path):
    """
    LOCALE-CODE-2.1: i18nConfig.ts imports from manifest (not hardcoded arrays)

    Given: Web application with i18n configuration
    When: Checking i18nConfig.ts or i18n.ts
    Then: Configuration imports locales from manifest or shared constant
          NOT hardcoded locale arrays like ['en', 'es', 'fr']
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    i18n_config = _find_file(
        WEB_DIR,
        "src/i18nConfig.ts",
        "src/i18n/config.ts",
        "src/i18n.ts",
        "src/lib/i18n.ts",
        "src/config/i18n.ts",
    )

    if i18n_config is None:
        pytest.skip("No i18n config file found in web/src/")

    content = _read_file_content(i18n_config)
    if content is None:
        pytest.skip(f"Cannot read {i18n_config}")

    hardcoded_array_pattern = re.compile(
        r"(?:locales|supportedLocales|SUPPORTED_LOCALES|languages)\s*[=:]\s*\[\s*['\"][a-z]{2}",
        re.IGNORECASE
    )

    if hardcoded_array_pattern.search(content):
        manifest_import_patterns = [
            r"from\s+['\"].*manifest",
            r"import.*manifest",
            r"require\s*\(\s*['\"].*manifest",
            r"SUPPORTED_LOCALES",
            r"getSupportedLocales",
        ]

        has_manifest_usage = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in manifest_import_patterns
        )

        if not has_manifest_usage:
            msg = (
                f"i18n config has hardcoded locale array: {i18n_config.relative_to(REPO_ROOT)}\n"
                f"  Should import from manifest.json or use shared SUPPORTED_LOCALES constant"
            )
            if should_enforce_locale(LocalePhase.FULL_ENFORCEMENT):
                pytest.fail(msg)
            else:
                emit_locale_warning("LOCALE-CODE-2.1", msg, LocalePhase.FULL_ENFORCEMENT)
                pytest.skip(msg)


@pytest.mark.locale
@pytest.mark.coder
def test_language_switcher_uses_shared_locales(locale_manifest, locale_manifest_path):
    """
    LOCALE-CODE-2.2: LanguageSwitcher uses shared SUPPORTED_LOCALES

    Given: Web application with language switcher component
    When: Checking LanguageSwitcher component
    Then: Component imports locales from shared constant or manifest
          NOT hardcoded locale arrays
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    switcher_patterns = [
        "src/components/LanguageSwitcher.tsx",
        "src/components/LocaleSwitcher.tsx",
        "src/components/ui/LanguageSwitcher.tsx",
        "src/components/common/LanguageSwitcher.tsx",
        "src/features/i18n/LanguageSwitcher.tsx",
    ]

    switcher_file = _find_file(WEB_DIR, *switcher_patterns)

    if switcher_file is None:
        switcher_files = list(WEB_DIR.rglob("*[Ll]anguage*[Ss]witcher*.tsx"))
        if not switcher_files:
            switcher_files = list(WEB_DIR.rglob("*[Ll]ocale*[Ss]witcher*.tsx"))
        if switcher_files:
            switcher_file = switcher_files[0]

    if switcher_file is None:
        pytest.skip("No LanguageSwitcher component found")

    content = _read_file_content(switcher_file)
    if content is None:
        pytest.skip(f"Cannot read {switcher_file}")

    hardcoded_array_pattern = re.compile(
        r"(?:locales|languages|options)\s*[=:]\s*\[\s*(?:\{[^}]*locale[^}]*['\"][a-z]{2}|['\"][a-z]{2})",
        re.IGNORECASE
    )

    if hardcoded_array_pattern.search(content):
        shared_patterns = [
            r"SUPPORTED_LOCALES",
            r"getSupportedLocales",
            r"from\s+['\"].*manifest",
            r"from\s+['\"].*i18n",
            r"from\s+['\"].*config",
            r"useLocales",
        ]

        has_shared_usage = any(
            re.search(pattern, content, re.IGNORECASE)
            for pattern in shared_patterns
        )

        if not has_shared_usage:
            msg = (
                f"LanguageSwitcher has hardcoded locale array: {switcher_file.relative_to(REPO_ROOT)}\n"
                f"  Should import from shared SUPPORTED_LOCALES or manifest"
            )
            if should_enforce_locale(LocalePhase.FULL_ENFORCEMENT):
                pytest.fail(msg)
            else:
                emit_locale_warning("LOCALE-CODE-2.2", msg, LocalePhase.FULL_ENFORCEMENT)
                pytest.skip(msg)
