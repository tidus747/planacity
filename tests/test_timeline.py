"""Timeline projection remains deterministic and independent from Qt."""

from datetime import date
from decimal import Decimal
from fractions import Fraction
from uuid import uuid4

from planacity.domain import (
    Allocation,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    WorkCalendar,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.timeline import (
    TimelineDateState,
    project_timeline,
    timeline_team_coverage,
)
from planacity.planning.work_context import TopicState


def team_coverage_plan() -> ProgramPlan:
    alice, bob, cara = (Person(name=name) for name in ("Alice", "Bob", "Cara"))
    calendar = WorkCalendar(name="Standard", weekday_hours=(Decimal(8),) * 5 + (Decimal(0),) * 2)
    first = WorkItem(
        title="Visible first",
        kind=WorkItemType.TASK,
        start=date(2026, 1, 5),
        end=date(2026, 1, 6),
    )
    second = WorkItem(
        title="Visible second",
        kind=WorkItemType.TASK,
        start=date(2026, 1, 7),
        end=date(2026, 1, 8),
    )
    undated = WorkItem(title="Hidden undated", kind=WorkItemType.TASK)
    return ProgramPlan(
        name="Coverage",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 9)),
        people=(alice, bob, cara),
        work_items=(first, second, undated),
        work_calendars=(calendar,),
        person_calendars=tuple(
            PersonCalendar(person_id=person.id, calendar_id=calendar.id)
            for person in (alice, bob, cara)
        ),
        allocations=(
            Allocation(work_item_id=first.id, person_id=alice.id, hours=Decimal(4)),
            Allocation(work_item_id=second.id, person_id=alice.id, hours=Decimal(2)),
            Allocation(work_item_id=second.id, person_id=bob.id, hours=Decimal(0)),
            Allocation(work_item_id=undated.id, person_id=cara.id, hours=Decimal(3)),
        ),
    )


def test_projection_preserves_hierarchy_order_identity_and_effective_groups() -> None:
    epic = WorkItem(title="Integration", kind=WorkItemType.EPIC)
    first = WorkItem(title="First task", kind=WorkItemType.TASK, parent_id=epic.id)
    second = WorkItem(title="Second task", kind=WorkItemType.TASK, parent_id=epic.id)
    subtask = WorkItem(title="Check wiring", kind=WorkItemType.SUBTASK, parent_id=first.id)
    standalone = WorkItem(title="Release notes", kind=WorkItemType.TASK)
    primary = WorkGroup(name="Primary", epic_ids=(epic.id,))
    secondary = WorkGroup(name="Secondary", epic_ids=(epic.id,))
    plan = ProgramPlan(
        name="Aurora",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        # Physical order need not put parents before children. Sibling order still
        # follows each sibling's position in this canonical tuple.
        work_items=(first, standalone, epic, subtask, second),
        work_groups=(primary, secondary),
    )

    projection = project_timeline(plan)

    assert [(row.item_id, row.depth) for row in projection.rows] == [
        (standalone.id, 0),
        (epic.id, 0),
        (first.id, 1),
        (subtask.id, 2),
        (second.id, 1),
    ]
    assert (projection.rows[2].title, projection.rows[2].kind, projection.rows[2].parent_id) == (
        "First task",
        WorkItemType.TASK,
        epic.id,
    )
    assert projection.rows[0].group_ids == ()
    assert all(row.group_ids == (primary.id, secondary.id) for row in projection.rows[1:])
    assert projection.rows[0].topic_state == TopicState.UNGROUPED
    assert projection.rows[0].primary_group_id is None
    assert all(row.topic_state == TopicState.AMBIGUOUS for row in projection.rows[1:])
    assert all(row.primary_group_id is None for row in projection.rows[1:])
    assert [(group.id, group.name) for group in projection.groups] == [
        (primary.id, "Primary"),
        (secondary.id, "Secondary"),
    ]


def test_projection_reports_inclusive_coordinates_and_date_states() -> None:
    items = (
        WorkItem(
            title="Same day",
            kind=WorkItemType.TASK,
            start=date(2026, 1, 1),
            end=date(2026, 1, 1),
        ),
        WorkItem(
            title="Cross horizon",
            kind=WorkItemType.TASK,
            start=date(2025, 12, 30),
            end=date(2026, 1, 3),
        ),
        WorkItem(title="Start known", kind=WorkItemType.TASK, start=date(2026, 1, 2)),
        WorkItem(title="End known", kind=WorkItemType.TASK, end=date(2025, 12, 30)),
        WorkItem(title="Unscheduled", kind=WorkItemType.TASK),
    )
    plan = ProgramPlan(
        name="New year",
        horizon=PlanningHorizon(date(2025, 12, 31), date(2026, 1, 2)),
        work_items=items,
    )

    projection = project_timeline(plan)

    assert projection.total_days == 3
    same_day, crossing, start_only, end_only, unscheduled = projection.rows
    assert (same_day.start_day, same_day.end_day, same_day.duration_days) == (1, 1, 1)
    assert same_day.date_state == TimelineDateState.SCHEDULED
    assert not same_day.outside_horizon
    assert (crossing.start_day, crossing.end_day, crossing.duration_days) == (-1, 3, 5)
    assert crossing.outside_horizon
    assert (start_only.start_day, start_only.end_day, start_only.duration_days) == (2, None, None)
    assert start_only.date_state == TimelineDateState.START_ONLY
    assert (end_only.start_day, end_only.end_day, end_only.duration_days) == (None, -1, None)
    assert end_only.date_state == TimelineDateState.END_ONLY
    assert end_only.outside_horizon
    assert unscheduled.date_state == TimelineDateState.UNSCHEDULED
    assert (unscheduled.start_day, unscheduled.end_day, unscheduled.duration_days) == (
        None,
        None,
        None,
    )


def test_projection_handles_empty_same_day_plan_without_mutating_it() -> None:
    plan = ProgramPlan(
        id=uuid4(),
        name="One day",
        horizon=PlanningHorizon(date(2026, 5, 4), date(2026, 5, 4)),
    )

    projection = project_timeline(plan)

    assert projection.horizon is plan.horizon
    assert projection.total_days == 1
    assert projection.rows == projection.groups == ()
    assert plan.work_items == plan.work_groups == ()


def test_team_coverage_counts_people_once_and_keeps_unplaced_demand_explicit() -> None:
    plan = team_coverage_plan()
    first, second, _ = plan.work_items

    result = timeline_team_coverage(plan, frozenset((first.id, second.id)))

    assert (result.visible_people, result.whole_plan_people, result.roster_people) == (1, 2, 3)
    assert result.unplaced_hours == Fraction(3)
    assert result.input_gaps == 1
    assert timeline_team_coverage(plan, frozenset()).visible_people == 0


def test_empty_timeline_team_coverage_is_explicit_and_complete() -> None:
    plan = ProgramPlan(
        name="Empty",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 9)),
    )

    result = timeline_team_coverage(plan, frozenset())

    assert (result.visible_people, result.whole_plan_people, result.roster_people) == (0, 0, 0)
    assert result.unplaced_hours == 0
    assert result.input_gaps == 0
