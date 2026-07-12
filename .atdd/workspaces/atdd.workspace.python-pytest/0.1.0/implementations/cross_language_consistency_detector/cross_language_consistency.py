"""python-pytest detector for coder.boundaries.xlang-entity (+ -enum, -naming, -contract).

Realizes the agnostic cross-language-consistency obligations. ONE run carries FOUR
distinct rule_ids — the v1.1 multi-rule output channel (PROVIDER-CONTRACT-v1.1.md
§3) — with a MIXED downstream disposition:

  * coder.boundaries.xlang-entity   — a contract entity implemented in some but
    not all stacks.                                  disposition: advisory
  * coder.boundaries.xlang-enum     — a same-named enum whose member sets differ
    between Python and Dart.                         disposition: strict
  * coder.boundaries.xlang-naming   — a shared base name spelled with different
    architectural suffixes across stacks.            disposition: strict
  * coder.boundaries.xlang-contract — a contract entity implemented in NO stack.
                                                     disposition: advisory

PROVENANCE — ported from core
    src/atdd/coder/validators/test_cross_language_consistency.py
        :: extract_python_classes / extract_dart_classes / extract_python_enums
           / extract_dart_enums / find_contract_entities
           / scan_entity_cross_language / scan_enum_cross_language
           / scan_naming_cross_language / scan_api_contracts_cross_language
    (blob ef9f2b775911f096). The regex extraction + comparison logic is copied
    behavior-for-behavior; the `atdd.coach.*` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_ENTITY`` / ``RULE_ENUM`` /
    ``RULE_NAMING`` / ``RULE_CONTRACT`` constants. Authoritative metadata
    (severities 3/3/2/3; mixed dispositions) lives in the convention nodes.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2).
  * ``find_repo_root`` + ``find_python_dir`` + the fixed ``REPO_ROOT/{python,lib,
    contracts}`` dirs -> REMOVED. Each ``ATDD_SCAN_ROOTS`` entry is treated as a
    repo-like root and the three language dirs (``python/`` Python sources,
    ``lib/`` Dart sources, ``contracts/`` schemas) are discovered UNDER it (§2).
  * ``assert_disposition_satisfied`` (ratchet baseline) -> NOT PORTED; disposition
    (advisory for entity/contract, strict for enum/naming) is applied downstream by
    the consumer (§1).

HONEST SCOPE CAVEAT (carried from the source validator + boundaries.convention):
  These are AGGREGATE cross-file facts ("entity X missing in Dart", "enum Y differs
  across stacks"), NOT single offending source lines. Each violation therefore
  carries a SYNTHETIC ``file`` (a logical id like ``contracts/<entity>`` /
  ``enums/<name>`` / ``naming/<base>``), ``line=1``/``col=0`` placeholders, and an
  EMPTY ``source_line`` — there is no per-site line to quote. Per-site suppression
  markers cannot apply to a markerless synthetic site, which is exactly why the
  entity/contract rules are dispositioned ``advisory`` downstream (issue #395).

Pure stdlib (``re``, ``json``, ``fnmatch``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

RULE_ENTITY = "coder.boundaries.xlang-entity"      # disposition: advisory
RULE_ENUM = "coder.boundaries.xlang-enum"           # disposition: strict
RULE_NAMING = "coder.boundaries.xlang-naming"       # disposition: strict
RULE_CONTRACT = "coder.boundaries.xlang-contract"   # disposition: advisory

# Stack subdirs discovered under each scan root (replacing core's repo_root/{...}).
PYTHON_SUBDIR = "python"
DART_SUBDIR = "lib"
CONTRACTS_SUBDIR = "contracts"

NAMING_SUFFIXES = ("Entity", "Model", "DTO", "Service", "Repository")


def _excluded(rel: str, exclude_globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in exclude_globs)


# ── extraction (ported behavior-for-behavior) ─────────────────────────────────


def extract_python_classes(python_dir: Path, exclude_globs: list[str]) -> dict:
    classes: dict = {}
    if not python_dir.exists():
        return classes
    for py_file in sorted(python_dir.rglob("*.py")):
        if "/test/" in str(py_file):
            continue
        rel = str(py_file.relative_to(python_dir))
        if _excluded(rel, exclude_globs):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"class\s+([A-Z][a-zA-Z0-9_]*)\s*[:\(]", content):
            classes[match.group(1)] = {"language": "python"}
    return classes


def extract_dart_classes(lib_dir: Path, exclude_globs: list[str]) -> dict:
    classes: dict = {}
    if not lib_dir.exists():
        return classes
    for dart_file in sorted(lib_dir.rglob("*.dart")):
        if dart_file.name.endswith("_test.dart"):
            continue
        rel = str(dart_file.relative_to(lib_dir))
        if _excluded(rel, exclude_globs):
            continue
        try:
            content = dart_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"class\s+([A-Z][a-zA-Z0-9_]*)\s*[{\s]", content):
            classes[match.group(1)] = {"language": "dart"}
    return classes


def extract_python_enums(python_dir: Path, exclude_globs: list[str]) -> dict:
    enums: dict = {}
    if not python_dir.exists():
        return enums
    for py_file in sorted(python_dir.rglob("*.py")):
        if "/test/" in str(py_file):
            continue
        rel = str(py_file.relative_to(python_dir))
        if _excluded(rel, exclude_globs):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"class\s+([A-Z][a-zA-Z0-9_]*)\s*\(\s*Enum\s*\):", content):
            enum_name = match.group(1)
            values = set()
            for line in content.split("\n"):
                val_match = re.match(r"^\s+([A-Z_]+)\s*=", line)
                if val_match:
                    values.add(val_match.group(1))
            if values:
                enums[enum_name] = values
    return enums


def extract_dart_enums(lib_dir: Path, exclude_globs: list[str]) -> dict:
    enums: dict = {}
    if not lib_dir.exists():
        return enums
    for dart_file in sorted(lib_dir.rglob("*.dart")):
        if dart_file.name.endswith("_test.dart"):
            continue
        rel = str(dart_file.relative_to(lib_dir))
        if _excluded(rel, exclude_globs):
            continue
        try:
            content = dart_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in re.finditer(r"enum\s+([A-Z][a-zA-Z0-9_]*)\s*\{([^}]+)\}", content):
            enum_name = match.group(1)
            values = set()
            for value in match.group(2).split(","):
                val = value.strip()
                if val and not val.startswith("//"):
                    val = val.split("//")[0].strip()
                    if val:
                        values.add(val)
            if values:
                enums[enum_name] = values
    return enums


def find_contract_entities(contracts_dir: Path, exclude_globs: list[str]) -> dict:
    entities: dict = {}
    if not contracts_dir.exists():
        return entities
    for schema_file in sorted(contracts_dir.rglob("*.schema.json")):
        rel = str(schema_file.relative_to(contracts_dir))
        if _excluded(rel, exclude_globs):
            continue
        try:
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        # Skip cross-cutting wire-shape contracts (wildcard `/*` operation paths).
        metadata = schema.get("x-artifact-metadata", {})
        operations = metadata.get("api", {}).get("operations", [])
        if any(op.get("path", "").startswith("/*") for op in operations):
            continue
        schema_id = schema.get("$id", "")
        if ":" in schema_id:
            entity_name = schema_id.split(":")[-1].replace(".", "_")
        else:
            entity_name = schema_file.stem.replace(".schema", "")
        required = set(schema.get("required", []))
        properties = set(schema.get("properties", {}).keys())
        entities[entity_name] = required if required else properties
    return entities


# ── synthetic violation helper ────────────────────────────────────────────────


def _synthetic(rule_id: str, location: str, evidence: str) -> dict:
    """Aggregate cross-file violation: synthetic location, no per-site source line.

    line=1/col=0 are schema placeholders (the contract requires line>=1); the empty
    ``source_line`` signals "no offending line to quote" — which is why per-site
    suppression cannot apply and entity/contract are advisory downstream.
    """
    return {
        "rule_id": rule_id,
        "file": location,
        "line": 1,
        "col": 0,
        "evidence": evidence,
        "source_line": "",
    }


def _normalize(entity_name: str) -> str:
    return "".join(word.capitalize() for word in re.split(r"[-_]", entity_name))


# ── cross-language scans (ported) ─────────────────────────────────────────────


def scan_entity_cross_language(python_classes: dict, dart_classes: dict, contract_entities: dict) -> list[dict]:
    if (not python_classes and not dart_classes) or not contract_entities:
        return []
    violations: list[dict] = []
    for entity_name in contract_entities:
        normalized = _normalize(entity_name)
        has_python = (normalized in python_classes or entity_name in python_classes or
                      any(normalized in cls for cls in python_classes))
        has_dart = (normalized in dart_classes or entity_name in dart_classes or
                    any(normalized in cls for cls in dart_classes))
        missing = []
        if python_classes and not has_python:
            missing.append("Python")
        if dart_classes and not has_dart:
            missing.append("Dart")
        if missing:
            violations.append(_synthetic(
                RULE_ENTITY,
                f"contracts/{entity_name}",
                f"{entity_name} missing in {', '.join(missing)} — contract entity not implemented in every stack",
            ))
    return violations


def scan_enum_cross_language(python_enums: dict, dart_enums: dict) -> list[dict]:
    if not python_enums and not dart_enums:
        return []
    violations: list[dict] = []
    for enum_name in sorted(set(python_enums) & set(dart_enums)):
        py_lower = {v.lower() for v in python_enums[enum_name]}
        dart_lower = {v.lower() for v in dart_enums[enum_name]}
        if py_lower != dart_lower:
            violations.append(_synthetic(
                RULE_ENUM,
                f"enums/{enum_name}",
                f"{enum_name}: Python-only={sorted(py_lower - dart_lower)} "
                f"Dart-only={sorted(dart_lower - py_lower)} — enum members differ across stacks",
            ))
    return violations


def scan_naming_cross_language(python_classes: dict, dart_classes: dict) -> list[dict]:
    if not python_classes or not dart_classes:
        return []
    python_suffixes: dict = {}
    dart_suffixes: dict = {}
    for name in python_classes:
        for suffix in NAMING_SUFFIXES:
            if name.endswith(suffix):
                python_suffixes.setdefault(suffix, set()).add(name[: -len(suffix)])
    for name in dart_classes:
        for suffix in NAMING_SUFFIXES:
            if name.endswith(suffix):
                dart_suffixes.setdefault(suffix, set()).add(name[: -len(suffix)])
    violations: list[dict] = []
    for suffix in sorted(set(python_suffixes) | set(dart_suffixes)):
        for base in sorted(python_suffixes.get(suffix, set())):
            for dart_suffix in sorted(dart_suffixes):
                if suffix != dart_suffix and base in dart_suffixes[dart_suffix]:
                    violations.append(_synthetic(
                        RULE_NAMING,
                        f"naming/{base}",
                        f"{base}: Python={suffix} Dart={dart_suffix} — shared base spelled with "
                        f"divergent architectural suffixes",
                    ))
    return violations


def scan_api_contracts_cross_language(python_classes: dict, dart_classes: dict, contract_entities: dict) -> list[dict]:
    if not contract_entities:
        return []
    violations: list[dict] = []
    for entity_name in contract_entities:
        normalized = _normalize(entity_name)
        has_any = (normalized in python_classes or entity_name in python_classes or
                   normalized in dart_classes or entity_name in dart_classes or
                   any(normalized in cls for cls in python_classes) or
                   any(normalized in cls for cls in dart_classes))
        if not has_any:
            violations.append(_synthetic(
                RULE_CONTRACT,
                f"contracts/{entity_name}",
                f"{entity_name}: no implementations found in any stack — unimplemented contract",
            ))
    return violations


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one repo-like ``root`` (containing python/, lib/, contracts/) and return
    RAW v1.1 violation dicts across all four cross-language rule_ids."""
    root = Path(root)
    exclude_globs = exclude_globs or []
    python_dir = root / PYTHON_SUBDIR
    lib_dir = root / DART_SUBDIR
    contracts_dir = root / CONTRACTS_SUBDIR

    python_classes = extract_python_classes(python_dir, exclude_globs)
    dart_classes = extract_dart_classes(lib_dir, exclude_globs)
    python_enums = extract_python_enums(python_dir, exclude_globs)
    dart_enums = extract_dart_enums(lib_dir, exclude_globs)
    contract_entities = find_contract_entities(contracts_dir, exclude_globs)

    violations: list[dict] = []
    violations.extend(scan_entity_cross_language(python_classes, dart_classes, contract_entities))
    violations.extend(scan_enum_cross_language(python_enums, dart_enums))
    violations.extend(scan_naming_cross_language(python_classes, dart_classes))
    violations.extend(scan_api_contracts_cross_language(python_classes, dart_classes, contract_entities))
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
