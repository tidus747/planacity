"""Read-only team projection over canonical work and shared dated capacity."""

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.capacity import CapacityGap
from planacity.planning.capacity_breakdown import (
    CapacityBucketScale,
    CapacityLoadState,
    calculate_capacity_breakdown,
)
from planacity.planning.timeline_availability import TimelineUnavailabilityEntry


@dataclass(frozen=True, kw_only=True)
class TeamTimelineWork:
    allocation_id: UUID
    work_item_id: UUID
    title: str
    start: date
    end: date
    visible_start_day: int
    visible_end_day: int
    hours: Fraction


@dataclass(frozen=True, kw_only=True)
class TeamTimelineUnplacedWork:
    allocation_id: UUID
    work_item_id: UUID
    title: str
    hours: Fraction


@dataclass(frozen=True, kw_only=True)
class TeamTimelineDuty:
    rule_id: UUID
    name: str
    hours: Fraction


@dataclass(frozen=True, kw_only=True)
class TeamTimelineDutyDay:
    day: date
    day_offset: int
    duties: tuple[TeamTimelineDuty, ...]


@dataclass(frozen=True, kw_only=True)
class TeamTimelineWeek:
    start: date
    end: date
    visible_start_day: int
    visible_end_day: int
    planning_hours: Fraction | None
    allocated_hours: Fraction | None
    remaining_hours: Fraction | None
    state: CapacityLoadState
    gaps: tuple[CapacityGap, ...]


@dataclass(frozen=True, kw_only=True)
class TeamTimelinePerson:
    person_id: UUID
    person_name: str
    work: tuple[TeamTimelineWork, ...]
    unplaced_work: tuple[TeamTimelineUnplacedWork, ...]
    absences: tuple[TimelineUnavailabilityEntry, ...]
    duty_days: tuple[TeamTimelineDutyDay, ...]
    weeks: tuple[TeamTimelineWeek, ...]
    gaps: tuple[CapacityGap, ...]


@dataclass(frozen=True, kw_only=True)
class TeamTimelineProjection:
    horizon: PlanningHorizon
    total_days: int
    people: tuple[TeamTimelinePerson, ...]


def _week_periods(horizon: PlanningHorizon) -> tuple[PlanningHorizon, ...]:
    periods = []
    start = horizon.start
    while start <= horizon.end:
        end = min(horizon.end, start + timedelta(days=6 - start.weekday()))
        periods.append(PlanningHorizon(start, end))
        start = end + timedelta(days=1)
    return tuple(periods)


def _absence_entries(plan: ProgramPlan, person_id: UUID) -> tuple[TimelineUnavailabilityEntry, ...]:
    horizon = plan.horizon
    total_days = (horizon.end - horizon.start).days + 1
    return tuple(
        sorted(
            (
                TimelineUnavailabilityEntry(
                    id=event.id,
                    start=event.period.start,
                    end=event.period.end,
                    visible_start_day=max(0, (event.period.start - horizon.start).days),
                    visible_end_day=min(total_days - 1, (event.period.end - horizon.start).days),
                    unavailable_fraction=event.unavailable_fraction,
                )
                for event in plan.availability_events
                if event.person_id == person_id
                and event.unavailable_fraction > 0
                and event.period.end >= horizon.start
                and event.period.start <= horizon.end
            ),
            key=lambda entry: (entry.start, entry.end, str(entry.id)),
        )
    )


def project_team_timeline(plan: ProgramPlan) -> TeamTimelineProjection:
    """Combine canonical inputs without adding appointments or changing plan data."""
    horizon = plan.horizon
    total_days = (horizon.end - horizon.start).days + 1
    breakdown = calculate_capacity_breakdown(plan, horizon, CapacityBucketScale.WEEK)
    capacity_by_person = {person.person_id: person for person in breakdown.capacity.people}
    breakdown_by_person = {person.person_id: person for person in breakdown.people}
    rules = {rule.id: rule for rule in plan.reservation_rules}
    items = {item.id: item for item in plan.work_items}

    people = []
    for person in plan.people:
        work = []
        unplaced = []
        for allocation in plan.allocations:
            if allocation.person_id != person.id or allocation.hours <= 0:
                continue
            item = items[allocation.work_item_id]
            if item.start is None or item.end is None:
                unplaced.append(
                    TeamTimelineUnplacedWork(
                        allocation_id=allocation.id,
                        work_item_id=item.id,
                        title=item.title,
                        hours=Fraction(allocation.hours),
                    )
                )
            elif item.end >= horizon.start and item.start <= horizon.end:
                work.append(
                    TeamTimelineWork(
                        allocation_id=allocation.id,
                        work_item_id=item.id,
                        title=item.title,
                        start=item.start,
                        end=item.end,
                        visible_start_day=max(0, (item.start - horizon.start).days),
                        visible_end_day=min(total_days - 1, (item.end - horizon.start).days),
                        hours=Fraction(allocation.hours),
                    )
                )

        capacity = capacity_by_person.get(person.id)
        duty_days: tuple[TeamTimelineDutyDay, ...] = ()
        if capacity is not None:
            duty_days = tuple(
                TeamTimelineDutyDay(
                    day=day.day,
                    day_offset=(day.day - horizon.start).days,
                    duties=tuple(
                        TeamTimelineDuty(
                            rule_id=entry.rule_id,
                            name=rules[entry.rule_id].name,
                            hours=entry.hours,
                        )
                        for entry in day.reservations
                    ),
                )
                for day in capacity.days
                if day.reservations
            )

        person_breakdown = breakdown_by_person[person.id]
        buckets = person_breakdown.buckets
        if person_breakdown.calendar_id is None:
            weeks = tuple(
                TeamTimelineWeek(
                    start=period.start,
                    end=period.end,
                    visible_start_day=(period.start - horizon.start).days,
                    visible_end_day=(period.end - horizon.start).days,
                    planning_hours=None,
                    allocated_hours=None,
                    remaining_hours=None,
                    state=CapacityLoadState.UNKNOWN,
                    gaps=person_breakdown.gaps,
                )
                for period in _week_periods(horizon)
            )
        else:
            weeks = tuple(
                TeamTimelineWeek(
                    start=bucket.period.start,
                    end=bucket.period.end,
                    visible_start_day=max(0, (bucket.period.start - horizon.start).days),
                    visible_end_day=min(total_days - 1, (bucket.period.end - horizon.start).days),
                    planning_hours=bucket.planning_hours,
                    allocated_hours=bucket.allocated_hours,
                    remaining_hours=bucket.remaining_hours,
                    state=bucket.state,
                    gaps=bucket.gaps,
                )
                for bucket in buckets
            )
        people.append(
            TeamTimelinePerson(
                person_id=person.id,
                person_name=person.name,
                work=tuple(
                    sorted(work, key=lambda entry: (entry.start, entry.end, entry.title.casefold()))
                ),
                unplaced_work=tuple(
                    sorted(
                        unplaced,
                        key=lambda entry: (entry.title.casefold(), str(entry.work_item_id)),
                    )
                ),
                absences=_absence_entries(plan, person.id),
                duty_days=duty_days,
                weeks=weeks,
                gaps=person_breakdown.gaps,
            )
        )
    return TeamTimelineProjection(horizon=horizon, total_days=total_days, people=tuple(people))
