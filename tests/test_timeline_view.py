"""Grouping and filtering never change the canonical plan."""

from datetime import date

from planacity.domain import PlanningHorizon, ProgramPlan, WorkGroup, WorkItem, WorkItemType
from planacity.planning.timeline import TimelineDateState, project_timeline
from planacity.planning.timeline_view import TimelineFilters, TimelineGrouping, arrange_timeline


def grouped_plan():
    epic = WorkItem(title="Integration", kind=WorkItemType.EPIC)
    task = WorkItem(
        title="Calibrate SENSOR",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        start=date(2026, 1, 2),
        end=date(2026, 1, 5),
    )
    sub = WorkItem(title="Verify sensor", kind=WorkItemType.SUBTASK, parent_id=task.id)
    standalone = WorkItem(title="Notes", kind=WorkItemType.TASK)
    groups = (
        WorkGroup(name="Hardware", epic_ids=(epic.id,)),
        WorkGroup(name="Delivery", epic_ids=(epic.id,)),
    )
    return ProgramPlan(
        name="Grouping",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 2, 28)),
        work_items=(standalone, task, epic, sub),
        work_groups=groups,
    )


def test_grouping_retains_canonical_order_and_explicit_fallback_sections():
    plan = grouped_plan()
    projection = project_timeline(plan)
    standalone, epic, task, sub = projection.rows
    assert arrange_timeline(projection) == projection
    by_epic = arrange_timeline(projection, TimelineGrouping.EPIC)
    assert [row.item_id for row in by_epic.rows] == [
        epic.item_id,
        task.item_id,
        sub.item_id,
        standalone.item_id,
    ]
    assert [row.section for row in by_epic.rows] == ["Integration"] * 3 + ["Standalone work"]
    by_group = arrange_timeline(projection, TimelineGrouping.WORKGROUP)
    assert [row.section for row in by_group.rows] == ["Hardware"] * 3 + ["Delivery"] * 3 + [
        "Ungrouped work"
    ]
    assert len({(row.item_id, row.section_id) for row in by_group.rows}) == 7
    assert len({row.item_id for row in by_group.rows}) == 4
    assert project_timeline(plan) == projection


def test_combined_filters_match_children_using_inherited_groups():
    projection = project_timeline(grouped_plan())
    result = arrange_timeline(
        projection,
        TimelineGrouping.EPIC,
        TimelineFilters(
            text="  sensor ",
            kind=WorkItemType.TASK,
            group_id=projection.groups[1].id,
            state=TimelineDateState.SCHEDULED,
        ),
    )
    assert [row.title for row in result.rows] == ["Calibrate SENSOR"]
    assert result.rows[0].section == "Integration"
    assert result.rows[0].depth == 1
    assert arrange_timeline(projection, filters=TimelineFilters(text="absent")).rows == ()
    assert arrange_timeline(projection, filters=TimelineFilters()).rows == projection.rows
