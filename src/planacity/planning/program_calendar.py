"""Read-only shared calendar events projected onto the planning horizon."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from planacity.domain import CalendarEventKind, PlanningHorizon, ProgramPlan


class CalendarProjectionState(StrEnum):
    INSIDE = "inside"
    PARTIAL = "partial"
    OUTSIDE = "outside"


@dataclass(frozen=True, kw_only=True)
class ProgramCalendarEntry:
    id: UUID
    name: str
    kind: CalendarEventKind
    start: date
    end: date
    unavailable_fraction: Decimal
    state: CalendarProjectionState
    visible_start_day: int | None
    visible_end_day: int | None


@dataclass(frozen=True, kw_only=True)
class ProgramCalendarProjection:
    horizon: PlanningHorizon
    total_days: int
    entries: tuple[ProgramCalendarEntry, ...]

    @property
    def visible_entries(self) -> tuple[ProgramCalendarEntry, ...]:
        return tuple(
            entry for entry in self.entries if entry.state != CalendarProjectionState.OUTSIDE
        )

    @property
    def outside_count(self) -> int:
        return sum(entry.state == CalendarProjectionState.OUTSIDE for entry in self.entries)


def project_program_calendar(plan: ProgramPlan) -> ProgramCalendarProjection:
    """Classify every event and clip only its optional display coordinates."""
    horizon = plan.horizon
    total_days = (horizon.end - horizon.start).days + 1
    entries: list[ProgramCalendarEntry] = []
    for event in sorted(
        plan.calendar_events,
        key=lambda value: (
            value.period.start,
            value.period.end,
            value.name.casefold(),
            str(value.id),
        ),
    ):
        outside = event.period.end < horizon.start or event.period.start > horizon.end
        partial = not outside and (
            event.period.start < horizon.start or event.period.end > horizon.end
        )
        state = (
            CalendarProjectionState.OUTSIDE
            if outside
            else CalendarProjectionState.PARTIAL
            if partial
            else CalendarProjectionState.INSIDE
        )
        entries.append(
            ProgramCalendarEntry(
                id=event.id,
                name=event.name,
                kind=event.kind,
                start=event.period.start,
                end=event.period.end,
                unavailable_fraction=event.unavailable_fraction,
                state=state,
                visible_start_day=(
                    None if outside else max(0, (event.period.start - horizon.start).days)
                ),
                visible_end_day=(
                    None
                    if outside
                    else min(total_days - 1, (event.period.end - horizon.start).days)
                ),
            )
        )
    return ProgramCalendarProjection(
        horizon=horizon,
        total_days=total_days,
        entries=tuple(entries),
    )
