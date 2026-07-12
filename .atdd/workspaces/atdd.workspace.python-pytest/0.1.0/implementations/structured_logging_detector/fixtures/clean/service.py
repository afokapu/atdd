"""GREEN fixture: every logging call carries structured context (extra=), and no
console-print is used. The detector emits ZERO raw violations here."""
import logging

logger = logging.getLogger(__name__)


def make(uid):
    logger.info("user created", extra={"user_id": uid})
    logger.error("creation failed", extra={"user_id": uid})
    return uid
