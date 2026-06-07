"""Shared logger for the coach-runtime feature.

A single getLogger call the whole feature imports, so the logger name is defined
once (DRY) and the per-module import headers stay distinct.
"""
from __future__ import annotations

import logging

log = logging.getLogger("atdd.coach_runtime")
