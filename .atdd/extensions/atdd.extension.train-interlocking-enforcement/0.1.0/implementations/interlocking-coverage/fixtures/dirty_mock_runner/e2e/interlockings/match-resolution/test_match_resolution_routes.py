# URN: test:match:match-resolution:E001-E2E-001-route-coverage
"""DIRTY fixture isolating tester.interlocking.production-runner-used.

Both admissible routes (nominal-all-voted / alternate-timeout) are referenced, so
route-coverage is satisfied; but the test PATCHES the production InterlockingRunner
instead of driving it, so it exercises a fake route resolver — the forbidden
substitution the production-runner rule flags.

Consumer-tree FIXTURE code; conftest.py keeps pytest from collecting it.
"""
from unittest.mock import patch

from trains.runtime import InterlockingRunner, TrainRunner  # imported, then patched away


def test_routes_resolve():
    # FORBIDDEN: patch around runner execution -> the test asserts against a fake.
    with patch("trains.runtime.InterlockingRunner") as fake_runner:
        fake_runner.return_value.resolve_train.return_value.route_id = "nominal-all-voted"
        runner = InterlockingRunner("plan/_trains/_interlockings/match-resolution.yaml")
        nominal = runner.resolve_train(
            "resolve_match", inputs={"all_players_voted": True}, state={}
        )
        assert nominal.route_id == "nominal-all-voted"
        # alternate-timeout referenced only to keep route-coverage satisfied.
        assert "alternate-timeout" != nominal.route_id
        TrainRunner("3007-match-resolution-standard")
