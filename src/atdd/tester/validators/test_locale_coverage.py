"""
Localization coverage validation (Localization Manifest Spec v1).

Validates locale files against manifest.json as single source of truth:
- LOCALE-TEST-1.1: Manifest schema compliance
- LOCALE-TEST-1.2: All locale/namespace files exist
- LOCALE-TEST-1.3: All files are valid JSON
- LOCALE-TEST-1.4: Keys match reference locale (deep comparison)
- LOCALE-TEST-1.5: Types match reference (object/array/primitive)
- LOCALE-TEST-1.6: Optional namespaces may be missing
- LOCALE-TEST-1.7: languageNames.<locale> exists in reference ui.json
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import atdd
from atdd.coach.utils.locale_phase import (
    LocalePhase,
    should_enforce_locale,
    emit_locale_warning,
)
from atdd.coach.utils.repo import find_repo_root

# Path constants
REPO_ROOT = find_repo_root()
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _load_json_file(path: Path) -> Tuple[Optional[Dict], Optional[str]]:
    """Load JSON file, returning (data, error_message)."""
    try:
        with open(path) as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    except Exception as e:
        return None, str(e)


def _get_all_keys(obj: Any, prefix: str = "") -> Set[str]:
    """
    Extract all keys from nested object using dot notation.
    Ignores keys starting with underscore (private/metadata keys).
    """
    keys = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.startswith("_"):
                continue
            full_key = f"{prefix}.{key}" if prefix else key
            keys.add(full_key)
            keys.update(_get_all_keys(value, full_key))
    return keys


def _get_type_signature(obj: Any) -> str:
    """Get type signature for comparison (object/array/primitive)."""
    if isinstance(obj, dict):
        return "object"
    elif isinstance(obj, list):
        return f"array[{len(obj)}]"
    elif isinstance(obj, bool):
        return "boolean"
    elif isinstance(obj, int):
        return "number"
    elif isinstance(obj, float):
        return "number"
    elif isinstance(obj, str):
        return "string"
    elif obj is None:
        return "null"
    return "unknown"


def _compare_types(ref_obj: Any, target_obj: Any, path: str = "") -> List[str]:
    """
    Compare types between reference and target objects recursively.
    Returns list of type mismatch descriptions.
    """
    mismatches = []
    ref_type = _get_type_signature(ref_obj)
    target_type = _get_type_signature(target_obj)

    if ref_type.startswith("array") and target_type.startswith("array"):
        pass
    elif ref_type != target_type:
        key_display = path or "(root)"
        mismatches.append(f"{key_display}: expected {ref_type}, got {target_type}")

    if isinstance(ref_obj, dict) and isinstance(target_obj, dict):
        for key in ref_obj:
            if key.startswith("_"):
                continue
            if key in target_obj:
                child_path = f"{path}.{key}" if path else key
                mismatches.extend(_compare_types(ref_obj[key], target_obj[key], child_path))

    return mismatches


@pytest.mark.locale
def test_locale_manifest_schema_compliance(locale_manifest, locale_manifest_path, load_schema):
    """
    LOCALE-TEST-1.1: Manifest schema compliance

    Given: localization.manifest configured in .atdd/config.yaml
    When: Loading the manifest file
    Then: File exists and validates against locale_manifest.schema.json
    """
    if locale_manifest_path is None:
        pytest.skip("Localization not configured (localization.manifest not in config)")

    if not locale_manifest_path.exists():
        msg = f"Manifest file not found: {locale_manifest_path.relative_to(REPO_ROOT)}"
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.1", msg)
            pytest.skip(msg)

    schema = load_schema("tester", "locale_manifest.schema.json")

    try:
        import jsonschema
        jsonschema.validate(locale_manifest, schema)
    except jsonschema.ValidationError as e:
        msg = f"Manifest schema validation failed: {e.message}"
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.1", msg)
            pytest.skip(msg)

    if locale_manifest["reference"] not in locale_manifest["locales"]:
        msg = f"Reference locale '{locale_manifest['reference']}' not in locales list"
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.1", msg)


@pytest.mark.locale
def test_locale_files_exist(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.2: All <locale>/<namespace>.json files exist

    Given: Manifest with locales and namespaces
    When: Checking file system
    Then: All required namespace files exist for all locales
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    missing_files = []
    locales = locale_manifest.get("locales", [])
    namespaces = locale_manifest.get("namespaces", [])

    for locale in locales:
        locale_dir = locales_dir / locale
        for namespace in namespaces:
            file_path = locale_dir / f"{namespace}.json"
            if not file_path.exists():
                missing_files.append(f"{locale}/{namespace}.json")

    if missing_files:
        msg = f"Missing locale files ({len(missing_files)}):\n" + "\n".join(f"  - {f}" for f in missing_files[:20])
        if len(missing_files) > 20:
            msg += f"\n  ... and {len(missing_files) - 20} more"

        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.2", msg)
            pytest.skip(msg)


@pytest.mark.locale
def test_locale_files_valid_json(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.3: All locale files are valid JSON

    Given: Locale namespace files
    When: Parsing as JSON
    Then: All files parse without errors
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    invalid_files = []
    locales = locale_manifest.get("locales", [])
    namespaces = locale_manifest.get("namespaces", [])
    optional_namespaces = locale_manifest.get("optional_namespaces", [])

    all_namespaces = namespaces + optional_namespaces

    for locale in locales:
        locale_dir = locales_dir / locale
        for namespace in all_namespaces:
            file_path = locale_dir / f"{namespace}.json"
            if file_path.exists():
                _, error = _load_json_file(file_path)
                if error:
                    invalid_files.append(f"{locale}/{namespace}.json: {error}")

    if invalid_files:
        msg = f"Invalid JSON files ({len(invalid_files)}):\n" + "\n".join(f"  - {f}" for f in invalid_files[:10])
        if len(invalid_files) > 10:
            msg += f"\n  ... and {len(invalid_files) - 10} more"

        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.3", msg)
            pytest.skip(msg)


@pytest.mark.locale
def test_locale_keys_match_reference(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.4: Keys match reference locale (deep comparison, ignore _ prefix)

    Given: Reference locale and other locales
    When: Comparing keys at all nesting levels
    Then: All locales have same keys as reference (ignoring _ prefixed keys)
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    reference = locale_manifest.get("reference")
    locales = locale_manifest.get("locales", [])
    namespaces = locale_manifest.get("namespaces", [])

    key_mismatches = []

    for namespace in namespaces:
        ref_path = locales_dir / reference / f"{namespace}.json"
        ref_data, ref_error = _load_json_file(ref_path)

        if ref_error:
            continue

        ref_keys = _get_all_keys(ref_data)

        for locale in locales:
            if locale == reference:
                continue

            locale_path = locales_dir / locale / f"{namespace}.json"
            locale_data, locale_error = _load_json_file(locale_path)

            if locale_error:
                continue

            locale_keys = _get_all_keys(locale_data)

            missing_keys = ref_keys - locale_keys
            extra_keys = locale_keys - ref_keys

            if missing_keys:
                key_mismatches.append(
                    f"{locale}/{namespace}.json missing keys: {', '.join(sorted(missing_keys)[:5])}"
                    + (f" (+{len(missing_keys) - 5} more)" if len(missing_keys) > 5 else "")
                )

            if extra_keys:
                key_mismatches.append(
                    f"{locale}/{namespace}.json extra keys: {', '.join(sorted(extra_keys)[:5])}"
                    + (f" (+{len(extra_keys) - 5} more)" if len(extra_keys) > 5 else "")
                )

    if key_mismatches:
        msg = f"Key mismatches ({len(key_mismatches)}):\n" + "\n".join(f"  - {m}" for m in key_mismatches[:15])
        if len(key_mismatches) > 15:
            msg += f"\n  ... and {len(key_mismatches) - 15} more"

        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.4", msg)
            pytest.skip(msg)


@pytest.mark.locale
def test_locale_types_match_reference(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.5: Types match reference (object->object, array->array, primitive->same type)

    Given: Reference locale and other locales
    When: Comparing value types at each key
    Then: Types match between reference and all locales
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    reference = locale_manifest.get("reference")
    locales = locale_manifest.get("locales", [])
    namespaces = locale_manifest.get("namespaces", [])

    type_mismatches = []

    for namespace in namespaces:
        ref_path = locales_dir / reference / f"{namespace}.json"
        ref_data, ref_error = _load_json_file(ref_path)

        if ref_error:
            continue

        for locale in locales:
            if locale == reference:
                continue

            locale_path = locales_dir / locale / f"{namespace}.json"
            locale_data, locale_error = _load_json_file(locale_path)

            if locale_error:
                continue

            mismatches = _compare_types(ref_data, locale_data)
            for mismatch in mismatches:
                type_mismatches.append(f"{locale}/{namespace}.json: {mismatch}")

    if type_mismatches:
        msg = f"Type mismatches ({len(type_mismatches)}):\n" + "\n".join(f"  - {m}" for m in type_mismatches[:10])
        if len(type_mismatches) > 10:
            msg += f"\n  ... and {len(type_mismatches) - 10} more"

        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.5", msg)
            pytest.skip(msg)


@pytest.mark.locale
def test_optional_namespaces_match_reference(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.6: Optional namespaces may be missing; if present, must match reference

    Given: Optional namespaces in manifest
    When: Checking locale files
    Then: Optional namespace files may not exist, but if they do, keys must match reference
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    optional_namespaces = locale_manifest.get("optional_namespaces", [])
    if not optional_namespaces:
        pytest.skip("No optional namespaces defined")

    reference = locale_manifest.get("reference")
    locales = locale_manifest.get("locales", [])

    key_mismatches = []

    for namespace in optional_namespaces:
        ref_path = locales_dir / reference / f"{namespace}.json"
        ref_data, ref_error = _load_json_file(ref_path)

        if ref_error or ref_data is None:
            continue

        ref_keys = _get_all_keys(ref_data)

        for locale in locales:
            if locale == reference:
                continue

            locale_path = locales_dir / locale / f"{namespace}.json"
            if not locale_path.exists():
                continue

            locale_data, locale_error = _load_json_file(locale_path)
            if locale_error:
                continue

            locale_keys = _get_all_keys(locale_data)

            missing_keys = ref_keys - locale_keys
            extra_keys = locale_keys - ref_keys

            if missing_keys:
                key_mismatches.append(
                    f"{locale}/{namespace}.json (optional) missing keys: {', '.join(sorted(missing_keys)[:5])}"
                )

            if extra_keys:
                key_mismatches.append(
                    f"{locale}/{namespace}.json (optional) extra keys: {', '.join(sorted(extra_keys)[:5])}"
                )

    if key_mismatches:
        msg = f"Optional namespace key mismatches ({len(key_mismatches)}):\n" + "\n".join(f"  - {m}" for m in key_mismatches[:10])
        if len(key_mismatches) > 10:
            msg += f"\n  ... and {len(key_mismatches) - 10} more"

        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.6", msg)
            pytest.skip(msg)


@pytest.mark.locale
def test_language_names_complete(locale_manifest, locales_dir):
    """
    LOCALE-TEST-1.7: languageNames.<locale> exists in reference ui.json

    Given: Manifest with locales list
    When: Checking reference ui.json for languageNames
    Then: Each locale in manifest has a corresponding languageNames entry
    """
    if locale_manifest is None:
        pytest.skip("Localization not configured")

    reference = locale_manifest.get("reference")
    locales = locale_manifest.get("locales", [])
    namespaces = locale_manifest.get("namespaces", [])

    if "ui" not in namespaces:
        pytest.skip("No 'ui' namespace configured - skipping languageNames check")

    ui_path = locales_dir / reference / "ui.json"
    ui_data, ui_error = _load_json_file(ui_path)

    if ui_error:
        pytest.skip(f"Cannot read reference ui.json: {ui_error}")

    language_names = ui_data.get("languageNames", {})
    if not language_names:
        msg = "Reference ui.json missing 'languageNames' object"
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.7", msg)
            pytest.skip(msg)

    missing_names = []
    for locale in locales:
        if locale not in language_names:
            missing_names.append(locale)

    if missing_names:
        msg = f"Missing languageNames entries for locales: {', '.join(missing_names)}"
        if should_enforce_locale(LocalePhase.TESTER_ENFORCEMENT):
            pytest.fail(msg)
        else:
            emit_locale_warning("LOCALE-TEST-1.7", msg)
            pytest.skip(msg)
