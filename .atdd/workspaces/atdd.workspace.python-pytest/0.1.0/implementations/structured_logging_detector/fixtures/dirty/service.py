"""RED fixture: mixed dispositions. The detector emits THREE raw violations; the
downstream consumer's disposition turns that into TWO unsuppressed -> FAIL.

  - print(...)            -> coder.logging.print (strict)            -> unsuppressed
  - logger.info(...)      -> coder.logging.structured (s&c), no marker -> unsuppressed
  - logger.warning(...)   -> coder.logging.structured (s&c), MARKED    -> suppressed
  - logger.error(..., extra=...) -> compliant, no violation
"""
import logging

logger = logging.getLogger(__name__)


def make(uid):
    print("debugging make")
    logger.info("user created")
    logger.warning("retrying create")  # atdd:suppress(coder.logging.structured) UNTIL=2099-01-01
    logger.error("creation failed", extra={"user_id": uid})
    return uid
