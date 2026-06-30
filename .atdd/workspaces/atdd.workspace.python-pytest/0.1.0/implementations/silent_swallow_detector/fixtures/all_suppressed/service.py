"""CRUX fixture: two silent swallows, BOTH suppress-marked. The detector emits
TWO RAW violations (NON-EMPTY) yet the downstream consumer absorbs both markers
-> disposition PASS. The flip happens ENTIRELY in the consumer."""


def create(player_id):
    try:
        return _remote_create(player_id).id
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2099-01-01
        return ""


def cleanup(handle):
    try:
        handle.close()
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2099-01-01
        pass


def _remote_create(player_id):
    return player_id
