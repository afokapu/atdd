# URN: test:govern-lifecycle:smoke-false-green-prevention:L002-UNIT-001-meta-walker-function-exists-and-classifies
# Acceptance: acc:govern-lifecycle:L002-UNIT-001-meta-walker-function-exists-and-classifies
# WMBT: wmbt:govern-lifecycle:L002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""
RED: walk_all_smoke_acceptances_for_anti_patterns(plan_dir) must exist and
return a list containing (urn, hit_description) tuples for any SMOKE
acceptance whose resolved test file uses a synthetic fixture, while returning
nothing for clean tests.  Currently fails because the function does not exist
yet in test_smoke_synthetic_fixture_bypass.py.
"""
from __future__ import annotations

import textwrap

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.planner]


def test_meta_walker_function_exists_and_classifies(tmp_path):
    """walk_all_smoke_acceptances_for_anti_patterns returns hits for synthetic, none for real."""
    from atdd.planner.validators.test_smoke_synthetic_fixture_bypass import (
        walk_all_smoke_acceptances_for_anti_patterns,
    )

    # WMBT YAML with a synthetic-fixture SMOKE acceptance
    bad_test = tmp_path / "test_bad_smoke.py"
    bad_test.write_text(
        textwrap.dedent(
            """\
            from atdd.coach.fake_multiplexer import FakeMultiplexer
            import pytest
            pytestmark = [pytest.mark.smoke, pytest.mark.platform]
            def test_bad(tmp_path):
                mux = FakeMultiplexer()
                assert mux
            """
        )
    )

    # WMBT YAML with a real-entry-point SMOKE acceptance
    good_test = tmp_path / "test_good_smoke.py"
    good_test.write_text(
        textwrap.dedent(
            """\
            import subprocess
            import pytest
            pytestmark = [pytest.mark.smoke, pytest.mark.platform]
            def test_good(tmp_path):
                result = subprocess.run(
                    ["atdd", "spawn", "--help"], capture_output=True, timeout=10
                )
                assert result.returncode == 0
            """
        )
    )

    # WMBT filenames must match [DLPCEMYRK]\d{3}.yaml pattern used by the walker
    bad_wmbt = tmp_path / "E901.yaml"
    bad_wmbt.write_text(
        yaml.dump(
            {
                "urn": "wmbt:test-wagon:E901",
                "acceptances": [
                    {
                        "identity": {
                            "urn": "acc:test-wagon:E901-SMOKE-001-bad",
                            "id": "AC-SMOKE-001",
                            "phase": "SMOKE",
                        },
                        "harness": {"type": "smoke", "category": "backend"},
                        "given": {"abstract": ["x"]},
                        "when": {"abstract": "y"},
                        "then": {"abstract": ["z"]},
                    }
                ],
            }
        )
    )

    good_wmbt = tmp_path / "E902.yaml"
    good_wmbt.write_text(
        yaml.dump(
            {
                "urn": "wmbt:test-wagon:E902",
                "acceptances": [
                    {
                        "identity": {
                            "urn": "acc:test-wagon:E902-SMOKE-001-good",
                            "id": "AC-SMOKE-001",
                            "phase": "SMOKE",
                        },
                        "harness": {"type": "smoke", "category": "backend"},
                        "given": {"abstract": ["x"]},
                        "when": {"abstract": "y"},
                        "then": {"abstract": ["z"]},
                    }
                ],
            }
        )
    )

    def _resolve(urn: str):
        if "E901" in urn:
            return bad_test
        return good_test

    hits = walk_all_smoke_acceptances_for_anti_patterns(
        plan_dir=tmp_path,
        resolve_test_file=_resolve,
    )

    hit_urns = [h[0] for h in hits]
    assert "acc:test-wagon:E901-SMOKE-001-bad" in hit_urns, (
        f"Expected synthetic-fixture acceptance in hits, got: {hit_urns}"
    )
    assert "acc:test-wagon:E902-SMOKE-001-good" not in hit_urns, (
        f"Real-entry-point acceptance must NOT appear in hits, got: {hit_urns}"
    )
