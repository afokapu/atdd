"""Fixture: acceptable shapes — handlers that log + re-raise or log + fallback."""

import logging

logger = logging.getLogger(__name__)


def re_raise_after_log(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except Exception as e:
        logger.warning(
            "match_creator failed",
            extra={"player_id": player_id, "error": str(e)},
        )
        raise


def fallback_after_log(player_id: str) -> str:
    try:
        return _remote_lookup(player_id)
    except Exception as e:
        logger.warning(
            "remote lookup failed, using fallback",
            extra={"player_id": player_id, "error": str(e)},
        )
        return _cached_value(player_id)


def reraise_with_context(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except ValueError as e:
        raise RuntimeError(f"match creation failed for {player_id}") from e


def returns_none_naturally(player_id: str) -> str | None:
    try:
        return _maybe_lookup(player_id)
    except KeyError as e:
        logger.info("lookup miss", extra={"player_id": player_id, "error": str(e)})
        return None


def suppression_pragma(player_id: str) -> str:
    try:
        return _create_match(player_id).id
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
        return ""


class _Match:
    id: str = ""


def _create_match(player_id: str) -> _Match:
    return _Match()


def _remote_lookup(player_id: str) -> str:
    return player_id


def _cached_value(player_id: str) -> str:
    return player_id


def _maybe_lookup(player_id: str) -> str:
    return player_id
