"""Operator-facing semantic wrappers around generic multiplexer primitives.

`atdd_cmux_send` is the first member: a pre-send classifier shim over
`cmux send` that rejects raw `claude ...` launches (issue #662).
"""
