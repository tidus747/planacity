"""Shared program-calendar context with an explicit capacity reduction."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from planacity.domain.horizon import PlanningHorizon


class CalendarEventKind(StrEnum):
    """Initial shared event categories without provider-specific terminology."""

    PUBLIC_HOLIDAY = "public_holiday"
    CUSTOMER_VISIT = "customer_visit"
    COMPANY_EVENT = "company_event"
    PROGRAM_EVENT = "program_event"
    OTHER = "other"


@dataclass(frozen=True, kw_only=True)
class CalendarEvent:
    """An event shared by the plan and every roster person's capacity.

    The unavailable fraction is applied to nominal calendar hours on each date.
    Zero records planning context without reducing capacity; one removes the
    complete nominal day. Personal and shared reductions use the strongest
    active fraction rather than adding possibly overlapping time periods.
    """

    name: str
    kind: CalendarEventKind
    period: PlanningHorizon
    unavailable_fraction: Decimal = Decimal(0)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ValueError("Calendar event ID must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Calendar event name must contain non-blank text.")
        if not isinstance(self.kind, CalendarEventKind):
            raise ValueError("Calendar event kind must be a CalendarEventKind.")
        if not isinstance(self.period, PlanningHorizon):
            raise ValueError("Calendar event period must be a PlanningHorizon.")
        fraction = self.unavailable_fraction
        if not isinstance(fraction, Decimal) or not fraction.is_finite() or not 0 <= fraction <= 1:
            raise ValueError("Unavailable fraction must be a finite Decimal between 0 and 1.")
