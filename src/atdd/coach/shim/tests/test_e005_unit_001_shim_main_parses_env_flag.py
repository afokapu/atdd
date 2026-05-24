"""E005-UNIT-001 — atdd-shim __main__ parses --env KEY=VALUE (repeatable).

RED: fails until _build_parser gains --env argument.
"""
from __future__ import annotations

import pytest

from atdd.coach.shim.__main__ import _build_parser


def test_single_env_flag_parsed():
    parser = _build_parser()
    args = parser.parse_args([
        "--agent-id", "x-001",
        "--runtime-dir", "/tmp/r",
        "--env", "ATDD_AGENT_ID=x-001",
        "--", "true",
    ])
    assert args.env == ["ATDD_AGENT_ID=x-001"]


def test_multiple_env_flags_all_collected():
    parser = _build_parser()
    args = parser.parse_args([
        "--agent-id", "x-001",
        "--runtime-dir", "/tmp/r",
        "--env", "ATDD_AGENT_ID=x-001",
        "--env", "ATDD_LLM=claude-code",
        "--", "true",
    ])
    assert "ATDD_AGENT_ID=x-001" in args.env
    assert "ATDD_LLM=claude-code" in args.env


def test_no_env_flag_defaults_to_empty_list():
    parser = _build_parser()
    args = parser.parse_args([
        "--agent-id", "x-001",
        "--runtime-dir", "/tmp/r",
        "--", "true",
    ])
    assert args.env == []


def test_unknown_env_key_does_not_raise_system_exit():
    parser = _build_parser()
    args = parser.parse_args([
        "--agent-id", "x-001",
        "--runtime-dir", "/tmp/r",
        "--env", "MY_CUSTOM_VAR=hello",
        "--", "true",
    ])
    assert args.env == ["MY_CUSTOM_VAR=hello"]
