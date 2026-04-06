"""
Ratchet baseline infrastructure for coder validators.

Allows validators to ship with a baseline violation count so that
pre-existing debt does not block adoption.  The ratchet ensures
violation counts can only decrease, never increase.
"""
