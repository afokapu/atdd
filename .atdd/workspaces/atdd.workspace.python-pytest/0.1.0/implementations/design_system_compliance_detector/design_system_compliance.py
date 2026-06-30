"""python-pytest detector for the design-system-compliance rule family.

Realizes SEVEN agnostic design-system obligations for the web/TypeScript stack.
ONE run carries SEVEN distinct rule_ids — the v1.1 multi-rule output channel
(PROVIDER-CONTRACT-v1.1.md §3), the same dual/poly-binding the core validator
performs via seven `bind_rule(...)` calls:

  * coder.design.primitives       — a presentation-layer component that renders
                                    JSX but imports nothing from the design system.
  * coder.design.token-color      — a UI file embeds a raw hex / rgba color literal
                                    instead of a design token.
  * coder.design.orphan-export    — a design-system primitive/component export that
                                    no consumer imports.
  * coder.design.foundations      — a design-system primitive/component embeds raw
                                    pixel values without composing foundations.
  * coder.design.hierarchy-import — a design-system file violates the layer
                                    hierarchy (primitives→components/templates,
                                    components→templates, or design-system→wagon).
  * coder.design.token-hardcoded  — a wagon UI file hardcodes spacing / radius /
                                    duration values that belong in foundations.
  * coder.design.orphan-ui        — ANY .tsx that renders JSX yet imports nothing
                                    from the design system (superset of -primitives,
                                    which checks the presentation/ layer only).

PROVENANCE — ported from core
    src/atdd/coder/validators/test_design_system_compliance.py
        :: get_presentation_files / get_all_ui_files / extract_imports /
           extract_imported_names / get_design_system_exports /
           find_design_system_usage / extract_raw_color_values /
           scan_ds_presentation_primitives / the seven `@pytest.mark.coder`
           enforcement bodies (presentation primitives, color tokens, orphan
           exports, foundations usage, hierarchy imports, hardcoded tokens,
           orphan UI). The metrics body (DESIGN-008, informational warnings, NO
           rule binding) is NOT a rule and is out of scope.
    (origin/main @ 624d3afe, validator blob 9aad333effe9a0b5,
     convention blob 21bedcb7d74cfb18). The regex/scan behavior is copied
     behavior-for-behavior; the `atdd.coach.*` substrate couplings were REMOVED.

DECOUPLED FROM CORE (every adaptation, per task §3):
  * ``bind_rule(...)``  -> module-level ``RULE_*`` constants. Authoritative
    metadata (severities 2/3; all seven `strict`) lives in the convention nodes,
    not bound at import.
  * ``Violation``  -> plain dicts in the v1.1 shape
    ``{rule_id, file, line, col, evidence, source_line}`` (§3.2). The core
    ``location`` (``path:line``) decomposes into ``file`` (scan-root-relative) +
    ``line`` + ``col`` (0 — the core checks are line/regex based and never tracked
    a column); ``detail`` -> ``evidence``.
  * ``find_repo_root`` + fixed ``web/src`` / ``maintain-ux`` paths  -> REMOVED.
    Scan scope is supplied explicitly via ``ATDD_SCAN_ROOTS`` /
    ``ATDD_SCAN_EXCLUDES`` (§2); never auto-discovered. Each scan root is treated
    as a ``web/src``-equivalent root: ``maintain-ux/`` lives directly under it and
    layer membership (`/presentation/`) is read from the path under that root,
    exactly as core read it relative to ``WEB_SRC``.
  * ``assert_disposition_satisfied`` (ratchet baselines for six of the rules,
    documentation-only/warning for color) -> NOT PORTED. The detector emits RAW
    violations only; the ratchet baseline / aggregation is consumer scan-policy,
    not detector logic (§1). All seven rule_ids are `strict` per the convention.
  * The core ``violations[:3]`` per-file cap for the color + hardcoded scans is
    PRESERVED verbatim (it is detection behavior, not disposition).

Pure stdlib (``re``, ``pathlib``) — no third-party or core imports.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

# The seven convention rule_ids this detector realizes (all disposition `strict`).
RULE_PRIMITIVES = "coder.design.primitives"          # presentation w/o DS import
RULE_COLOR = "coder.design.token-color"              # raw hex/rgba literal
RULE_ORPHAN_EXPORT = "coder.design.orphan-export"    # DS export with no consumer
RULE_FOUNDATIONS = "coder.design.foundations"        # DS primitive w/ raw pixels
RULE_HIERARCHY_IMPORT = "coder.design.hierarchy-import"  # DS layer hierarchy break
RULE_HARDCODED = "coder.design.token-hardcoded"      # wagon hardcoded spacing/etc
RULE_ORPHAN_UI = "coder.design.orphan-ui"            # any JSX tsx w/o DS import

# Allowed design system import paths — copied verbatim from core.
DESIGN_SYSTEM_IMPORTS = [
    "@/maintain-ux/primitives",
    "@/maintain-ux/components",
    "@/maintain-ux/foundations",
    "@maintain-ux/primitives",
    "@maintain-ux/components",
    "@maintain-ux/foundations",
    "../primitives",
    "../components",
    "../foundations",
    "./primitives",
    "./components",
    "./foundations",
]


# ── path helpers (root == a web/src-equivalent scan root) ─────────────────────


def _maintain_ux(root: Path) -> Path:
    return root / "maintain-ux"


def _matches_exclude(rel: Path, exclude_globs: list[str]) -> bool:
    rel_str = str(rel)
    return any(fnmatch.fnmatch(rel_str, pat) for pat in exclude_globs)


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _is_test(path: Path) -> bool:
    return ".test." in path.name or "/tests/" in str(path)


def _line_text(content: str, line: int) -> str:
    lines = content.splitlines()
    return lines[line - 1] if 1 <= line <= len(lines) else ""


# ── file discovery (ported from core, parameterized by root) ──────────────────


def get_presentation_files(root: Path, exclude_globs: list[str]) -> list[Path]:
    """Presentation-layer .tsx files (mirrors core get_presentation_files)."""
    if not root.exists():
        return []
    files: list[Path] = []
    for f in sorted(root.rglob("*.tsx")):
        if _is_test(f):
            continue
        if "/maintain-ux/" in str(f):
            continue
        if "/presentation/" not in str(f):
            continue
        if exclude_globs and _matches_exclude(f.relative_to(root), exclude_globs):
            continue
        files.append(f)
    return files


def get_all_ui_files(root: Path, exclude_globs: list[str]) -> list[Path]:
    """All UI .tsx files outside the design system (mirrors core get_all_ui_files)."""
    if not root.exists():
        return []
    files: list[Path] = []
    for f in sorted(root.rglob("*.tsx")):
        if _is_test(f):
            continue
        if "/maintain-ux/" in str(f):
            continue
        if exclude_globs and _matches_exclude(f.relative_to(root), exclude_globs):
            continue
        files.append(f)
    return files


def extract_imports(file_path: Path) -> list[str]:
    """Import source specifiers (mirrors core extract_imports)."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    import_pattern = r"import\s+.+\s+from\s+['\"](.+)['\"]"
    return re.findall(import_pattern, content)


def extract_imported_names(file_path: Path) -> list[tuple[str, str]]:
    """Imported names + their source paths (mirrors core extract_imported_names)."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    results: list[tuple[str, str]] = []
    pattern = r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]"
    for match in re.finditer(pattern, content):
        names = [n.strip().split(" as ")[0] for n in match.group(1).split(",")]
        path = match.group(2)
        for name in names:
            if name:
                results.append((name.strip(), path))
    pattern2 = r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]"
    for match in re.finditer(pattern2, content):
        name = match.group(1)
        path = match.group(2)
        if name not in ["type", "React", "h"]:
            results.append((name, path))
    return results


def get_design_system_exports(root: Path) -> dict:
    """Exported names from the design system (mirrors core get_design_system_exports)."""
    mux = _maintain_ux(root)
    primitives_dir = mux / "primitives"
    components_dir = mux / "components"
    foundations_dir = mux / "foundations"

    exports = {"primitives": set(), "components": set(), "foundations": set()}

    primitives_index = primitives_dir / "index.ts"
    if primitives_index.exists():
        content = primitives_index.read_text(encoding="utf-8")
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(" as ")[-1] for n in match.group(1).split(",")]
            exports["primitives"].update(n.strip() for n in names if n.strip())

    display_index = primitives_dir / "display" / "index.ts"
    if display_index.exists():
        content = display_index.read_text(encoding="utf-8")
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(" as ")[-1] for n in match.group(1).split(",")]
            exports["primitives"].update(n.strip() for n in names if n.strip())

    components_index = components_dir / "index.ts"
    if components_index.exists():
        content = components_index.read_text(encoding="utf-8")
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(" as ")[-1] for n in match.group(1).split(",")]
            exports["components"].update(n.strip() for n in names if n.strip())

    foundations_index = foundations_dir / "index.ts"
    if foundations_index.exists():
        content = foundations_index.read_text(encoding="utf-8")
        for match in re.finditer(r"export\s+\{([^}]+)\}", content):
            names = [n.strip().split(" as ")[-1] for n in match.group(1).split(",")]
            exports["foundations"].update(n.strip() for n in names if n.strip())
        for match in re.finditer(r"export\s+\*\s+from\s+['\"]\.\/(\w+)['\"]", content):
            submodule = match.group(1)
            subfile = foundations_dir / f"{submodule}.ts"
            if subfile.exists():
                subcontent = subfile.read_text(encoding="utf-8")
                for submatch in re.finditer(r"export\s+(?:const|function|class)\s+(\w+)", subcontent):
                    exports["foundations"].add(submatch.group(1))

    for key in exports:
        exports[key] = {e for e in exports[key] if not e.endswith("Props")}
    return exports


def find_design_system_usage(root: Path) -> set:
    """Names imported from the design system anywhere (mirrors core find_design_system_usage)."""
    used: set = set()
    if not root.exists():
        return used
    for pattern in ("*.ts", "*.tsx"):
        for f in root.rglob(pattern):
            if "/maintain-ux/" in str(f):
                continue
            for name, path in extract_imported_names(f):
                if any(ds in path for ds in ["maintain-ux", "@maintain-ux"]):
                    used.add(name)
    return used


def extract_raw_color_values(file_path: Path) -> list[tuple[int, str]]:
    """Raw hex/rgba color sites (mirrors core extract_raw_color_values)."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(content.split("\n"), 1):
        if line.strip().startswith("import") or line.strip().startswith("//"):
            continue
        if "colors." in line or "colors[" in line:
            continue
        for match in re.findall(r"#[0-9a-fA-F]{6}\b", line):
            if match.lower() not in ["#ffffff", "#000000", "#1a1a1a", "#fff", "#000"]:
                violations.append((i, f"Raw hex color: {match}"))
        if "rgba(" in line.lower() and "colors" not in line:
            violations.append((i, "Raw rgba() color"))
    return violations


def _get_maintain_ux_files(root: Path, subdir: str) -> list[Path]:
    """TS/TSX files under a maintain-ux subdir (mirrors core _get_maintain_ux_files)."""
    base = _maintain_ux(root) / subdir
    if not base.exists():
        return []
    files: list[Path] = []
    for ext in ("*.ts", "*.tsx"):
        for f in base.rglob(ext):
            if not _is_test(f):
                files.append(f)
    return sorted(set(files))


# ── the seven rule emitters (RAW v1.1 dicts) ──────────────────────────────────


def _rule_primitives(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-001: presentation .tsx renders JSX but imports no design system."""
    violations: list[dict] = []
    for f in get_presentation_files(root, exclude_globs):
        imports = extract_imports(f)
        has_jsx = f.suffix == ".tsx"
        has_ds = any(any(ds in imp for ds in DESIGN_SYSTEM_IMPORTS) for imp in imports)
        if has_jsx and not has_ds:
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if re.search(r"return\s*\(?\s*<", content):
                rel = _rel(root, f)
                violations.append({
                    "rule_id": RULE_PRIMITIVES,
                    "file": rel,
                    "line": 1,
                    "col": 0,
                    "evidence": f"{rel}: presentation component without DS imports",
                    "source_line": _line_text(content, 1),
                })
    return violations


def _rule_token_color(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-002: UI file embeds a raw hex/rgba color literal (max 3 per file)."""
    violations: list[dict] = []
    for f in get_all_ui_files(root, exclude_globs):
        color_sites = extract_raw_color_values(f)
        if not color_sites:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            content = ""
        rel = _rel(root, f)
        for line_num, issue in color_sites[:3]:  # core's per-file cap, preserved
            violations.append({
                "rule_id": RULE_COLOR,
                "file": rel,
                "line": line_num,
                "col": 0,
                "evidence": issue,
                "source_line": _line_text(content, line_num),
            })
    return violations


def _rule_orphan_export(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-003: a design-system primitive/component export has no consumer."""
    exports = get_design_system_exports(root)
    used = find_design_system_usage(root)
    all_exports = exports["primitives"] | exports["components"]
    orphaned = all_exports - used
    orphaned = orphaned - {"type", "h", "Fragment"}  # core false positives

    # Locate the export declaration so the violation points at a real site.
    mux = _maintain_ux(root)
    index_files = [
        mux / "primitives" / "index.ts",
        mux / "primitives" / "display" / "index.ts",
        mux / "components" / "index.ts",
    ]

    def _export_site(name: str) -> tuple[str, int, str]:
        pat = re.compile(r"\b" + re.escape(name) + r"\b")
        for idx in index_files:
            if not idx.exists():
                continue
            try:
                lines = idx.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if "export" in line and pat.search(line):
                    return _rel(root, idx), i, line
        # No declaration line found — orphan is an absence; synthesize a site.
        return f"maintain-ux/{name}", 1, ""

    violations: list[dict] = []
    for name in sorted(orphaned):
        rel, line, source_line = _export_site(name)
        violations.append({
            "rule_id": RULE_ORPHAN_EXPORT,
            "file": rel,
            "line": line,
            "col": 0,
            "evidence": f"orphaned export: {name}",
            "source_line": source_line,
        })
    return violations


def _rule_foundations(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-004: a DS primitive/component embeds raw pixels w/o foundations."""
    violations: list[dict] = []
    for category in ("primitives", "components"):
        for f in _get_maintain_ux_files(root, category):
            if f.suffix == ".ts" and f.name == "index.ts":
                continue  # core skipped index.ts (only .tsx category files)
            if f.suffix != ".tsx":
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue
            imports = extract_imports(f)
            uses_foundations = any(
                "../foundations" in imp or "./foundations" in imp for imp in imports
            )
            raw_pixels = re.findall(r":\s*['\"]?(\d{2,}px)['\"]?", content)
            if raw_pixels and not uses_foundations:
                rel = _rel(root, f)
                violations.append({
                    "rule_id": RULE_FOUNDATIONS,
                    "file": rel,
                    "line": 1,
                    "col": 0,
                    "evidence": f"{rel}: raw pixel values {', '.join(raw_pixels[:5])}",
                    "source_line": _line_text(content, 1),
                })
    return violations


def _rule_hierarchy_import(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-005: a design-system file breaks the layer import hierarchy."""
    mux = _maintain_ux(root)
    primitives_files = _get_maintain_ux_files(root, "primitives")
    components_files = _get_maintain_ux_files(root, "components")
    all_ds_files: list[Path] = []
    if mux.exists():
        for ext in ("*.ts", "*.tsx"):
            for f in mux.rglob(ext):
                if not _is_test(f):
                    all_ds_files.append(f)
    all_ds_files = sorted(set(all_ds_files))

    if not primitives_files and not components_files and not all_ds_files:
        return []  # core pytest.skip — nothing to check

    violations: list[dict] = []

    def _emit(f: Path, detail: str) -> None:
        rel = _rel(root, f)
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            content = ""
        violations.append({
            "rule_id": RULE_HIERARCHY_IMPORT,
            "file": rel,
            "line": 1,
            "col": 0,
            "evidence": detail,
            "source_line": _line_text(content, 1),
        })

    # VC-DS-03: primitives must not import components or templates.
    for f in primitives_files:
        for imp in extract_imports(f):
            if "../components/" in imp or "../components" == imp:
                _emit(f, f"primitives → components (import '{imp}')")
            if "../templates/" in imp or "../templates" == imp:
                _emit(f, f"primitives → templates (import '{imp}')")

    # VC-DS-04: components must not import templates.
    for f in components_files:
        for imp in extract_imports(f):
            if "../templates/" in imp or "../templates" == imp:
                _emit(f, f"components → templates (import '{imp}')")

    # VC-DS-05 / VC-DS-06: no design-system file reaches into a wagon.
    for f in all_ds_files:
        for imp in extract_imports(f):
            if imp.startswith(".") or imp.startswith("@/maintain-ux"):
                continue
            if imp.startswith("preact") or imp.startswith("@preact"):
                continue
            if imp.startswith("@/") or imp.startswith("../"):
                _emit(f, f"design system → wagon (import '{imp}')")
    return violations


def _rule_token_hardcoded(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-006: wagon UI file hardcodes spacing/radii/duration (max 3 per file)."""
    patterns = [
        (r'''(?:padding|margin|gap|top|bottom|left|right|width|height)\s*:\s*["'](\d+)px["']''',
         "Hardcoded pixel value in style string"),
        (r"""\$\{\s*(\d+)\s*\}px""",
         "Hardcoded pixel value in template literal"),
        (r'''borderRadius\s*:\s*["'](\d+)px["']''',
         "Hardcoded border-radius string"),
        (r"""borderRadius\s*:\s*(\d+)\s*[,}\n]""",
         "Hardcoded border-radius number"),
        (r'''(?:transition|animation(?:Duration)?)\s*:\s*["'][^"']*?(\d{2,})ms''',
         "Hardcoded duration"),
        (r"""(?:padding|margin|gap)\s*:\s*(\d+)\s*[,}\n]""",
         "Hardcoded numeric spacing"),
    ]
    violations: list[dict] = []
    for f in get_all_ui_files(root, exclude_globs):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        file_sites: list[tuple[int, str]] = []
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("import") or stripped.startswith("//") or stripped.startswith("/*"):
                continue
            if "spacing." in line or "radii." in line or "motion." in line or "tokens." in line:
                continue
            for pattern, description in patterns:
                for match in re.finditer(pattern, line):
                    value = int(match.group(1))
                    if value <= 4:  # borders (1px/2px) and zeros — core exclusion
                        continue
                    file_sites.append((i, f"{description}: {match.group(0).strip()}"))
        if file_sites:
            rel = _rel(root, f)
            for line_num, issue in file_sites[:3]:  # core's per-file cap, preserved
                violations.append({
                    "rule_id": RULE_HARDCODED,
                    "file": rel,
                    "line": line_num,
                    "col": 0,
                    "evidence": issue,
                    "source_line": _line_text(content, line_num),
                })
    return violations


def _rule_orphan_ui(root: Path, exclude_globs: list[str]) -> list[dict]:
    """DESIGN-007: ANY JSX-rendering .tsx imports nothing from the design system."""
    violations: list[dict] = []
    for f in get_all_ui_files(root, exclude_globs):
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if not re.search(r"return\s*\(?\s*<", content):
            continue
        imports = extract_imports(f)
        has_ds = any("maintain-ux" in imp or "@maintain-ux" in imp for imp in imports)
        if not has_ds:
            rel = _rel(root, f)
            violations.append({
                "rule_id": RULE_ORPHAN_UI,
                "file": rel,
                "line": 1,
                "col": 0,
                "evidence": f"{rel}: TSX component with zero design system imports",
                "source_line": _line_text(content, 1),
            })
    return violations


_RULE_EMITTERS = (
    _rule_primitives,
    _rule_token_color,
    _rule_orphan_export,
    _rule_foundations,
    _rule_hierarchy_import,
    _rule_token_hardcoded,
    _rule_orphan_ui,
)


# ── public scan API (the v1.1 contract surface) ───────────────────────────────


def scan_root(root: Path, exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan one web/src-equivalent ``root`` and return RAW v1.1 violation dicts.

    Runs all seven design-system checks; ``maintain-ux/`` is read directly under
    ``root`` and layer membership from the path under ``root``. Emits up to seven
    distinct rule_ids in one run (§3). ``file`` is relative to ``root``.
    """
    root = Path(root)
    exclude_globs = exclude_globs or []
    if not root.exists():
        return []
    violations: list[dict] = []
    for emitter in _RULE_EMITTERS:
        violations.extend(emitter(root, exclude_globs))
    return violations


def scan_roots(roots: list[Path], exclude_globs: list[str] | None = None) -> list[dict]:
    """Scan every root and return the concatenated RAW violation list."""
    out: list[dict] = []
    for r in roots:
        out.extend(scan_root(Path(r), exclude_globs))
    return out
