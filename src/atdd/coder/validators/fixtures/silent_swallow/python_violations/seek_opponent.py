"""Fixture: real-incident shape — silent swallow returning broken success value."""

import logging

logger = logging.getLogger(__name__)


def seek_opponent_silent_return(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except Exception:
        return ""


def seek_opponent_pass_then_fall_through(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except Exception:
        pass
    return ""


def seek_opponent_bare_except(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except:  # noqa: E722
        return "fallback"


def seek_opponent_typed_except(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except (ValueError, KeyError):
        return "default"


class _Match:
    id: str = ""


def _create_match(player_id: str) -> _Match:
    return _Match()
