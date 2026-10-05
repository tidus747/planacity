"""Shared dated capacity across calendars, duties, and planned work."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import uuid4

from planacity.domain import (
    Allocation,
    AvailabilityEvent,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    ReservationRule,
    WorkCalendar,
    WorkItem,
    WorkItemType,
)
from planacity.planning.capacity import (
    MAX_CAPACITY_PERSON_DAYS,
    CapacityGapKind,
    calculate_dated_capacity,
)

MONDAY = date(2026, 1, 5)
WORK_WEEK = PlanningHorizon(MONDAY, date(2026, 1, 9))
FULL_WEEK = PlanningHorizon(MONDAY, date(2026, 1, 11))


def calendar(*hours: str) -> WorkCalendar:
    values = hours or ("8", "8", "8", "8", "8", "0", "0")
    return WorkCalendar(name="Engineering", weekday_hours=tuple(Decimal(value) for value in values))


def capacity_plan(
    *,
    plan_calendar: WorkCalendar | None = None,
    items: tuple[WorkItem, ...] = (),
    allocations: tuple[Allocation, ...] = (),
    availability: tuple[AvailabilityEvent, ...] = (),
    reservations: tuple[ReservationRule, ...] = (),
    horizon: PlanningHorizon = FULL_WEEK,
) -> ProgramPlan:
    person = Person(name="Alex")
    assigned = plan_calendar or calendar()
    translated_allocations = tuple(replace(entry, person_id=person.id) for entry in allocations)
    translated_availability = tuple(replace(event, person_id=person.id) for event in availability)
    translated_reservations = tuple(replace(rule, person_ids=(person.id,)) for rule in reservations)
    return ProgramPlan(
        name="Capacity example",
        horizon=horizon,
        people=(person,),
        work_items=items,
        work_calendars=(assigned,),
        person_calendars=(PersonCalendar(person_id=person.id, calendar_id=assigned.id),),
        availability_events=translated_availability,
        reservation_rules=translated_reservations,
        allocations=translated_allocations,
    )


def task(title: str, period: PlanningHorizon | None = WORK_WEEK) -> WorkItem:
    return WorkItem(
        title=title,
        kind=WorkItemType.TASK,
        start=period.start if period else None,
        end=period.end if period else None,
    )


def allocation(item: WorkItem, hours: str) -> Allocation:
    return Allocation(work_item_id=item.id, person_id=uuid4(), hours=Decimal(hours))


def reservation(hours: str = "4") -> ReservationRule:
    return ReservationRule(
        name="Meetings",
        person_ids=(uuid4(),),
        hours_per_person=Decimal(hours),
        anchor=MONDAY,
        interval_weeks=1,
        effective=FULL_WEEK,
    )


def absence(fraction: str) -> AvailabilityEvent:
    return AvailabilityEvent(
        person_id=uuid4(),
        period=PlanningHorizon(MONDAY, MONDAY),
        unavailable_fraction=Decimal(fraction),
    )


def test_calculation_reconciles_calendar_availability_reservations_and_work():
    work = task("Integration")
    duty = reservation()
    plan = capacity_plan(
        items=(work,),
        allocations=(allocation(work, "20"),),
        availability=(absence("0.5"), absence("1")),
        reservations=(duty,),
    )

    result = calculate_dated_capacity(plan, FULL_WEEK)
    person = result.people[0]

    assert result.complete
    assert person.nominal_hours == 40
    assert person.unavailable_hours == 8
    assert person.available_hours == 32
    assert person.reserved_hours == 4
    assert person.planning_hours == 28
    assert person.allocated_hours == 20
    assert person.remaining_hours == 8
    assert person.days[0].allocated_hours == 0
    assert person.days[1].reservations[0].rule_id == duty.id
    assert person.days[1].reserved_hours == 1
    assert person.days[1].allocated_hours == 5
    assert person.days[1].remaining_hours == 2
    assert person.reservation_breakdown[0].hours == 4
    assert person.allocation_breakdown[0].hours == 20


def test_allocation_uses_complete_window_before_clipping_query():
    work = task("Weighted work")
    plan = capacity_plan(
        plan_calendar=calendar("4", "8", "0", "4", "4", "0", "0"),
        items=(work,),
        allocations=(allocation(work, "10"),),
    )

    one_day = calculate_dated_capacity(plan, PlanningHorizon(date(2026, 1, 6), date(2026, 1, 6)))
    full = calculate_dated_capacity(plan, WORK_WEEK)

    assert one_day.people[0].allocated_hours == 4
    assert full.people[0].allocated_hours == 10
    assert one_day.people[0].allocation_breakdown[0].hours == 4


def test_reservation_uses_complete_anchored_period_before_clipping():
    duty = reservation("10")
    plan = capacity_plan(availability=(absence("1"),), reservations=(duty,))
    wednesday = PlanningHorizon(date(2026, 1, 7), date(2026, 1, 7))

    result = calculate_dated_capacity(plan, wednesday).people[0]

    assert result.reserved_hours == Fraction(5, 2)
    assert result.planning_hours == Fraction(11, 2)
    assert len(result.reservation_breakdown) == 1
    assert result.reservation_breakdown[0].rule_id == duty.id


def test_concurrent_allocations_add_and_keep_negative_remaining_capacity():
    first = task("First", PlanningHorizon(MONDAY, MONDAY))
    second = task("Second", PlanningHorizon(MONDAY, MONDAY))
    plan = capacity_plan(
        items=(first, second),
        allocations=(allocation(first, "6"), allocation(second, "7")),
    )

    day = calculate_dated_capacity(plan, PlanningHorizon(MONDAY, MONDAY)).people[0].days[0]

    assert day.allocated_hours == 13
    assert day.remaining_hours == -5
    assert {entry.allocation_id for entry in day.allocations} == {
        entry.id for entry in plan.allocations
    }


def test_non_overlapping_allocations_are_not_treated_as_concurrent():
    monday = task("Monday", PlanningHorizon(MONDAY, MONDAY))
    tuesday_day = date(2026, 1, 6)
    tuesday = task("Tuesday", PlanningHorizon(tuesday_day, tuesday_day))
    plan = capacity_plan(
        items=(monday, tuesday),
        allocations=(allocation(monday, "8"), allocation(tuesday, "8")),
    )

    result = calculate_dated_capacity(plan, PlanningHorizon(MONDAY, tuesday_day)).people[0]

    assert result.allocated_hours == 16
    assert [day.allocated_hours for day in result.days] == [8, 8]
    assert result.remaining_hours == 0


def test_each_person_uses_their_own_calendar_in_roster_order():
    alex = Person(name="Alex")
    sam = Person(name="Sam")
    full_time = calendar()
    part_time = calendar("4", "4", "4", "4", "4", "0", "0")
    work = task("Shared", PlanningHorizon(MONDAY, MONDAY))
    plan = ProgramPlan(
        name="Two calendars",
        horizon=FULL_WEEK,
        people=(sam, alex),
        work_items=(work,),
        work_calendars=(full_time, part_time),
        person_calendars=(
            PersonCalendar(person_id=alex.id, calendar_id=full_time.id),
            PersonCalendar(person_id=sam.id, calendar_id=part_time.id),
        ),
        allocations=(
            Allocation(work_item_id=work.id, person_id=alex.id, hours=Decimal(8)),
            Allocation(work_item_id=work.id, person_id=sam.id, hours=Decimal(4)),
        ),
    )

    result = calculate_dated_capacity(plan, PlanningHorizon(MONDAY, MONDAY))

    assert [person.person_id for person in result.people] == [sam.id, alex.id]
    assert [person.nominal_hours for person in result.people] == [4, 8]
    assert [person.remaining_hours for person in result.people] == [0, 0]


def test_overlapping_reservations_add_and_retain_negative_planning_capacity():
    meetings = reservation("30")
    support = replace(meetings, id=uuid4(), name="Support")
    plan = capacity_plan(reservations=(meetings, support))

    result = calculate_dated_capacity(plan, FULL_WEEK).people[0]

    assert result.complete
    assert result.reserved_hours == 60
    assert result.planning_hours == -20
    assert result.remaining_hours == -20
    assert {entry.rule_id: entry.hours for entry in result.reservation_breakdown} == {
        meetings.id: Fraction(30),
        support.id: Fraction(30),
    }


def test_missing_calendar_and_dates_remain_unknown_and_unplaced():
    dated = task("Dated")
    undated = task("Undated", None)
    plan = capacity_plan(
        items=(dated, undated),
        allocations=(allocation(dated, "10"), allocation(undated, "3")),
    )
    plan = replace(plan, person_calendars=())

    result = calculate_dated_capacity(plan, FULL_WEEK).people[0]

    assert not result.capacity_known and not result.complete
    assert result.nominal_hours is None
    assert result.remaining_hours is None
    assert result.unplaced_hours == 13
    assert {gap.kind for gap in result.gaps} == {
        CapacityGapKind.MISSING_CALENDAR,
        CapacityGapKind.MISSING_WORK_DATES,
    }


def test_undated_and_zero_capacity_allocations_are_explicit_gaps():
    undated = task("Undated", None)
    scheduled = task("Scheduled")
    plan = capacity_plan(
        plan_calendar=calendar("0", "0", "0", "0", "0", "0", "0"),
        items=(undated, scheduled),
        allocations=(allocation(undated, "3"), allocation(scheduled, "10")),
    )

    result = calculate_dated_capacity(plan, FULL_WEEK).people[0]

    assert result.capacity_known and not result.complete
    assert result.remaining_hours == 0
    assert result.allocated_hours == 0
    assert result.unplaced_hours == 13
    assert {gap.kind for gap in result.gaps} == {
        CapacityGapKind.MISSING_WORK_DATES,
        CapacityGapKind.NO_PLANNING_CAPACITY,
    }
    zero_capacity = next(
        gap for gap in result.gaps if gap.kind == CapacityGapKind.NO_PLANNING_CAPACITY
    )
    assert zero_capacity.period == WORK_WEEK


def test_reservation_without_eligible_days_retains_requested_hours():
    duty = reservation("6")
    plan = capacity_plan(
        plan_calendar=calendar("0", "0", "0", "0", "0", "0", "0"),
        reservations=(duty,),
    )

    result = calculate_dated_capacity(plan, FULL_WEEK).people[0]

    assert not result.complete
    assert result.reserved_hours == 0
    assert result.unplaced_hours == 6
    assert result.gaps[0].kind == CapacityGapKind.UNRESOLVED_RESERVATION
    assert result.gaps[0].source_id == duty.id


def test_work_outside_plan_horizon_uses_its_own_dates_when_queried():
    february = PlanningHorizon(date(2026, 2, 2), date(2026, 2, 6))
    work = task("Future work", february)
    plan = capacity_plan(
        items=(work,),
        allocations=(allocation(work, "15"),),
        horizon=FULL_WEEK,
    )

    result = calculate_dated_capacity(plan, february).people[0]

    assert result.allocated_hours == 15
    assert result.complete


def test_exact_conservation_determinism_and_no_input_mutation():
    first = task("First", PlanningHorizon(MONDAY, date(2026, 1, 7)))
    second = task("Second", PlanningHorizon(MONDAY, date(2026, 1, 7)))
    first_duty = reservation("1.00000000000000000000000000001")
    second_duty = replace(first_duty, id=uuid4(), name="Support", hours_per_person=Decimal("2"))
    plan = capacity_plan(
        plan_calendar=calendar("1", "2", "3", "0", "0", "0", "0"),
        items=(first, second),
        allocations=(
            allocation(first, "1.00000000000000000000000000001"),
            allocation(second, "2"),
        ),
        reservations=(first_duty, second_duty),
    )
    before = repr(plan)

    with localcontext() as context:
        context.prec = 2
        expected = calculate_dated_capacity(plan, PlanningHorizon(MONDAY, date(2026, 1, 7)))
        reordered = calculate_dated_capacity(
            replace(
                plan,
                allocations=tuple(reversed(plan.allocations)),
                reservation_rules=tuple(reversed(plan.reservation_rules)),
            ),
            PlanningHorizon(MONDAY, date(2026, 1, 7)),
        )
        assert expected == reordered
        assert expected.people[0].allocated_hours == Fraction(
            Decimal("3.00000000000000000000000000001")
        )
        assert context.prec == 2
    assert repr(plan) == before


def test_large_required_range_returns_incomplete_result_not_partial_totals():
    period = PlanningHorizon(date(2000, 1, 1), date(2300, 1, 1))
    long_running_rule = replace(reservation(), anchor=period.start, effective=period)
    plan = capacity_plan(horizon=period, reservations=(long_running_rule,))

    result = calculate_dated_capacity(plan, period)

    assert not result.complete
    assert result.people == ()
    assert result.gaps[0].kind == CapacityGapKind.QUERY_LIMIT
    assert f"{MAX_CAPACITY_PERSON_DAYS:,}" in result.gaps[0].message
