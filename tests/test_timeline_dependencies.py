"""Dependency semantics and geometry do not depend on Qt or screenshots."""

from dataclasses import replace
from datetime import date

import pytest

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkItem,
    WorkItemType,
)
from planacity.planning.timeline import project_timeline
from planacity.planning.timeline_dependencies import connector_points, timeline_dependencies
from planacity.planning.timeline_view import TimelineFilters, arrange_timeline


def dependency_plan():
    first = WorkItem(
        title="Build", kind=WorkItemType.TASK, start=date(2026, 1, 2), end=date(2026, 1, 4)
    )
    second = WorkItem(
        title="Verify", kind=WorkItemType.TASK, start=date(2026, 1, 7), end=date(2026, 1, 9)
    )
    link = Relationship(source_id=second.id, target_id=first.id, kind=RelationshipType.DEPENDS_ON)
    return ProgramPlan(
        name="Dependencies",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 2, 28)),
        work_items=(first, second),
        relationships=(link,),
    )


def test_directions_related_links_and_immutable_dates():
    plan = dependency_plan()
    first, second = plan.work_items
    for kind, source, target in (
        (RelationshipType.DEPENDS_ON, second.id, first.id),
        (RelationshipType.BLOCKS, first.id, second.id),
    ):
        changed = replace(
            plan, relationships=(Relationship(source_id=source, target_id=target, kind=kind),)
        )
        (link,) = timeline_dependencies(changed, project_timeline(changed))
        assert (link.predecessor, link.successor, link.reason) == (first.id, second.id, "")
        assert "Build -> Verify" in link.description
        assert kind.value in link.description
        assert changed.work_items is plan.work_items
    related = replace(
        plan, relationships=(replace(plan.relationships[0], kind=RelationshipType.RELATED_TO),)
    )
    assert timeline_dependencies(related, project_timeline(related)) == ()


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("filtered", "hidden by filters"),
        ("partial", "not fully scheduled"),
        ("outside", "outside planning horizon"),
        ("cycle", "cycle"),
    ],
)
def test_unavailable_or_cyclic_endpoints_explain_why_no_arrow(mode, reason):
    plan = dependency_plan()
    if mode == "partial":
        plan = replace(plan, work_items=(replace(plan.work_items[0], end=None), plan.work_items[1]))
    if mode == "outside":
        plan = replace(
            plan,
            work_items=(replace(plan.work_items[0], start=date(2025, 12, 30)), plan.work_items[1]),
        )
    if mode == "cycle":
        plan = replace(
            plan,
            relationships=plan.relationships
            + (
                Relationship(
                    source_id=plan.work_items[0].id,
                    target_id=plan.work_items[1].id,
                    kind=RelationshipType.DEPENDS_ON,
                ),
            ),
        )
    projection = project_timeline(plan)
    if mode == "filtered":
        projection = arrange_timeline(projection, filters=TimelineFilters(text="Verify"))
    links = timeline_dependencies(plan, projection)
    assert all(reason in link.reason for link in links)


@pytest.mark.parametrize(
    "start,end", [((20, 18), (100, 54)), ((100, 54), (20, 18)), ((20, 18), (20, 54))]
)
def test_connector_geometry_always_points_into_successor_start(start, end):
    points = connector_points(start, end)
    assert points[0] == start and points[-1] == end
    assert points[-2][0] < end[0] and points[-2][1] == end[1]
    assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:], strict=False))


def test_overlapping_dates_are_shown_without_rescheduling():
    plan = dependency_plan()
    plan = replace(
        plan, work_items=(plan.work_items[0], replace(plan.work_items[1], start=date(2026, 1, 3)))
    )
    (link,) = timeline_dependencies(plan, project_timeline(plan))
    assert not link.reason
    assert "overlap" in link.description
    assert plan.work_items[1].start == date(2026, 1, 3)
