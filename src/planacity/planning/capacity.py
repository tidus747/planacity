"""Shared dated capacity calculation over canonical planning inputs."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.availability import availability_capacity
from planacity.planning.reservations import (
    CapacityDay,
    PersonCapacity,
    ReservationOccurrence,
    reservation_periods,
    reserve_capacity,
)

MAX_CAPACITY_PERSON_DAYS = 100_000


class CapacityGapKind(StrEnum):
    """Why a capacity result is incomplete without treating unknown as zero."""

    MISSING_CALENDAR = "missing_calendar"
    MISSING_WORK_DATES = "missing_work_dates"
    NO_PLANNING_CAPACITY = "no_planning_capacity"
    UNRESOLVED_RESERVATION = "unresolved_reservation"
    QUERY_LIMIT = "query_limit"


@dataclass(frozen=True)
class CapacityGap:
    kind: CapacityGapKind
    message: str
    person_id: UUID | None = None
    source_id: UUID | None = None
    work_item_id: UUID | None = None
    period: PlanningHorizon | None = None
    hours: Fraction | None = None


@dataclass(frozen=True)
class ReservationHours:
    rule_id: UUID
    hours: Fraction


@dataclass(frozen=True)
class AllocationHours:
    allocation_id: UUID
    work_item_id: UUID
    hours: Fraction


@dataclass(frozen=True)
class DatedCapacityDay:
    day: date
    nominal_hours: Fraction
    unavailable_hours: Fraction
    available_hours: Fraction
    reserved_hours: Fraction
    planning_hours: Fraction
    allocated_hours: Fraction
    remaining_hours: Fraction
    reservations: tuple[ReservationHours, ...]
    allocations: tuple[AllocationHours, ...]


def _sum_days(days: tuple[DatedCapacityDay, ...], attribute: str) -> Fraction:
    return sum((getattr(day, attribute) for day in days), Fraction())


@dataclass(frozen=True)
class PersonDatedCapacity:
    person_id: UUID
    calendar_id: UUID | None
    period: PlanningHorizon
    days: tuple[DatedCapacityDay, ...]
    gaps: tuple[CapacityGap, ...]

    @property
    def capacity_known(self) -> bool:
        return self.calendar_id is not None

    @property
    def complete(self) -> bool:
        return self.capacity_known and not self.gaps

    def _known_total(self, attribute: str) -> Fraction | None:
        return _sum_days(self.days, attribute) if self.capacity_known else None

    @property
    def nominal_hours(self) -> Fraction | None:
        return self._known_total("nominal_hours")

    @property
    def unavailable_hours(self) -> Fraction | None:
        return self._known_total("unavailable_hours")

    @property
    def available_hours(self) -> Fraction | None:
        return self._known_total("available_hours")

    @property
    def reserved_hours(self) -> Fraction | None:
        return self._known_total("reserved_hours")

    @property
    def planning_hours(self) -> Fraction | None:
        return self._known_total("planning_hours")

    @property
    def allocated_hours(self) -> Fraction | None:
        return self._known_total("allocated_hours")

    @property
    def remaining_hours(self) -> Fraction | None:
        return self._known_total("remaining_hours")

    @property
    def unplaced_hours(self) -> Fraction:
        return sum((gap.hours for gap in self.gaps if gap.hours is not None), Fraction())

    @property
    def reservation_breakdown(self) -> tuple[ReservationHours, ...]:
        totals: dict[UUID, Fraction] = {}
        for day in self.days:
            for entry in day.reservations:
                totals[entry.rule_id] = totals.get(entry.rule_id, Fraction()) + entry.hours
        return tuple(ReservationHours(key, totals[key]) for key in sorted(totals, key=str))

    @property
    def allocation_breakdown(self) -> tuple[AllocationHours, ...]:
        totals: dict[tuple[UUID, UUID], Fraction] = {}
        for day in self.days:
            for entry in day.allocations:
                key = (entry.allocation_id, entry.work_item_id)
                totals[key] = totals.get(key, Fraction()) + entry.hours
        return tuple(
            AllocationHours(allocation_id, work_item_id, totals[(allocation_id, work_item_id)])
            for allocation_id, work_item_id in sorted(totals, key=lambda key: str(key[0]))
        )


@dataclass(frozen=True)
class DatedCapacity:
    period: PlanningHorizon
    people: tuple[PersonDatedCapacity, ...]
    gaps: tuple[CapacityGap, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.gaps and all(person.complete for person in self.people)

    @property
    def all_gaps(self) -> tuple[CapacityGap, ...]:
        return (*self.gaps, *(gap for person in self.people for gap in person.gaps))


@dataclass(frozen=True)
class _BaseDay:
    nominal: Fraction
    unavailable: Fraction
    available: Fraction
    available_decimal: Decimal


def _ordinals(period: PlanningHorizon) -> range:
    return range(period.start.toordinal(), period.end.toordinal() + 1)


def _intersects(first: PlanningHorizon, second: PlanningHorizon) -> bool:
    return first.start <= second.end and second.start <= first.end


def _merge_periods(periods: list[PlanningHorizon]) -> tuple[PlanningHorizon, ...]:
    ordered = sorted(periods, key=lambda period: (period.start, period.end))
    merged: list[PlanningHorizon] = []
    for period in ordered:
        if not merged or period.start.toordinal() > merged[-1].end.toordinal() + 1:
            merged.append(period)
            continue
        merged[-1] = PlanningHorizon(merged[-1].start, max(merged[-1].end, period.end))
    return tuple(merged)


def _period_days(periods: tuple[PlanningHorizon, ...]) -> int:
    return sum((period.end - period.start).days + 1 for period in periods)


def _limit_result(period: PlanningHorizon, person_days: int) -> DatedCapacity:
    return DatedCapacity(
        period,
        (),
        (
            CapacityGap(
                CapacityGapKind.QUERY_LIMIT,
                f"Capacity calculation requires at least {person_days:,} person-days, above the "
                f"{MAX_CAPACITY_PERSON_DAYS:,} limit. Shorten the query or work date ranges.",
                period=period,
            ),
        ),
    )


def _target_periods(
    plan: ProgramPlan, person_id: UUID, period: PlanningHorizon
) -> tuple[PlanningHorizon, ...]:
    periods = [period]
    items = {item.id: item for item in plan.work_items}
    for allocation in plan.allocations:
        if allocation.person_id != person_id or allocation.hours == 0:
            continue
        item = items[allocation.work_item_id]
        if item.start is None or item.end is None:
            continue
        work_period = PlanningHorizon(item.start, item.end)
        if _intersects(work_period, period):
            periods.append(work_period)
    return _merge_periods(periods)


def _required_periods(
    plan: ProgramPlan, person_id: UUID, targets: tuple[PlanningHorizon, ...]
) -> tuple[PlanningHorizon, ...]:
    periods = list(targets)
    rules = tuple(rule for rule in plan.reservation_rules if person_id in rule.person_ids)
    for target in targets:
        for rule in rules:
            periods.extend(reservation_periods(rule, target))
    return _merge_periods(periods)


def _missing_calendar_result(
    plan: ProgramPlan, person_id: UUID, period: PlanningHorizon
) -> PersonDatedCapacity:
    person = plan.person(person_id)
    items = {item.id: item for item in plan.work_items}
    gaps = [
        CapacityGap(
            CapacityGapKind.MISSING_CALENDAR,
            f"Assign a work calendar to '{person.name}' before calculating capacity.",
            person_id=person_id,
            source_id=person_id,
            period=period,
        )
    ]
    for allocation in sorted(plan.allocations, key=lambda value: str(value.id)):
        if allocation.person_id != person_id or allocation.hours == 0:
            continue
        item = items[allocation.work_item_id]
        if item.start is None or item.end is None:
            gaps.append(
                CapacityGap(
                    CapacityGapKind.MISSING_WORK_DATES,
                    f"Set both dates for '{item.title}' before distributing its allocation.",
                    person_id=person_id,
                    source_id=allocation.id,
                    work_item_id=item.id,
                    hours=Fraction(allocation.hours),
                )
            )
            continue
        work_period = PlanningHorizon(item.start, item.end)
        if _intersects(work_period, period):
            gaps.append(
                CapacityGap(
                    CapacityGapKind.MISSING_CALENDAR,
                    f"'{item.title}' has allocated demand, but '{person.name}' has no calendar.",
                    person_id=person_id,
                    source_id=allocation.id,
                    work_item_id=item.id,
                    period=work_period,
                    hours=Fraction(allocation.hours),
                )
            )
    for rule in sorted(plan.reservation_rules, key=lambda value: str(value.id)):
        if person_id in rule.person_ids and _intersects(rule.effective, period):
            gaps.append(
                CapacityGap(
                    CapacityGapKind.UNRESOLVED_RESERVATION,
                    f"'{rule.name}' cannot be placed for '{person.name}' without a calendar.",
                    person_id=person_id,
                    source_id=rule.id,
                    period=period,
                )
            )
    return PersonDatedCapacity(person_id, None, period, (), tuple(gaps))


def _base_days(
    plan: ProgramPlan,
    person_id: UUID,
    calendar_id: UUID,
    required: tuple[PlanningHorizon, ...],
) -> dict[int, _BaseDay]:
    calendar = plan.work_calendar(calendar_id)
    events = tuple(event for event in plan.availability_events if event.person_id == person_id)
    result: dict[int, _BaseDay] = {}
    for required_period in required:
        for ordinal in _ordinals(required_period):
            day = date.fromordinal(ordinal)
            availability = availability_capacity(
                calendar, PlanningHorizon(day, day), person_id, events
            )
            nominal = Fraction(availability.nominal_hours)
            available = Fraction(availability.available_hours)
            result[ordinal] = _BaseDay(
                nominal,
                nominal - available,
                available,
                availability.available_hours,
            )
    return result


def _occurrence_share(occurrence: ReservationOccurrence) -> Fraction | None:
    if occurrence.reserved_hours is None:
        return None
    if occurrence.included_days == 0:
        return Fraction()
    return occurrence.reserved_hours / occurrence.included_days


def _reservation_load(
    plan: ProgramPlan,
    person_id: UUID,
    person_name: str,
    targets: tuple[PlanningHorizon, ...],
    base: dict[int, _BaseDay],
) -> tuple[dict[int, dict[UUID, Fraction]], tuple[CapacityGap, ...]]:
    rules = tuple(rule for rule in plan.reservation_rules if person_id in rule.person_ids)
    if not rules:
        return {}, ()
    inputs = PersonCapacity(
        person_id,
        tuple(
            CapacityDay(date.fromordinal(ordinal), base[ordinal].available_decimal)
            for ordinal in sorted(base)
        ),
    )
    by_day: dict[int, dict[UUID, Fraction]] = {}
    unresolved: dict[tuple[UUID, date, date], CapacityGap] = {}
    for target in targets:
        result = reserve_capacity(rules, target, (inputs,))[0]
        occurrences = result.occurrences
        for occurrence in occurrences:
            if occurrence.reserved_hours is None:
                rule = next(rule for rule in rules if rule.id == occurrence.rule_id)
                key = (rule.id, occurrence.period.start, occurrence.period.end)
                unresolved[key] = CapacityGap(
                    CapacityGapKind.UNRESOLVED_RESERVATION,
                    f"'{rule.name}' requests {rule.hours_per_person} h for '{person_name}', "
                    "but its complete period has no positive available-capacity day.",
                    person_id=person_id,
                    source_id=rule.id,
                    period=occurrence.period,
                    hours=Fraction(rule.hours_per_person),
                )
        shares = tuple(
            (occurrence.rule_id, occurrence.period, _occurrence_share(occurrence))
            for occurrence in occurrences
            if occurrence.reserved_hours is not None
        )
        for day in result.days:
            ordinal = day.day.toordinal()
            loads = by_day.setdefault(ordinal, {})
            for rule_id in day.rule_ids:
                share = next(
                    value
                    for candidate, occurrence_period, value in shares
                    if candidate == rule_id
                    and occurrence_period.start <= day.day <= occurrence_period.end
                )
                if share is not None:
                    loads[rule_id] = share
    return by_day, tuple(unresolved[key] for key in sorted(unresolved, key=str))


def _allocation_load(
    plan: ProgramPlan,
    person_id: UUID,
    person_name: str,
    period: PlanningHorizon,
    base: dict[int, _BaseDay],
    reservations: dict[int, dict[UUID, Fraction]],
) -> tuple[dict[int, dict[tuple[UUID, UUID], Fraction]], tuple[CapacityGap, ...]]:
    items = {item.id: item for item in plan.work_items}
    by_day: dict[int, dict[tuple[UUID, UUID], Fraction]] = {}
    gaps = []
    for allocation in sorted(plan.allocations, key=lambda value: str(value.id)):
        if allocation.person_id != person_id or allocation.hours == 0:
            continue
        item = items[allocation.work_item_id]
        if item.start is None or item.end is None:
            gaps.append(
                CapacityGap(
                    CapacityGapKind.MISSING_WORK_DATES,
                    f"Set both dates for '{item.title}' before distributing its allocation.",
                    person_id=person_id,
                    source_id=allocation.id,
                    work_item_id=item.id,
                    hours=Fraction(allocation.hours),
                )
            )
            continue
        work_period = PlanningHorizon(item.start, item.end)
        if not _intersects(work_period, period):
            continue
        weights = {
            ordinal: max(
                base[ordinal].available - sum(reservations.get(ordinal, {}).values(), Fraction()),
                Fraction(),
            )
            for ordinal in _ordinals(work_period)
        }
        total_weight = sum(weights.values(), Fraction())
        if total_weight == 0:
            gaps.append(
                CapacityGap(
                    CapacityGapKind.NO_PLANNING_CAPACITY,
                    f"'{item.title}' has {allocation.hours} h allocated to '{person_name}', "
                    "but its complete date window has no positive planning capacity.",
                    person_id=person_id,
                    source_id=allocation.id,
                    work_item_id=item.id,
                    period=work_period,
                    hours=Fraction(allocation.hours),
                )
            )
            continue
        demand = Fraction(allocation.hours)
        key = (allocation.id, item.id)
        for ordinal, weight in weights.items():
            if weight > 0:
                by_day.setdefault(ordinal, {})[key] = demand * weight / total_weight
    return by_day, tuple(gaps)


def calculate_dated_capacity(plan: ProgramPlan, period: PlanningHorizon) -> DatedCapacity:
    """Calculate exact dated capacity without changing plan data or moving work.

    Allocation weights use the complete WorkItem date window and each person's
    positive planning capacity after reservations. Results are then clipped to
    the requested period. Gaps keep missing or unplaceable demand visible.
    """
    if not isinstance(plan, ProgramPlan) or not isinstance(period, PlanningHorizon):
        raise ValueError("Supply a ProgramPlan and an inclusive planning period.")

    assignments = {
        assignment.person_id: assignment.calendar_id for assignment in plan.person_calendars
    }
    planned: dict[UUID, tuple[tuple[PlanningHorizon, ...], tuple[PlanningHorizon, ...]]] = {}
    person_days = 0
    for person in plan.people:
        if person.id not in assignments:
            continue
        targets = _target_periods(plan, person.id, period)
        target_days = _period_days(targets)
        if person_days + target_days > MAX_CAPACITY_PERSON_DAYS:
            return _limit_result(period, person_days + target_days)
        required = _required_periods(plan, person.id, targets)
        person_days += _period_days(required)
        if person_days > MAX_CAPACITY_PERSON_DAYS:
            return _limit_result(period, person_days)
        planned[person.id] = (targets, required)

    people = []
    for person in plan.people:
        calendar_id = assignments.get(person.id)
        if calendar_id is None:
            people.append(_missing_calendar_result(plan, person.id, period))
            continue
        targets, required = planned[person.id]
        base = _base_days(plan, person.id, calendar_id, required)
        reservations, reservation_gaps = _reservation_load(
            plan, person.id, person.name, targets, base
        )
        allocations, allocation_gaps = _allocation_load(
            plan, person.id, person.name, period, base, reservations
        )
        days = []
        for ordinal in _ordinals(period):
            source = base[ordinal]
            reservation_entries = tuple(
                ReservationHours(rule_id, hours)
                for rule_id, hours in sorted(
                    reservations.get(ordinal, {}).items(), key=lambda value: str(value[0])
                )
            )
            allocation_entries = tuple(
                AllocationHours(allocation_id, work_item_id, hours)
                for (allocation_id, work_item_id), hours in sorted(
                    allocations.get(ordinal, {}).items(), key=lambda value: str(value[0][0])
                )
            )
            reserved = sum((entry.hours for entry in reservation_entries), Fraction())
            allocated = sum((entry.hours for entry in allocation_entries), Fraction())
            planning = source.available - reserved
            days.append(
                DatedCapacityDay(
                    date.fromordinal(ordinal),
                    source.nominal,
                    source.unavailable,
                    source.available,
                    reserved,
                    planning,
                    allocated,
                    planning - allocated,
                    reservation_entries,
                    allocation_entries,
                )
            )
        people.append(
            PersonDatedCapacity(
                person.id,
                calendar_id,
                period,
                tuple(days),
                (*reservation_gaps, *allocation_gaps),
            )
        )
    return DatedCapacity(period, tuple(people))
