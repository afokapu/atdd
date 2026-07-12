"""Clean: StatusEnum members match the Dart enum (case-insensitively)."""
from enum import Enum


class StatusEnum(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
