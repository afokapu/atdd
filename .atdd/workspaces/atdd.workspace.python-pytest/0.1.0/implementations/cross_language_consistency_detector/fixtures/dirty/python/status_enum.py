"""Dirty: StatusEnum has fewer members than the Dart enum -> xlang-enum."""
from enum import Enum


class StatusEnum(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
