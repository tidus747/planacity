"""Read-only personal unavailability projected onto the planning horizon."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan


@dataclass(frozen=True, kw_only=True)
class TimelineUnavailabilityEntry:
    """One canonical availability entry with display coordinates clipped to the horizon."""

    id: UUID
    start: date
    end: date
    visible_start_day: int
    visible_end_day: int
    unavailable_fraction: Decimal


@dataclass(frozen=True, kw_only=True)
class TimelineUnavailabilityLane:
    """Every visible unavailability entry for one named roster person."""

    person_id: UUID
    person_name: str
    entries: tuple[TimelineUnavailabilityEntry, ...]


@dataclass(frozen=True, kw_only=True)
class TimelineUnavailabilityProjection:
    """Unavailability lanes aligned with one inclusive planning horizon."""

    horizon: PlanningHorizon
    total_days: int
    lanes: tuple[TimelineUnavailabilityLane, ...]


def project_timeline_unavailability(plan: ProgramPlan) -> TimelineUnavailabilityProjection:
    """Project positive intersecting entries without changing their canonical dates or share."""
    horizon = plan.horizon
    total_days = (horizon.end - horizon.start).days + 1
    by_person: dict[UUID, list[TimelineUnavailabilityEntry]] = {}
    for event in plan.availability_events:
        if (
            event.unavailable_fraction <= 0
            or event.period.end < horizon.start
            or event.period.start > horizon.end
        ):
            continue
        by_person.setdefault(event.person_id, []).append(
            TimelineUnavailabilityEntry(
                id=event.id,
                start=event.period.start,
                end=event.period.end,
                visible_start_day=max(0, (event.period.start - horizon.start).days),
                visible_end_day=min(total_days - 1, (event.period.end - horizon.start).days),
                unavailable_fraction=event.unavailable_fraction,
            )
        )
    lanes = tuple(
        TimelineUnavailabilityLane(
            person_id=person.id,
            person_name=person.name,
            entries=tuple(
                sorted(
                    by_person[person.id],
                    key=lambda entry: (entry.start, entry.end, str(entry.id)),
                )
            ),
        )
        for person in sorted(plan.people, key=lambda value: (value.name.casefold(), str(value.id)))
        if person.id in by_person
    )
    return TimelineUnavailabilityProjection(
        horizon=horizon,
        total_days=total_days,
        lanes=lanes,
    )
