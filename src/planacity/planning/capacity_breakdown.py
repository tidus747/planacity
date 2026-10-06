"""Deterministic People-facing aggregation over shared dated capacity."""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.availability import availability_capacity
from planacity.planning.capacity import (
    AllocationHours,
    CapacityGap,
    DatedCapacity,
    DatedCapacityDay,
    PersonDatedCapacity,
    ReservationHours,
    calculate_dated_capacity,
)


class CapacityBucketScale(StrEnum):
    DAY = "day"
    WEEK = "week"
    PERIOD = "period"


class CapacityLoadState(StrEnum):
    UNKNOWN = "unknown"
    INCOMPLETE = "incomplete"
    OVERLOADED = "overloaded"
    FULL = "full"
    WITHIN_CAPACITY = "within_capacity"
    NO_WORK = "no_work"
    NO_CAPACITY = "no_capacity"


@dataclass(frozen=True)
class CapacityBucket:
    period: PlanningHorizon
    nominal_hours: Fraction | None
    unavailable_hours: Fraction | None
    available_hours: Fraction | None
    reserved_hours: Fraction | None
    planning_hours: Fraction | None
    allocated_hours: Fraction | None
    remaining_hours: Fraction | None
    reservations: tuple[ReservationHours, ...]
    allocations: tuple[AllocationHours, ...]
    gaps: tuple[CapacityGap, ...]
    state: CapacityLoadState

    @property
    def load_fraction(self) -> Fraction | None:
        if self.planning_hours is None or self.planning_hours <= 0:
            return None
        assert self.allocated_hours is not None
        return self.allocated_hours / self.planning_hours


@dataclass(frozen=True)
class PersonCapacityBreakdown:
    person_id: UUID
    calendar_id: UUID | None
    period: PlanningHorizon
    nominal_hours: Fraction | None
    working_days: int | None
    unavailable_hours: Fraction | None
    available_hours: Fraction | None
    overlap_periods: int | None
    reserved_hours: Fraction | None
    planning_hours: Fraction | None
    allocated_hours: Fraction | None
    remaining_hours: Fraction | None
    unplaced_hours: Fraction
    gaps: tuple[CapacityGap, ...]
    state: CapacityLoadState
    buckets: tuple[CapacityBucket, ...]


@dataclass(frozen=True)
class CapacityBreakdown:
    period: PlanningHorizon
    scale: CapacityBucketScale
    capacity: DatedCapacity
    people: tuple[PersonCapacityBreakdown, ...]

    def person(self, person_id: UUID) -> PersonCapacityBreakdown:
        for person in self.people:
            if person.person_id == person_id:
                return person
        raise ValueError(f"Person {person_id} does not exist in this capacity result.")


def _intersects(first: PlanningHorizon, second: PlanningHorizon) -> bool:
    return first.start <= second.end and second.start <= first.end


def _relevant_gaps(
    gaps: tuple[CapacityGap, ...], period: PlanningHorizon
) -> tuple[CapacityGap, ...]:
    return tuple(gap for gap in gaps if gap.period is None or _intersects(gap.period, period))


def _state(
    *,
    capacity_known: bool,
    planning: Fraction | None,
    allocated: Fraction | None,
    remaining: Fraction | None,
    gaps: tuple[CapacityGap, ...],
    overloaded: bool = False,
) -> CapacityLoadState:
    if not capacity_known or planning is None or allocated is None or remaining is None:
        return CapacityLoadState.UNKNOWN
    if overloaded or remaining < 0:
        return CapacityLoadState.OVERLOADED
    if gaps:
        return CapacityLoadState.INCOMPLETE
    if planning <= 0:
        return CapacityLoadState.NO_CAPACITY
    if allocated == 0:
        return CapacityLoadState.NO_WORK
    if remaining == 0:
        return CapacityLoadState.FULL
    return CapacityLoadState.WITHIN_CAPACITY


def _source_totals(
    days: tuple[DatedCapacityDay, ...],
) -> tuple[tuple[ReservationHours, ...], tuple[AllocationHours, ...]]:
    reservations: dict[UUID, Fraction] = {}
    allocations: dict[tuple[UUID, UUID], Fraction] = {}
    for day in days:
        for reservation_entry in day.reservations:
            reservations[reservation_entry.rule_id] = (
                reservations.get(reservation_entry.rule_id, Fraction()) + reservation_entry.hours
            )
        for allocation_entry in day.allocations:
            key = (allocation_entry.allocation_id, allocation_entry.work_item_id)
            allocations[key] = allocations.get(key, Fraction()) + allocation_entry.hours
    return (
        tuple(
            ReservationHours(rule_id, reservations[rule_id])
            for rule_id in sorted(reservations, key=str)
        ),
        tuple(
            AllocationHours(allocation_id, work_item_id, allocations[(allocation_id, work_item_id)])
            for allocation_id, work_item_id in sorted(allocations, key=lambda key: str(key[0]))
        ),
    )


def _sum(days: tuple[DatedCapacityDay, ...], attribute: str) -> Fraction:
    return sum((getattr(day, attribute) for day in days), Fraction())


