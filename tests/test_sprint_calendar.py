"""Graphical sprint calendar projection behavior."""

from dataclasses import replace
from datetime import date

from test_sprints import sprint_plan

from planacity.domain import PlanningHorizon, Sprint, WorkItem, WorkItemType
from planacity.planning.sprint_calendar import SprintCalendarState, project_sprint_calendar
from planacity.planning.sprints import assign_work_to_sprint


def test_projection_clips_lanes_and_keeps_explicit_assignment_states() -> None:
    plan, first, _, task, undated = sprint_plan()
    partial = Sprint(
        name="Early",
        period=PlanningHorizon(date(2026, 12, 28), date(2027, 1, 5)),
    )
    outside = Sprint(
        name="Later",
        period=PlanningHorizon(date(2027, 3, 1), date(2027, 3, 5)),
    )
    crossing = WorkItem(
        title="Crossing work",
        kind=WorkItemType.TASK,
        start=date(2027, 1, 8),
        end=date(2027, 1, 12),
    )
    unassigned = WorkItem(
        title="Not sprint work",
        kind=WorkItemType.TASK,
        start=date(2027, 1, 6),
        end=date(2027, 1, 7),
    )
    plan = replace(
        plan,
        work_items=(*plan.work_items, crossing, unassigned),
        sprints=(outside, first, partial),
    )
    plan = assign_work_to_sprint(plan, first.id, task.id)
    plan = assign_work_to_sprint(plan, first.id, undated.id)
    plan = assign_work_to_sprint(plan, first.id, crossing.id)

    result = project_sprint_calendar(plan)

    assert tuple(lane.name for lane in result.lanes) == ("Early", "Sprint 1", "Later")
    assert result.outside_count == 1
    assert tuple(lane.name for lane in result.visible_lanes) == ("Early", "Sprint 1")
    assert result.lanes[0].state == SprintCalendarState.PARTIAL
    assert (result.lanes[0].visible_start_day, result.lanes[0].visible_end_day) == (0, 1)
    assert result.lanes[2].state == SprintCalendarState.OUTSIDE
    assert result.lanes[2].visible_start_day is result.lanes[2].visible_end_day is None

    lane = result.lanes[1]
    assert lane.state == SprintCalendarState.INSIDE
    assert (lane.visible_start_day, lane.visible_end_day) == (0, 6)
    assert tuple(value.title for value in lane.work) == (
        task.title,
        crossing.title,
        undated.title,
    )
    assert (lane.work[0].visible_start_day, lane.work[0].visible_end_day) == (1, 5)
    assert lane.work[0].inside_sprint is True
    assert lane.work[1].inside_sprint is False
    assert lane.work[2].inside_sprint is None
    assert lane.work[2].visible_start_day is lane.work[2].visible_end_day is None
    assert unassigned.id not in {value.id for value in lane.work}


def test_projection_is_read_only_and_reuses_the_exact_sprint_load() -> None:
    plan, first, _, task, _ = sprint_plan()
    plan = replace(plan, sprints=(first,))
    plan = assign_work_to_sprint(plan, first.id, task.id)

    result = project_sprint_calendar(plan)

    assert result.horizon == plan.horizon
    assert result.total_days == 56
    assert result.lanes[0].load.sprint_id == first.id
    assert result.lanes[0].load.work_without_allocation_ids == (task.id,)
    assert plan.sprints == (first,)
    assert len(plan.sprint_assignments) == 1
