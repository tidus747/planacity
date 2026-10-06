"""People capacity buckets reconcile exactly with the shared dated engine."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

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
from planacity.planning.capacity_breakdown import (
    CapacityBucketScale,
    CapacityLoadState,
    calculate_capacity_breakdown,
    day_period,
    week_period,
)
from planacity.planning.findings import FindingRule, planning_findings
from planacity.planning.reservation_preview import preview_plan_reservations

MONDAY = date(2026, 10, 5)
WEEK = PlanningHorizon(MONDAY, date(2026, 10, 11))


def plan_with_capacity() -> ProgramPlan:
    alex, sam, robin = (Person(name=name) for name in ("Alex", "Sam", "Robin"))
    calendar = WorkCalendar(
        name="Engineering",
        weekday_hours=tuple(Decimal(value) for value in ("8", "8", "8", "8", "8", "0", "0")),
    )
    integration = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(20),
        start=WEEK.start,
        end=date(2026, 10, 9),
    )
    review = WorkItem(
        title="Review",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(8),
        start=MONDAY,
        end=MONDAY,
    )
    undated = WorkItem(
        title="Undated",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(3),
    )
    meeting = ReservationRule(
        name="Meeting",
        person_ids=(alex.id,),
        hours_per_person=Decimal(5),
        anchor=MONDAY,
        interval_weeks=1,
        effective=WEEK,
    )
    return ProgramPlan(
        name="Capacity breakdown",
        horizon=WEEK,
        people=(alex, sam, robin),
        work_items=(integration, review, undated),
        work_calendars=(calendar,),
        person_calendars=(
            PersonCalendar(person_id=alex.id, calendar_id=calendar.id),
            PersonCalendar(person_id=sam.id, calendar_id=calendar.id),
        ),
        reservation_rules=(meeting,),
        allocations=(
            Allocation(work_item_id=integration.id, person_id=alex.id, hours=Decimal(20)),
            Allocation(work_item_id=review.id, person_id=alex.id, hours=Decimal(8)),
            Allocation(work_item_id=undated.id, person_id=sam.id, hours=Decimal(3)),
        ),
    )


@pytest.mark.parametrize("scale", list(CapacityBucketScale))
def test_buckets_conserve_totals_and_source_ids(scale):
    plan = plan_with_capacity()
    result = calculate_capacity_breakdown(plan, WEEK, scale)
    alex = result.people[0]
    buckets = alex.buckets

    assert sum((bucket.nominal_hours for bucket in buckets), Fraction()) == alex.nominal_hours
    assert sum((bucket.unavailable_hours for bucket in buckets), Fraction()) == 0
    assert sum((bucket.reserved_hours for bucket in buckets), Fraction()) == 5
    assert sum((bucket.planning_hours for bucket in buckets), Fraction()) == 35
    assert sum((bucket.allocated_hours for bucket in buckets), Fraction()) == 28
    assert sum((bucket.remaining_hours for bucket in buckets), Fraction()) == 7
    assert {entry.rule_id for bucket in buckets for entry in bucket.reservations} == {
        plan.reservation_rules[0].id
    }
    assert {entry.allocation_id for bucket in buckets for entry in bucket.allocations} == {
        plan.allocations[0].id,
        plan.allocations[1].id,
    }
    assert result.capacity.people[0].remaining_hours == alex.remaining_hours


def test_day_heatmap_retains_concurrent_overload_and_exact_text_inputs():
    plan = plan_with_capacity()
    alex = calculate_capacity_breakdown(plan, WEEK, CapacityBucketScale.DAY).people[0]
    monday = alex.buckets[0]

    assert monday.period == PlanningHorizon(MONDAY, MONDAY)
    assert monday.planning_hours == 7
    assert monday.allocated_hours == 12
    assert monday.remaining_hours == -5
    assert monday.load_fraction == Fraction(12, 7)
    assert monday.state == CapacityLoadState.OVERLOADED
    assert len(monday.allocations) == 2
    assert alex.state == CapacityLoadState.OVERLOADED


def test_week_buckets_use_iso_boundaries_and_clip_to_selected_period():
    plan = plan_with_capacity()
    period = PlanningHorizon(date(2026, 10, 9), date(2026, 10, 13))
    result = calculate_capacity_breakdown(plan, period, CapacityBucketScale.WEEK)
    buckets = result.people[0].buckets

    assert tuple(bucket.period for bucket in buckets) == (
        PlanningHorizon(date(2026, 10, 9), date(2026, 10, 11)),
        PlanningHorizon(date(2026, 10, 12), date(2026, 10, 13)),
    )


def test_unknown_and_unplaced_demand_never_become_free_capacity():
    plan = plan_with_capacity()
    result = calculate_capacity_breakdown(plan, WEEK)
    sam = result.people[1]
    robin = result.people[2]

    assert sam.calendar_id is not None
    assert sam.unplaced_hours == 3
    assert sam.allocated_hours == 0
    assert sam.state == CapacityLoadState.INCOMPLETE
    assert sam.buckets[0].state == CapacityLoadState.INCOMPLETE
    assert robin.calendar_id is None
    assert robin.nominal_hours is None
    assert robin.remaining_hours is None
    assert robin.state == CapacityLoadState.UNKNOWN
    assert robin.buckets[0].state == CapacityLoadState.UNKNOWN


def test_zero_allocation_roster_member_remains_with_known_capacity():
    plan = plan_with_capacity()
    robin = plan.people[2]
    calendar = plan.work_calendars[0]
    plan = replace(
        plan,
        person_calendars=(
            *plan.person_calendars,
            PersonCalendar(person_id=robin.id, calendar_id=calendar.id),
        ),
    )

    result = calculate_capacity_breakdown(plan, WEEK)
    row = result.person(robin.id)

    assert len(result.people) == 3
    assert row.nominal_hours == 40
    assert row.allocated_hours == 0
    assert row.remaining_hours == 40
    assert row.state == CapacityLoadState.NO_WORK


def test_availability_and_range_shortcuts_are_explicit():
    plan = plan_with_capacity()
    alex = plan.people[0]
    absence = AvailabilityEvent(
        person_id=alex.id,
        period=PlanningHorizon(MONDAY, MONDAY),
        unavailable_fraction=Decimal("0.5"),
    )
    changed = calculate_capacity_breakdown(replace(plan, availability_events=(absence,)), WEEK)

    assert changed.people[0].unavailable_hours == 4
    assert changed.people[0].available_hours == 36
    assert day_period(MONDAY) == PlanningHorizon(MONDAY, MONDAY)
    assert week_period(MONDAY) == WEEK
    assert week_period(date.max) == PlanningHorizon(date.max, date.max)


def test_invalid_scale_is_rejected_without_changing_the_plan():
    plan = plan_with_capacity()
    before = repr(plan)

    with pytest.raises(ValueError, match="day, week, or period"):
        calculate_capacity_breakdown(plan, WEEK, "month")  # type: ignore[arg-type]

    assert repr(plan) == before


def test_people_reservations_and_findings_reconcile_to_one_snapshot():
    plan = plan_with_capacity()
    people = calculate_capacity_breakdown(plan, WEEK, CapacityBucketScale.DAY)
    preview = preview_plan_reservations(plan)
    overload = next(
        finding for finding in planning_findings(plan) if finding.rule_key == FindingRule.OVERLOAD
    )

    assert people.people[0].reserved_hours == preview[0].reserved_hours == 5
    assert people.people[0].buckets[0].remaining_hours == -5
    assert overload.person_ids == (plan.people[0].id,)
    assert overload.date_range == PlanningHorizon(MONDAY, MONDAY)


def test_shared_reservation_is_calculated_for_each_person():
    plan = plan_with_capacity()
    shared = replace(
        plan.reservation_rules[0],
        person_ids=(plan.people[0].id, plan.people[1].id),
    )
    result = calculate_capacity_breakdown(replace(plan, reservation_rules=(shared,)), WEEK)

    assert result.people[0].reserved_hours == 5
    assert result.people[1].reserved_hours == 5
