"""Fixed-hour recurring duties, separate from work, absences, and allocations."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from planacity.domain.horizon import PlanningHorizon


@dataclass(frozen=True, kw_only=True)
class ReservationRule:
    """Reserve the stated hours for each selected person in every anchored period."""

    name: str
    person_ids: tuple[UUID, ...]
    hours_per_person: Decimal
    anchor: date
    interval_weeks: int
    effective: PlanningHorizon
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ValueError("Reservation ID must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Reservation name must contain non-blank text.")
        if (
            not isinstance(self.person_ids, tuple)
            or not self.person_ids
            or any(not isinstance(person, UUID) for person in self.person_ids)
            or len(set(self.person_ids)) != len(self.person_ids)
        ):
            raise ValueError("Select a non-empty tuple of distinct person UUIDs.")
        hours = self.hours_per_person
        if not isinstance(hours, Decimal) or not hours.is_finite() or hours <= 0:
            raise ValueError("Hours per person must be a positive finite Decimal.")
        if type(self.anchor) is not date:
            raise ValueError("Sprint anchor must be a date without a time.")
        if type(self.interval_weeks) is not int or self.interval_weeks <= 0:
            raise ValueError("Sprint interval must be a positive whole number of weeks.")
        if not isinstance(self.effective, PlanningHorizon):
            raise ValueError("Effective dates must be a PlanningHorizon.")
