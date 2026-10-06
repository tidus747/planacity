"""Compact Overview projections reconcile with canonical planning services."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

from test_capacity_breakdown import MONDAY, WEEK, plan_with_capacity

from planacity.domain import (
    Allocation,
    AvailabilityEvent,
    ProgramPlan,
    ReservationRule,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.capacity_breakdown import CapacityLoadState
from planacity.planning.overview_analysis import calculate_overview_analysis


def test_overview_capacity_reconciles_known_subtotals_and_unplaced_demand() -> None:
    plan = plan_with_capacity()

    result = calculate_overview_analysis(plan)

    assert result.period == WEEK
    assert tuple(person.person_id for person in result.people) == tuple(
        person.id for person in plan.people
    )
    assert tuple(person.state for person in result.people) == (
        CapacityLoadState.OVERLOADED,
        CapacityLoadState.INCOMPLETE,
        CapacityLoadState.UNKNOWN,
    )
    assert result.capacity.known_people == 2
    assert result.capacity.total_people == 3
    assert result.capacity.nominal_hours == 80
    assert result.capacity.unavailable_hours == 0
    assert result.capacity.reserved_hours == 5
    assert result.capacity.planning_hours == 75
    assert result.capacity.scheduled_hours == 28
    assert result.capacity.remaining_hours == 47
    assert result.capacity.unplaced_hours == 3
    assert result.capacity.partial
    assert tuple((entry.name, entry.hours) for entry in result.capacity.reservations) == (
        ("Meeting", Fraction(5)),
    )
    assert any("known-person subtotals" in message for message in result.coverage)
    assert any("3 h" in message and "could not be placed" in message for message in result.coverage)


def test_topic_projection_has_one_additive_bucket_for_each_hour() -> None:
    plan = plan_with_capacity()
    integration, review, undated = plan.work_items
    alpha = WorkGroup(name="Alpha")
    beta = WorkGroup(name="Beta")
    plan = replace(
        plan,
        work_items=(
            replace(integration, primary_group_id=alpha.id),
            replace(review, primary_group_id=beta.id),
            undated,
        ),
        work_groups=(alpha, beta),
    )

    topics = calculate_overview_analysis(plan).topics

    assert tuple(topic.label for topic in topics) == ("Alpha", "Beta", "Ungrouped")
    assert tuple(topic.scheduled_hours for topic in topics) == (20, 8, 0)
    assert tuple(topic.unplaced_hours for topic in topics) == (0, 0, 3)
    assert tuple(topic.estimated_leaf_hours for topic in topics) == (20, 8, 3)
    assert sum((topic.scheduled_hours for topic in topics), Fraction()) == 28
    assert sum((topic.unplaced_hours for topic in topics), Fraction()) == 3
    assert sum((topic.estimated_leaf_hours for topic in topics), Fraction()) == 31


def test_breakdown_keeps_unavailability_and_named_reservations_separate() -> None:
    plan = plan_with_capacity()
    absence = AvailabilityEvent(
        person_id=plan.people[0].id,
        period=plan.horizon,
        unavailable_fraction=Decimal("0.1"),
    )
    front_office = ReservationRule(
        name="Front office",
        person_ids=(plan.people[1].id,),
        hours_per_person=Decimal(4),
        anchor=MONDAY,
        interval_weeks=1,
        effective=WEEK,
    )
    changed = replace(
        plan,
        availability_events=(absence,),
        reservation_rules=(*plan.reservation_rules, front_office),
    )

    capacity = calculate_overview_analysis(changed).capacity

    assert capacity.nominal_hours == 80
    assert capacity.unavailable_hours == 4
    assert capacity.available_hours == 76
    assert tuple((entry.name, entry.hours) for entry in capacity.reservations) == (
        ("Meeting", Fraction(5)),
        ("Front office", Fraction(4)),
    )
    assert capacity.reserved_hours == 9
    assert capacity.planning_hours == 67
    assert capacity.scheduled_hours == 28
    assert capacity.remaining_hours == 39


def test_estimated_topics_use_leaves_and_keep_ambiguous_and_unknown_explicit() -> None:
    epic = WorkItem(title="Program", kind=WorkItemType.EPIC, estimate_hours=Decimal(999))
    known = WorkItem(
        title="Known",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        estimate_hours=Decimal(6),
    )
    unknown = WorkItem(
        title="Unknown",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
    )
    standalone = WorkItem(
        title="Standalone",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(4),
    )
    alpha = WorkGroup(name="Alpha", epic_ids=(epic.id,))
    beta = WorkGroup(name="Beta", epic_ids=(epic.id,))
    plan = ProgramPlan(
        name="Topics",
        horizon=WEEK,
        work_items=(epic, known, unknown, standalone),
        work_groups=(alpha, beta),
    )

    result = calculate_overview_analysis(plan)
    ungrouped, ambiguous = result.topics

    assert ungrouped.label == "Ungrouped"
    assert ungrouped.estimated_leaf_hours == 4
    assert ambiguous.label == "Ambiguous group"
    assert ambiguous.estimated_leaf_hours == 6
    assert ambiguous.missing_estimate_count == 1
    assert sum((topic.estimated_leaf_hours for topic in result.topics), Fraction()) == 10
    assert all(topic.estimated_leaf_hours != 999 for topic in result.topics)
    assert any("1 leaf work item" in message for message in result.coverage)


def test_outside_horizon_allocations_do_not_become_scheduled_hours() -> None:
    plan = plan_with_capacity()
    alex = plan.people[0]
    outside = WorkItem(
        title="Outside",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(5),
        start=date(2026, 11, 2),
        end=date(2026, 11, 6),
    )
    changed = replace(
        plan,
        work_items=(*plan.work_items, outside),
        allocations=(
            *plan.allocations,
            Allocation(work_item_id=outside.id, person_id=alex.id, hours=Decimal(5)),
        ),
    )

    result = calculate_overview_analysis(changed)

    assert result.capacity.scheduled_hours == 28
    assert sum((topic.estimated_leaf_hours for topic in result.topics), Fraction()) == 36
    assert any("outside the plan horizon" in message for message in result.coverage)


def test_empty_plan_is_complete_empty_data_not_unknown_capacity() -> None:
    plan = ProgramPlan(name="Empty", horizon=WEEK)

    result = calculate_overview_analysis(plan)

    assert result.people == ()
    assert result.topics == ()
    assert result.capacity.known_people == result.capacity.total_people == 0
    assert result.capacity.nominal_hours == 0
    assert result.capacity.planning_hours == 0
    assert result.capacity.scheduled_hours == 0
    assert result.capacity.remaining_hours == 0
    assert any("No people" in message for message in result.coverage)


def test_zero_capacity_keeps_demand_visible_instead_of_marking_it_scheduled() -> None:
    plan = plan_with_capacity()
    zero_calendar = replace(
        plan.work_calendars[0],
        weekday_hours=tuple(Decimal(0) for _ in range(7)),
    )
    changed = replace(plan, work_calendars=(zero_calendar,))

    result = calculate_overview_analysis(changed)
    alex = result.people[0]

    assert alex.planning_hours == 0
    assert alex.scheduled_hours == 0
    assert alex.remaining_hours == 0
    assert alex.unplaced_hours == 33
    assert alex.state == CapacityLoadState.INCOMPLETE
    assert result.capacity.unplaced_hours == 36
    assert any(
        "36 h" in message and "could not be placed" in message for message in result.coverage
    )
