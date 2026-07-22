"""Operator-facing semantic wrappers around generic multiplexer primitives.

The sole member, ``atdd_cmux_send`` (a pre-send classifier shim that rejected
raw ``claude ...`` launches, #662), was retired with the coach's sub-worker
orchestration (#1483). The package is kept as a namespace anchor for any future
operator-facing wrapper.
"""