def _bucket(days: tuple[DatedCapacityDay, ...], gaps: tuple[CapacityGap, ...]) -> CapacityBucket:
    period = PlanningHorizon(days[0].day, days[-1].day)
    relevant = _relevant_gaps(gaps, period)
    reservations, allocations = _source_totals(days)
    planning = _sum(days, "planning_hours")
    allocated = _sum(days, "allocated_hours")
    remaining = _sum(days, "remaining_hours")
    return CapacityBucket(
        period,
        _sum(days, "nominal_hours"),
        _sum(days, "unavailable_hours"),
        _sum(days, "available_hours"),
        _sum(days, "reserved_hours"),
        planning,
        allocated,
        remaining,
        reservations,
        allocations,
        relevant,
        _state(
            capacity_known=True,
            planning=planning,
            allocated=allocated,
            remaining=remaining,
            gaps=relevant,
            overloaded=any(day.remaining_hours < 0 for day in days),
        ),
    )


def _groups(
    days: tuple[DatedCapacityDay, ...], scale: CapacityBucketScale
) -> tuple[tuple[DatedCapacityDay, ...], ...]:
    if scale == CapacityBucketScale.PERIOD:
        return (days,) if days else ()
    if scale == CapacityBucketScale.DAY:
        return tuple((day,) for day in days)
    grouped: list[list[DatedCapacityDay]] = []
    previous: tuple[int, int] | None = None
    for day in days:
        iso = day.day.isocalendar()
        key = (iso.year, iso.week)
        if key != previous:
            grouped.append([])
            previous = key
        grouped[-1].append(day)
    return tuple(tuple(group) for group in grouped)


def capacity_buckets(
    person: PersonDatedCapacity,
    scale: CapacityBucketScale,
    *,
    global_gaps: tuple[CapacityGap, ...] = (),
) -> tuple[CapacityBucket, ...]:
    """Aggregate exact R04 days without recalculating or rounding their hours."""
    gaps = (*global_gaps, *person.gaps)
    if not person.days:
        return (
            CapacityBucket(
                person.period,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                (),
                (),
                gaps,
                CapacityLoadState.UNKNOWN,
            ),
        )
    return tuple(_bucket(group, gaps) for group in _groups(person.days, scale))


def _unknown_person(
    person_id: UUID,
    period: PlanningHorizon,
    gaps: tuple[CapacityGap, ...],
) -> PersonCapacityBreakdown:
    bucket = CapacityBucket(
        period,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        (),
        (),
        gaps,
        CapacityLoadState.UNKNOWN,
    )
    return PersonCapacityBreakdown(
        person_id,
        None,
        period,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        Fraction(),
        gaps,
        CapacityLoadState.UNKNOWN,
        (bucket,),
    )


def calculate_capacity_breakdown(
    plan: ProgramPlan,
    period: PlanningHorizon,
    scale: CapacityBucketScale = CapacityBucketScale.WEEK,
) -> CapacityBreakdown:
    """Return roster-order totals and source-preserving buckets for People."""
    if not isinstance(scale, CapacityBucketScale):
        raise ValueError("Capacity scale must be day, week, or period.")
    capacity = calculate_dated_capacity(plan, period)
    by_person = {person.person_id: person for person in capacity.people}
    people = []
    for roster_person in plan.people:
        result = by_person.get(roster_person.id)
        if result is None:
            people.append(_unknown_person(roster_person.id, period, capacity.gaps))
            continue
        gaps = (*capacity.gaps, *result.gaps)
        if result.capacity_known:
            assert result.calendar_id is not None
            calendar = plan.work_calendar(result.calendar_id)
            availability = availability_capacity(
                calendar,
                period,
                roster_person.id,
                tuple(
                    event
                    for event in plan.availability_events
                    if event.person_id == roster_person.id
                ),
            )
            working_days = sum(day.nominal_hours > 0 for day in result.days)
            overlaps = len(availability.overlaps)
        else:
            working_days = None
            overlaps = None
        state = _state(
            capacity_known=result.capacity_known,
            planning=result.planning_hours,
            allocated=result.allocated_hours,
            remaining=result.remaining_hours,
            gaps=gaps,
            overloaded=any(day.remaining_hours < 0 for day in result.days),
        )
        people.append(
            PersonCapacityBreakdown(
                roster_person.id,
                result.calendar_id,
                period,
                result.nominal_hours,
                working_days,
                result.unavailable_hours,
                result.available_hours,
                overlaps,
                result.reserved_hours,
                result.planning_hours,
                result.allocated_hours,
                result.remaining_hours,
                result.unplaced_hours,
                gaps,
                state,
                capacity_buckets(result, scale, global_gaps=capacity.gaps),
            )
        )
    return CapacityBreakdown(period, scale, capacity, tuple(people))


def day_period(start: date) -> PlanningHorizon:
    return PlanningHorizon(start, start)


def week_period(start: date) -> PlanningHorizon:
    """Return seven inclusive dates without overflowing date.max."""
    end = date.max if start > date.max - timedelta(days=6) else start + timedelta(days=6)
    return PlanningHorizon(start, end)
