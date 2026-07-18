# URN: test:migrate-projection-authority:decommission-manifest-fallback:Y002-UNIT-002-no-core-reader-references-manifest
# Acceptance: acc:migrate-projection-authority:Y002-UNIT-002-no-core-reader-references-manifest
# WMBT: wmbt:migrate-projection-authority:Y002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A static scan of the core source tree finds NO module that opens, globs, or parses .atdd/manifest.yaml for lifecycle state — the readers are removed, not deprecated in place — and the scan is proven to bite on each way a reader can spell that read. Refs #1434.
"""No core module retains a manifest read path (Y002-UNIT-002).

wagon: migrate-projection-authority | feature: decommission-manifest-fallback | phase: GREEN
WMBT: wmbt:migrate-projection-authority:Y002

"Removed, not deprecated in place" is the wording, and it is the wording because a deprecated reader
still reads. While `.atdd/manifest.yaml` can answer "what phase is #1234 in?", two developers can
hold two different answers and both be reading a file the tool told them to trust.

What the scan looks for is the **read** — Y002's own words are *opens, globs, or parses* — and it
tracks a manifest path through the name a module binds it to, because that is how the readers were
actually written (``self.manifest_file = self.atdd_config_dir / "manifest.yaml"`` … later …
``open(self.manifest_file)``). Naming the path is not the offence: a helper that hands it to
``git commit`` sources nothing, and flagging it would have forced this wagon to delete code that was
never the problem. Refs #1434 / #1400.
"""
from __future__ import annotations

from pathlib import Path

from atdd.state import manifest_fallback as fallback

#: This repo's own `atdd` package — the source tree the claim is about.
CORE = Path(__file__).resolve().parents[3]


def _package(root: Path, source: str) -> Path:
    package = root / "atdd"
    (package / "coach" / "commands").mkdir(parents=True)
    for init in ("__init__.py", "coach/__init__.py", "coach/commands/__init__.py"):
        (package / init).write_text("")
    (package / "coach" / "commands" / "reader.py").write_text(source)
    return package


def test_y002_unit_002_no_core_reader_references_manifest(tmp_path) -> None:
    """The real core tree holds no manifest reader — and the scan that says so demonstrably bites."""
    report = fallback.check(CORE)

    assert report.ok, report.render()
    assert report.reads == []
    assert len(report.scanned) > 100, "the scan covered almost nothing — it would pass vacuously"

    # The exemption is a LIST a reviewer can shorten, not a hole. Only the migration modules — the
    # code that reads the legacy manifest in order to RETIRE it — are exempt.
    assert set(report.exempt) == {f"atdd.{name}" for name in fallback.LEGACY_MODULES}
    assert len(report.exempt) == 4

    # Now prove it BITES, once per way a reader can spell the read.
    scanned = ("coach/commands",)

    # (a) open() on a path bound to an attribute — how the real readers were written.
    package = _package(tmp_path / "attr", (
        "from pathlib import Path\n"
        "import yaml\n"
        "class M:\n"
        "    def __init__(self, root):\n"
        "        self.manifest_file = Path(root) / '.atdd' / 'manifest.yaml'\n"
        "    def load(self):\n"
        "        with open(self.manifest_file) as f:\n"
        "            return yaml.safe_load(f)\n"
    ))
    caught = fallback.check(package, packages=scanned, legacy=())
    assert not caught.ok
    assert caught.reads[0].rule == fallback.RULE_MANIFEST_READ
    assert "manifest_file" in caught.reads[0].target

    # (b) read_text() straight off an inline path — no intermediate name at all.
    package = _package(tmp_path / "inline", (
        "from pathlib import Path\n"
        "import yaml\n"
        "def phase(root):\n"
        "    return yaml.safe_load((Path(root) / '.atdd' / 'manifest.yaml').read_text())\n"
    ))
    assert not fallback.check(package, packages=scanned, legacy=()).ok

    # (c) a module-level path constant, read through a local name.
    package = _package(tmp_path / "const", (
        "from pathlib import Path\n"
        "import yaml\n"
        "_MANIFEST_REL = Path('.atdd/manifest.yaml')\n"
        "def phase(root):\n"
        "    return yaml.safe_load(_MANIFEST_REL.read_text())\n"
    ))
    assert not fallback.check(package, packages=scanned, legacy=()).ok

    # And it does NOT bite on the things that are not reads — or it would be measuring tidiness
    # instead of authority, and this wagon would have had to delete code that was never the problem.

    # (d) handing the path to `git commit`: it writes the manifest out and asks it nothing.
    package = _package(tmp_path / "commit", (
        "import subprocess\n"
        "from pathlib import Path\n"
        "class M:\n"
        "    def __init__(self, root):\n"
        "        self.manifest_file = Path(root) / '.atdd' / 'manifest.yaml'\n"
        "    def commit(self):\n"
        "        if not self.manifest_file.exists():\n"
        "            return\n"
        "        subprocess.run(['git', 'add', str(self.manifest_file)])\n"
    ))
    assert fallback.check(package, packages=scanned, legacy=()).ok

    # (e) prose. A module that DOCUMENTS the retirement is the opposite of a violation.
    package = _package(tmp_path / "prose", (
        '"""The .atdd/manifest.yaml fallback is retired; see manifest.yaml in the runbook."""\n'
        "HELP = 'imports .atdd/manifest.yaml into the store (retired)'\n"
    ))
    assert fallback.check(package, packages=scanned, legacy=()).ok
