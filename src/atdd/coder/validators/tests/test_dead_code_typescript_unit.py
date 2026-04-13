"""
Unit tests for test_dead_code_typescript reachability helpers.

SPEC-CODER-DEADCODE-TS-0001..0004 — BE parity with test_dead_code_python.

Each test builds an isolated synthetic TS/TSX project under a tmp dir and
asserts the graph/reachability primitives behave as specified. No web/src/
dependency: this keeps the unit suite hermetic and fast.
"""

from pathlib import Path
from typing import List

import pytest

from atdd.coder.validators.test_dead_code_typescript import (
    build_file_import_graph,
    extract_import_paths,
    find_reachable_files,
    is_root_file,
    is_test_file,
    resolve_import_to_file,
    scan_dead_code_typescript,
)


def _write(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _collect(root: Path) -> List[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in {".ts", ".tsx"}
    )


def test_extract_import_paths_static_and_dynamic(tmp_path: Path):
    f = _write(
        tmp_path,
        "src/a.ts",
        """
        import { Foo } from './foo';
        import Bar from "../bar";
        export { Baz } from '@/lib/baz';
        import './side-effect';
        const mod = require('commonjs-mod');
        const lazy = import('./lazy');
        """,
    )

    specs = set(extract_import_paths(f))

    assert "./foo" in specs
    assert "../bar" in specs
    assert "@/lib/baz" in specs
    assert "./side-effect" in specs
    assert "commonjs-mod" in specs
    assert "./lazy" in specs


def test_resolve_import_relative_file_with_extension(tmp_path: Path):
    src = _write(tmp_path, "src/a.ts", "import './b';")
    target = _write(tmp_path, "src/b.ts", "export const x = 1;")
    all_files = {src, target}

    resolved = resolve_import_to_file("./b", src, all_files)

    assert target in resolved


def test_resolve_import_directory_index(tmp_path: Path):
    src = _write(tmp_path, "src/a.ts", "import './dir';")
    index = _write(tmp_path, "src/dir/index.ts", "export const x = 1;")
    all_files = {src, index}

    resolved = resolve_import_to_file("./dir", src, all_files)

    assert index in resolved


def test_is_root_file_classification(tmp_path: Path):
    assert is_root_file(tmp_path / "index.ts")
    assert is_root_file(tmp_path / "index.tsx")
    assert is_root_file(tmp_path / "main.tsx")
    assert is_root_file(tmp_path / "composition.ts")
    assert is_root_file(tmp_path / "wagon.ts")
    assert is_root_file(tmp_path / "foo.test.ts")
    assert is_root_file(tmp_path / "foo.spec.tsx")
    assert not is_root_file(tmp_path / "Button.tsx")


def test_is_test_file_directory_detection(tmp_path: Path):
    nested = tmp_path / "feature" / "__tests__" / "Button.tsx"
    assert is_test_file(nested)


def test_reachable_follows_imports(tmp_path: Path):
    _write(tmp_path, "main.tsx", "import './a';")
    _write(tmp_path, "a.ts", "import './b';")
    _write(tmp_path, "b.ts", "export const x = 1;")
    files = _collect(tmp_path)

    graph = build_file_import_graph(files)
    roots = {f for f in files if f.name == "main.tsx"}
    reachable = find_reachable_files(roots, graph)

    assert {f.name for f in reachable} == {"main.tsx", "a.ts", "b.ts"}


def test_scan_reports_unreachable_module(tmp_path: Path, monkeypatch):
    # Force scan_dead_code_typescript to treat tmp_path as the "web/src/" tree.
    import atdd.coder.validators.test_dead_code_typescript as mod

    web_src = tmp_path / "web" / "src"
    _write(web_src, "main.tsx", "import './alive';")
    _write(web_src, "alive.ts", "export const ok = 1;")
    _write(web_src, "dead.ts", "export const lost = 1;")

    count, violations = scan_dead_code_typescript(tmp_path)

    assert count == 1
    assert any("dead.ts" in v for v in violations)
    assert not any("alive.ts" in v for v in violations)
    assert not any("main.tsx" in v for v in violations)


def test_scan_excludes_index_barrels(tmp_path: Path):
    web_src = tmp_path / "web" / "src"
    _write(web_src, "main.tsx", "import './feature';")
    _write(web_src, "feature/index.ts", "export * from './impl';")
    _write(web_src, "feature/impl.ts", "export const x = 1;")
    # A completely orphaned index.ts should still be ignored (structural)
    _write(web_src, "orphan/index.ts", "export const y = 1;")

    count, violations = scan_dead_code_typescript(tmp_path)

    assert count == 0, f"expected index.ts to be excluded, got: {violations}"


def test_scan_missing_web_src_returns_empty(tmp_path: Path):
    count, violations = scan_dead_code_typescript(tmp_path)
    assert count == 0
    assert violations == []
