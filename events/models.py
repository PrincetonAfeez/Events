from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from uuid import uuid4

class Severity(IntEnum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3

    @classmethod
    def from_value(cls, value: "Severity | str") -> "Severity":
        if isinstance(value, cls):
            return value

        normalized = value.strip().upper()
        try:
            return cls[normalized]
        except KeyError as error:
            allowed = ", ".join(member.name for member in cls)
            raise ValueError(f"Unknown severity '{value}'. Expected one of: {allowed}.") from error

    def __str__(self) -> str:
        return self.name