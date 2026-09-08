# URN: test:govern-lifecycle:core-agnosticity:E064-SMOKE-001-built-wheel-ships-no-javascript
# Acceptance: acc:govern-lifecycle:E064-SMOKE-001-built-wheel-ships-no-javascript
# WMBT: wmbt:govern-lifecycle:E064
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""E064-SMOKE-001 — the wheel a consumer installs carries no JavaScript or TypeScript.

Core is the stack-agnostic engine; the stack belongs to a workspace provider
(``atdd.workspace.typescript``, ``frontend.extension.vite-coder``). A ``.ts`` in the
wheel means core froze a language into the engine again (#1518).

Asserted against the BUILT WHEEL rather than the source tree, and that distinction
is load-bearing twice:

  * ``[tool.setuptools.package-data]`` is a broad ``"atdd" = ["**/*"]`` ship-it-all
    glob (#1474/E062), so a stray ``.ts`` anywhere under ``src/atdd/`` reaches
    consumers automatically. Nothing has to opt it in for the leak to happen, which
    is why the guard belongs at the artifact and not at the config text.
  * setuptools does NOT clean ``build/lib`` between runs and ``bdist_wheel`` packs it
    wholesale, so a deleted file can survive into a later wheel. ``_wheel_harness``
    builds from a pristine copy with ``build/`` excluded — that is what makes a green
    here mean "actually gone" rather than "not rebuilt".

Note also what this does NOT do: match on filenames. #1518's original measurement
found 13 TypeScript validators by grepping "typescript" in the FILENAME and missed 11
more that were equally TypeScript-only but not named that way. Suffix-matching the
shipped artifact has no such blind spot.
"""
from __future__ import annotations

import pytest

from atdd.coach.validators.tests._wheel_harness import wheel_members

# Every extension a JS/TS toolchain compiles or a bundler resolves. `.mjs`/`.cjs`
# are included deliberately: the harness leak that survived the first pass of #1518
# arrived as `.mjs`, not `.ts`.
JS_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

# Deliberately exempt, and deliberately EXACT PATHS rather than a directory prefix —
# a prefix would let a new file slip in beside an old one. Each entry has a live
# in-core consumer, which is why #1518 could not remove it:
#
#   coach/templates/harness/*.mjs
#       The Node + @testing-library/preact render harness. `tester/conventions/
#       smoke.convention.yaml` declares this directory as its `template_dir`, and
#       `tester/validators/test_train_renders_content.py` shells out to
#       `node .atdd/harness/mount-train.mjs` (TESTER-RENDER-003). NO extension owns
#       this yet — `tester.vite.presentation-smoke-coverage` explicitly disclaims it
#       ("non-empty content is a distinct RUNTIME concern (a render harness), not
#       this static [check]"). Deleting it would have left a strict rule with an
#       unreachable enforcer, the #1466 failure mode.
#
#   coder/validators/fixtures/composition_completeness/typescript_repo/**
#       `test_composition_completeness.py` is dual-stack: it also exports
#       `analyze_python_root`, which `_four_tier_ratchet.py` and two other modules
#       import. Its TypeScript and Python halves share `stack`-parameterized helpers,
#       so separating them is a port rather than a prune and was left out of #1518.
#
# Both are tracked in #1526 for relocation into `frontend.extension.vite-{coder,tester}`
# — note the harness needs a convention node + implementation AUTHORED there first,
# since nothing owns it yet. When #1526 lands, delete the entries — and once this set
# is empty, delete `test_carveout_covers_only_the_two_sanctioned_locations` with it.
PENDING_RELOCATION = frozenset({
    "atdd/coach/templates/harness/mount-train.mjs",
    "atdd/coach/templates/harness/vitest.config.mjs",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/arena/show-forecast/application/useForecast.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/arena/show-forecast/domain/forecast.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/arena/show-forecast/integration/ForecastGateway.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/arena/show-forecast/presentation/ForecastView.tsx",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/application/useCameoBalance.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/application/useFinalsRewards.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/domain/cameo-types.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/domain/finals-rewards-types.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/integration/CameoRepository.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/integration/FinalsRewardsRepository.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/presentation/FinalsRewardCard.tsx",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/presentation/ProfilePage.tsx",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/manage-profile/display-profile/presentation/ProfileView.tsx",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/reveal-status/display-leaderboard/application/usePlayerRank.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/reveal-status/display-leaderboard/domain/rank.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/reveal-status/display-leaderboard/index.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/reveal-status/display-leaderboard/integration/LeaderboardRepository.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/reveal-status/display-leaderboard/presentation/LeaderboardPage.tsx",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/score/compute-elo/domain/elo.ts",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/web/src/score/compute-elo/integration/EloRepository.ts",
})


def _shipped_js_ts() -> set[str]:
    """Every JS/TS member of the built wheel."""
    return {name for name in wheel_members() if name.endswith(JS_TS_SUFFIXES)}


@pytest.mark.platform
def test_built_wheel_ships_no_javascript_or_typescript() -> None:
    """No JS/TS member ships, bar the exactly-enumerated pending-relocation set."""
    offenders = sorted(_shipped_js_ts() - PENDING_RELOCATION)
    assert not offenders, (
        f"{len(offenders)} JavaScript/TypeScript file(s) ship in the built wheel. Core is "
        f"stack-agnostic — the stack belongs to a workspace provider, so a pure-Python "
        f"consumer must not receive these:\n  "
        + "\n  ".join(offenders)
        + "\n\nIf this is a validator fixture, the validator belongs in "
          "`frontend.extension.vite-coder` / `atdd.extension.coder`, not core (#1518)."
    )


# The only two locations the carve-out is allowed to cover. Anything else is a new
# leak wearing an exemption's clothes.
SANCTIONED_CARVEOUT_PREFIXES = (
    "atdd/coach/templates/harness/",
    "atdd/coder/validators/fixtures/composition_completeness/typescript_repo/",
)


@pytest.mark.platform
def test_carveout_covers_only_the_two_sanctioned_locations() -> None:
    """The allowlist may shrink, but it may not be extended to new places.

    Without this the guard above has an obvious defeat: add a `.ts`, add its path to
    ``PENDING_RELOCATION``, gate stays green. Constraining the allowlist to the two
    directories whose blockers are documented means buying an exemption for anything
    else fails HERE instead — and the fix for a genuinely new file is an extension
    home, not another line in this set.

    Note this asserts over the DECLARED constant, not the shipped set, which is what
    makes it a different question from the test above rather than a restatement of it.
    """
    unsanctioned = sorted(
        path for path in PENDING_RELOCATION
        if not path.startswith(SANCTIONED_CARVEOUT_PREFIXES)
    )
    assert not unsanctioned, (
        f"{len(unsanctioned)} carve-out entr(y/ies) fall outside the two sanctioned "
        f"locations {SANCTIONED_CARVEOUT_PREFIXES}:\n  " + "\n  ".join(unsanctioned)
        + "\n\nThe exemption exists for TESTER-RENDER-003 and the dual-stack "
          "composition-completeness fixtures. New JavaScript elsewhere in core needs "
          "an extension home, not an allowlist entry."
    )


@pytest.mark.platform
def test_no_typescript_grammar_is_a_runtime_dependency() -> None:
    """A pure-Python consumer installs no TypeScript parser.

    The sharpest symptom in #1518: `tree-sitter-typescript` sat in `[project]
    dependencies`, so every consumer — including pure-Python ones — installed a
    TypeScript grammar to use a stack-agnostic engine. Read from the built wheel's
    own metadata rather than pyproject, so this reflects what actually gets resolved
    at install time.
    """
    import zipfile
    from email.parser import BytesParser

    from atdd.coach.validators.tests._wheel_harness import built_wheel

    with zipfile.ZipFile(built_wheel()) as zf:
        metadata_name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(zf.read(metadata_name))

    requires = [r.lower() for r in metadata.get_all("Requires-Dist") or []]
    grammars = [r for r in requires if "tree-sitter" in r or "tree_sitter" in r]
    assert not grammars, (
        f"the wheel declares a language-grammar runtime dependency: {grammars}. Core "
        f"parses Python with `radon` and the stdlib `ast` module; a tree-sitter grammar "
        f"is a workspace-provider concern (#1518)."
    )
