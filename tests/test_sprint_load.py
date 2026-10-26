"""Sprint load reconciles explicit membership with canonical dated capacity."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

from test_capacity_breakdown import WEEK, plan_with_capacity

from planacity.domain import (
    Allocation,
    ReservationCoverage,
    Sprint,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.sprints import (
    SprintLoadState,
    assign_work_to_sprint,
    calculate_sprint_load,
    calculate_sprint_loads,
)


def scoped_sprint_plan():
    plan = plan_with_capacity()
    group = WorkGroup(name="Alpha")
    integration = replace(plan.work_items[0], primary_group_id=group.id)
    sprint = Sprint(name="Sprint Alpha", period=WEEK, work_group_id=group.id)
    plan = replace(
        plan,
        work_items=(integration, *plan.work_items[1:]),
        work_groups=(group,),
        sprints=(sprint,),
        reservation_coverages=(
            ReservationCoverage(
                allocation_id=plan.allocations[0].id,
                reservation_rule_id=plan.reservation_rules[0].id,
            ),
        ),
    )
    return assign_work_to_sprint(plan, sprint.id, integration.id), sprint


def test_scoped_sprint_separates_covered_ordinary_and_competing_load() -> None:
    plan, sprint = scoped_sprint_plan()

    result = calculate_sprint_load(plan, sprint)

    assert result.person_ids == (plan.people[0].id,)
    assert result.known_people == 1
    assert result.planning_hours == 35
    assert result.sprint_hours == 20
    assert result.covered_hours == 5
    assert result.ordinary_hours == 15
    assert result.competing_hours == 8
    assert result.remaining_hours == 12
    assert result.unplaced_hours == 0
    assert result.allocation_ids == (plan.allocations[0].id,)
    assert result.state == SprintLoadState.OVERLOADED
    assert result.messages == ()


def test_whole_roster_keeps_known_subtotal_and_unknown_calendar_explicit() -> None:
    plan, scoped = scoped_sprint_plan()
    sprint = replace(scoped, work_group_id=None)
    plan = replace(plan, sprints=(sprint,))

    result = calculate_sprint_load(plan, sprint)

    assert result.person_ids == tuple(person.id for person in plan.people)
    assert result.known_people == 2
    assert result.planning_hours == 75
    assert result.remaining_hours == 52
    assert result.state == SprintLoadState.INCOMPLETE
    assert any("Missing work calendars: Robin" in message for message in result.messages)


def test_unplaced_and_owner_only_sprint_work_remain_visible() -> None:
    plan = plan_with_capacity()
    owner_only = WorkItem(title="Owner only", kind=WorkItemType.TASK, assignee_id=plan.people[0].id)
    sprint = Sprint(name="Sprint", period=WEEK)
    plan = replace(plan, work_items=(*plan.work_items, owner_only), sprints=(sprint,))
    plan = assign_work_to_sprint(plan, sprint.id, plan.work_items[2].id)
    plan = assign_work_to_sprint(plan, sprint.id, owner_only.id)

    result = calculate_sprint_load(plan, sprint)

    assert result.sprint_hours == 0
    assert result.unplaced_hours == 3
    assert result.work_without_allocation_ids == (owner_only.id,)
    assert result.state == SprintLoadState.INCOMPLETE
    assert any("1 assigned work item" in message for message in result.messages)
    assert any("3 h" in message and "could not be placed" in message for message in result.messages)


def test_empty_derived_scope_is_not_zero_free_capacity() -> None:
    plan = plan_with_capacity()
    unused = WorkGroup(name="Unused")
    sprint = Sprint(name="Empty scope", period=WEEK, work_group_id=unused.id)
    plan = replace(plan, work_groups=(unused,), sprints=(sprint,))

    result = calculate_sprint_load(plan, sprint)

    assert result.person_ids == ()
    assert result.known_people == 0
    assert result.planning_hours == Fraction()
    assert result.state == SprintLoadState.EMPTY_SCOPE
    assert "No people" in result.messages[0]


def test_assigned_person_outside_group_scope_is_explicit_and_order_is_stable() -> None:
    plan, sprint = scoped_sprint_plan()
    outside = WorkItem(
        title="Outside scope",
        kind=WorkItemType.TASK,
        start=WEEK.start,
        end=WEEK.end,
    )
    outside_allocation = Allocation(
        work_item_id=outside.id,
        person_id=plan.people[1].id,
        hours=Decimal(4),
    )
    later = Sprint(name="Later", period=replace(WEEK, start=WEEK.end, end=WEEK.end))
    plan = replace(
        plan,
        work_items=(*plan.work_items, outside),
        allocations=(*plan.allocations, outside_allocation),
        sprints=(later, sprint),
    )
    plan = assign_work_to_sprint(plan, sprint.id, outside.id)

    result = calculate_sprint_load(plan, sprint)

    assert result.outside_scope_person_ids == (plan.people[1].id,)
    assert result.state == SprintLoadState.INCOMPLETE
    assert any("outside the derived WorkGroup scope" in message for message in result.messages)
    assert tuple(value.sprint_id for value in calculate_sprint_loads(plan)) == (
        sprint.id,
        later.id,
    )


def test_query_limit_is_an_unknown_result_instead_of_partial_free_capacity() -> None:
    plan = plan_with_capacity()
    sprint = Sprint(name="Unsupported range", period=replace(WEEK, start=date.min, end=date.max))
    plan = replace(plan, sprints=(sprint,))

    result = calculate_sprint_load(plan, sprint)

    assert result.known_people == 0
    assert result.planning_hours == 0
    assert result.state == SprintLoadState.UNKNOWN
    assert any("100,000" in message for message in result.messages)
    assert not any("Missing work calendars" in message for message in result.messages)
