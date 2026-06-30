"""GREEN fixture: every handler observably reacts -> RAW = [] -> disposition PASS."""
import logging

logger = logging.getLogger(__name__)


def create(player_id):
    try:
        return _remote_create(player_id)
    except Exception as e:
        logger.warning("create failed", extra={"player_id": player_id, "error": str(e)})
        raise


def lookup(key):
    try:
        return _remote_lookup(key)
    except RuntimeError as e:
        logger.warning("lookup failed, using fallback", extra={"key": key, "error": str(e)})
        return _cached(key)


def _remote_create(player_id):
    return player_id


def _remote_lookup(key):
    return key


def _cached(key):
    return None
