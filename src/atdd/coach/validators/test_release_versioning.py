"""
Release versioning validation.

Ensures:
- .atdd/config.yaml defines release.version_file
- Version file exists and contains a version
- Git tag on HEAD matches tag_prefix + version
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()
CONFIG_FILE = REPO_ROOT / ".atdd" / "config.yaml"


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        pytest.skip(f"Config not found: {CONFIG_FILE}. Run 'atdd init' first.")

    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f) or {}


def _get_release_config(config: dict) -> tuple[str, str]:
    release = config.get("release")
    if not isinstance(release, dict):
        pytest.fail(
            "Missing release config in .atdd/config.yaml. "
            "Add release.version_file and release.tag_prefix."
        )

    version_file = release.get("version_file")
    if not version_file or not isinstance(version_file, str):
        pytest.fail("Missing release.version_file in .atdd/config.yaml.")

    tag_prefix = release.get("tag_prefix", "v")
    if tag_prefix is None:
        tag_prefix = ""
    if not isinstance(tag_prefix, str):
        pytest.fail("release.tag_prefix must be a string.")

    return version_file, tag_prefix


def _read_version_from_file(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"Version file not found: {path}")

    if path.name == "pyproject.toml":
        version = _parse_pyproject_version(path)
    elif path.name == "package.json":
        version = _parse_package_json_version(path)
    else:
        version = _parse_plain_version(path)
        if not version:
            pytest.fail(
                f"Could not read version from {path}. "
                "Expected first non-comment line to contain a semver like "
                "'1.2.3' or '1.2.3 - short summary'."
            )

    if not version:
        pytest.fail(f"Could not read version from {path}")

    return version


def _parse_pyproject_version(path: Path) -> Optional[str]:
    text = path.read_text()

    # Try tomllib/tomli first for correctness
    data = _load_toml(text)
    if isinstance(data, dict):
        project = data.get("project", {})
        if isinstance(project, dict) and project.get("version"):
            return str(project["version"]).strip()
        tool = data.get("tool", {})
        if isinstance(tool, dict):
            poetry = tool.get("poetry", {})
            if isinstance(poetry, dict) and poetry.get("version"):
                return str(poetry["version"]).strip()

    # Fallback to lightweight parsing
    return _parse_pyproject_version_text(text)


def _load_toml(text: str) -> Optional[dict]:
    try:
        import tomllib  # type: ignore[attr-defined]
        return tomllib.loads(text)
    except Exception:
        try:
            import tomli  # type: ignore
            return tomli.loads(text)
        except Exception:
            return None


def _parse_pyproject_version_text(text: str) -> Optional[str]:
    current_section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped.strip("[]").strip()
            continue
        if current_section in {"project", "tool.poetry"}:
            match = re.match(r'version\s*=\s*["\']([^"\']+)["\']', stripped)
            if match:
                return match.group(1).strip()
    return None


def _parse_package_json_version(path: Path) -> Optional[str]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None

    version = data.get("version")
    return str(version).strip() if version else None


def _parse_plain_version(path: Path) -> Optional[str]:
    version_pattern = re.compile(
        r"\bv?(?P<version>\d+\.\d+(?:\.\d+)?(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\b"
    )
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = version_pattern.search(stripped)
        if match:
            return match.group("version")
        return None
    return None


def _git_tags_on_head(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--points-at", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "git tag --points-at HEAD failed"
        pytest.fail(stderr)

    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return tags


def test_release_version_file_and_tag_on_head():
    """
    SPEC-RELEASE-0001: Version file exists and tag on HEAD matches version.
    """
    config = _load_config()
    version_file, tag_prefix = _get_release_config(config)

    version_path = Path(version_file)
    if not version_path.is_absolute():
        version_path = (REPO_ROOT / version_path).resolve()

    version = _read_version_from_file(version_path)
    expected_tag = f"{tag_prefix}{version}"

    tags = _git_tags_on_head(REPO_ROOT)
    if not tags:
        pytest.fail(
            "No git tag found on HEAD. "
            f"Create tag: git tag {expected_tag}"
        )

    if expected_tag not in tags:
        found = ", ".join(tags) if tags else "none"
        pytest.fail(
            f"Expected tag '{expected_tag}' on HEAD, found: {found}"
        )
