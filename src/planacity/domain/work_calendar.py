"""Explicit nominal working hours, independent of people and external calendars."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class PersonCalendar:
    """One explicit calendar assignment, separate from imported Person snapshots."""

    person_id: UUID
    calendar_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.person_id, UUID) or not isinstance(self.calendar_id, UUID):
            raise ValueError("Person/calendar references must be UUIDs.")


@dataclass(frozen=True, kw_only=True)
class WorkCalendar:
    """A repeating Monday-to-Sunday pattern before leave or other deductions.

    All seven values must be supplied. Zero explicitly identifies a non-working
    day; neither a five-day week nor any particular daily hours are inferred.
    This is a nominal hours model, not a shift timetable or a timezone calendar.
    """

    name: str
    weekday_hours: tuple[Decimal, ...]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ValueError("WorkCalendar ID must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("WorkCalendar name must contain non-blank text.")
        if not isinstance(self.weekday_hours, tuple) or len(self.weekday_hours) != 7:
            raise ValueError(
                "Supply exactly seven weekday hours, Monday through Sunday, as a tuple."
            )
        for weekday, hours in enumerate(self.weekday_hours, start=1):
            if not isinstance(hours, Decimal) or not hours.is_finite() or not 0 <= hours <= 24:
                raise ValueError(
                    f"Weekday {weekday} hours must be a finite Decimal between 0 and 24."
                )

    def hours_on(self, day: date) -> Decimal:
        """Return the nominal hours for one date without applying any exceptions."""
        if type(day) is not date:
            raise ValueError("Calendar day must be a date without a time.")
        return self.weekday_hours[day.weekday()]
