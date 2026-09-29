"""Calendar-aligned display coordinates, independent from scheduling and Qt."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from planacity.domain import PlanningHorizon


class TimelineScale(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class TimelinePeriod:
    """Inclusive visible day offsets and the length of the full calendar period."""

    start_day: int
    end_day: int
    full_days: int
    label: str

    @property
    def days(self) -> int:
        return self.end_day - self.start_day + 1


@dataclass(frozen=True)
class TimelineAxis:
    """Calculate columns lazily, including partial edge periods and date limits."""

    horizon: PlanningHorizon
    scale: TimelineScale

    @property
    def total_days(self) -> int:
        return (self.horizon.end - self.horizon.start).days + 1

    @property
    def columns(self) -> int:
        if self.scale == TimelineScale.DAY:
            return self.total_days
        if self.scale == TimelineScale.WEEK:
            return (self.total_days + self.horizon.start.weekday() + 6) // 7
        start, end = self.horizon.start, self.horizon.end
        return (end.year - start.year) * 12 + end.month - start.month + 1

    def period(self, column: int) -> TimelinePeriod:
        if not 0 <= column < self.columns:
            raise IndexError("Timeline column is outside the planning horizon.")
        origin = self.horizon.start.toordinal()
        if self.scale == TimelineScale.DAY:
            first = last = origin + column
            full_days = 1
            day = date.fromordinal(first)
            label = f"{day:%b} {day.day}" if column == 0 or day.day == 1 else str(day.day)
        elif self.scale == TimelineScale.WEEK:
            first = origin - self.horizon.start.weekday() + column * 7
            last = first + 6
            full_days = 7
            iso_year, week, _ = date.fromordinal(first).isocalendar()
            label = f"{iso_year}-W{week:02d}"
        else:
            month_index = self.horizon.start.month - 1 + column
            year = self.horizon.start.year + month_index // 12
            month = month_index % 12 + 1
            first_date = date(year, month, 1)
            first = first_date.toordinal()
            full_days = monthrange(year, month)[1]
            last = first + full_days - 1
            label = f"{first_date:%b} {year}"
        return TimelinePeriod(
            max(first, origin) - origin,
            min(last, self.horizon.end.toordinal()) - origin,
            full_days,
            label,
        )

    def column_for_day(self, day_offset: int) -> int:
        """Locate a day, clamping display navigation to the visible horizon."""
        day_offset = min(max(day_offset, 0), self.total_days - 1)
        if self.scale == TimelineScale.DAY:
            return day_offset
        if self.scale == TimelineScale.WEEK:
            return (day_offset + self.horizon.start.weekday()) // 7
        day = date.fromordinal(self.horizon.start.toordinal() + day_offset)
        return (day.year - self.horizon.start.year) * 12 + day.month - self.horizon.start.month


def bar_span(start_day: int, end_day: int, period: TimelinePeriod) -> tuple[float, float] | None:
    """Return fractional cell edges for the visible part of an inclusive date range."""
    first, last = max(start_day, period.start_day), min(end_day, period.end_day)
    if first > last:
        return None
    return (first - period.start_day) / period.days, (last - period.start_day + 1) / period.days
