# URN: test:self-compliance:config-comments:YBE-UNIT-001-config-writes-preserve-operator-comments
# Phase: RED
# Layer: unit
# Assertion: behavioral
# Runtime: python
"""YBE-UNIT-001 — writing one key back must not destroy the rest of the file.

    Setting or removing a top-level block preserves every comment, blank line
    and key the write did not target.

Four writers in `initializer.py` load `.atdd/config.yaml` with `yaml.safe_load`
and write it back with `yaml.dump`. That round-trip cannot preserve comments —
PyYAML discards them at parse — so a substrate or GitHub-bootstrap write silently
drops whatever the operator wrote. Reproduced on a real config:

    _write_substrate_config: comment before=1 after=0

Each of those writers mutates exactly ONE top-level key (`repo`, `github`), so
the round-trip was never needed. Editing that block in the text leaves every
other byte untouched, and needs no new dependency: `ruamel.yaml` would preserve
comments, but PyYAML is what this project ships.
"""
from __future__ import annotations

import yaml

from atdd.coach.utils.yaml_block_edit import remove_top_level_block, set_top_level_block

_CONFIG = """\
# Header comment the operator wrote
version: '1.0'

# A section they care about
themes:
  0: commons   # trailing comment
  1: plan

toolkit:
  last_version: 4.0.0
"""


def test_setting_a_new_block_preserves_every_comment() -> None:
    out = set_top_level_block(_CONFIG, "repo", {"substrate": {"enabled": True}})
    assert "# Header comment the operator wrote" in out
    assert "# A section they care about" in out
    assert "# trailing comment" in out
    assert yaml.safe_load(out)["repo"] == {"substrate": {"enabled": True}}


def test_replacing_an_existing_block_preserves_the_others() -> None:
    out = set_top_level_block(_CONFIG, "toolkit", {"last_version": "4.47.5"})
    assert "# Header comment the operator wrote" in out
    assert "# trailing comment" in out
    loaded = yaml.safe_load(out)
    assert loaded["toolkit"] == {"last_version": "4.47.5"}
    assert loaded["themes"] == {0: "commons", 1: "plan"}


def test_removing_a_block_preserves_the_others() -> None:
    with_repo = set_top_level_block(_CONFIG, "repo", {"substrate": {"enabled": True}})
    out = remove_top_level_block(with_repo, "repo")
    assert "repo:" not in out
    assert "# Header comment the operator wrote" in out
    assert "# A section they care about" in out
    assert yaml.safe_load(out)["themes"] == {0: "commons", 1: "plan"}


def test_removing_an_absent_block_is_a_no_op() -> None:
    assert remove_top_level_block(_CONFIG, "repo") == _CONFIG


def test_the_document_still_parses_and_keeps_key_order() -> None:
    out = set_top_level_block(_CONFIG, "github", {"repo": "owner/name"})
    assert list(yaml.safe_load(out)) == ["version", "themes", "toolkit", "github"]


def test_a_comment_directly_above_the_replaced_block_survives() -> None:
    """The comment belongs to the operator, not to the value being replaced."""
    src = "# keep me\ntoolkit:\n  last_version: 1.0.0\n"
    out = set_top_level_block(src, "toolkit", {"last_version": "2.0.0"})
    assert out.startswith("# keep me\n")
    assert yaml.safe_load(out)["toolkit"] == {"last_version": "2.0.0"}


def test_setting_the_same_block_twice_is_byte_identical() -> None:
    """`atdd init --force` runs this twice and asserts the file does not change.

    An earlier draft appended a blank separator when the key was absent but not
    when replacing it, so the result depended on whether the key already existed
    and a repeated force-init produced two different files.
    """
    once = set_top_level_block(_CONFIG, "repo", {"test_root": "tests/"})
    twice = set_top_level_block(once, "repo", {"test_root": "tests/"})
    assert once == twice


def test_removing_then_setting_returns_to_the_same_bytes() -> None:
    once = set_top_level_block(_CONFIG, "repo", {"a": 1})
    round_tripped = set_top_level_block(remove_top_level_block(once, "repo"), "repo", {"a": 1})
    assert once == round_tripped
