"""Plan-wide estimate presentation, independent of canonical hour estimates."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from planacity.domain.work_calendar import WorkCalendar


class EstimateUnit(StrEnum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"

    @property
    def symbol(self) -> str:
        return {self.HOURS: "h", self.DAYS: "d", self.WEEKS: "w"}[self]


@dataclass(frozen=True, kw_only=True)
class EstimatePreferences:
    unit: EstimateUnit = EstimateUnit.HOURS
    calendar_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.unit, EstimateUnit):
            raise ValueError("Choose hours, days, or weeks for estimate units.")
        if self.calendar_id is not None and not isinstance(self.calendar_id, UUID):
            raise ValueError("Estimate calendar reference must be a UUID.")
        if self.unit != EstimateUnit.HOURS and self.calendar_id is None:
            raise ValueError("Choose a work calendar to define estimate days or weeks.")

    def validate_calendars(self, calendars: tuple[WorkCalendar, ...]) -> None:
        if self.calendar_id is None:
            return
        calendar = next((c for c in calendars if c.id == self.calendar_id), None)
        if calendar is None:
            raise ValueError(
                "Estimate units reference a missing calendar. Choose another calendar "
                "or switch to Hours before removing it."
            )
        if not any(hours > 0 for hours in calendar.weekday_hours):
            raise ValueError("The estimate reference calendar must have positive working hours.")
