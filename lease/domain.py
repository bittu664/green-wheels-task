from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(StrEnum):
    PAID = "payment_made"
    MISSED = "payment_missed"
    PAUSED = "lease_paused"


class Fact(BaseModel):
    event_id: UUID
    driver_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    event_type: EventType


def apply_fact(cycle: int, event: EventType) -> tuple[str, int]:
    return {
        EventType.PAID: ("active", cycle + 1),
        EventType.MISSED: ("overdue", cycle),
        EventType.PAUSED: ("paused", cycle),
    }[event]


def freshness_outcome(projected_at, deadline):
    return "good" if projected_at is not None and projected_at <= deadline else "bad"
