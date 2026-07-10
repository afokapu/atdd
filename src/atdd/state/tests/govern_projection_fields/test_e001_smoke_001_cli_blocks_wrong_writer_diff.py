# URN: test:govern-projection-fields:validate-field-writer:E001-SMOKE-001-cli-blocks-wrong-writer-diff
# Acceptance: acc:govern-projection-fields:E001-SMOKE-001-cli-blocks-wrong-writer-diff
# WMBT: wmbt:govern-projection-fields:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: RED skeleton for acc:govern-projection-fields:E001-SMOKE-001-cli-blocks-wrong-writer-diff — fails until the govern-projection-fields wagon implements it. Refs #1400.
"""RED skeleton for acc:govern-projection-fields:E001-SMOKE-001-cli-blocks-wrong-writer-diff.

wagon: govern-projection-fields | feature: validate-field-writer | phase: SMOKE
WMBT: wmbt:govern-projection-fields:E001

STATUS: RED (xfail-strict). Executable statement of intent for the acceptance; it fails
until the govern-projection-fields wagon lands the behaviour. When it xpasses, drop the xfail
marker and assert the real behaviour. Refs #1400.
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.xfail(strict=True, reason="govern-projection-fields not yet implemented (RED; #1400)")
def test_e001_smoke_001_cli_blocks_wrong_writer_diff(tmp_path) -> None:
    """E001-SMOKE-001-cli-blocks-wrong-writer-diff — behaviour not yet implemented."""
    raise AssertionError(
        "RED: govern-projection-fields acceptance acc:govern-projection-fields:E001-SMOKE-001-cli-blocks-wrong-writer-diff is not implemented yet"
    )
