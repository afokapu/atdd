"""RED fixture: three silent swallows. The detector emits THREE raw violations;
the downstream consumer's suppress-and-clean disposition turns that into TWO
unsuppressed -> FAIL.

  - except returning a value, no log/raise         -> unsuppressed
  - except: pass, no log/raise                     -> unsuppressed
  - except returning a value, MARKED with suppress -> suppressed
"""


def create(player_id):
    try:
        return _remote_create(player_id).id
    except Exception:
        return ""


def cleanup(handle):
    try:
        handle.close()
    except Exception:
        pass


def legacy_lookup(key):
    try:
        return _remote_lookup(key)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2099-01-01
        return None


def _remote_create(player_id):
    return player_id


def _remote_lookup(key):
    return key
