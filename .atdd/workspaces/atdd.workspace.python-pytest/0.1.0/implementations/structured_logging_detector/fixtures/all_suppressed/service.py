"""The crux fixture for the separability proof. Every bare logging call carries a
valid inline suppress marker, and there is NO print() (no strict violations).

The detector emits TWO RAW violations here (it never reads the markers) — so the
provider's output is NON-EMPTY — yet the downstream suppress-and-clean disposition
absorbs both, so the final verdict is PASS. The verdict flips entirely in the
consumer; the provider stays purely factual.
"""
import logging

logger = logging.getLogger(__name__)


def make(uid):
    logger.info("user created")  # atdd:suppress(coder.logging.structured) UNTIL=2099-01-01
    logger.warning("retrying create")  # atdd:suppress(coder.logging.structured) UNTIL=2099-01-01
    logger.error("creation failed", extra={"user_id": uid})
    return uid
