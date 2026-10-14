"""Elapsed-day critical-path analysis is deterministic and independent from Qt."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkItem,
    WorkItemType,
    WorkPriority,
)
from planacity.planning.critical_path import (
    CriticalPathDiagnosticKind,
    CriticalPathStatus,
    calculate_critical_path,
)


def work(title: str, start: date | None, end: date | None) -> WorkItem:
    return WorkItem(title=title, kind=WorkItemType.TASK, start=start, end=end)


def blocks(before: WorkItem, after: WorkItem) -> Relationship:
    return Relationship(
        source_id=before.id,
        target_id=after.id,
        kind=RelationshipType.BLOCKS,
    )


def make_plan(
    items: tuple[WorkItem, ...], relationships: tuple[Relationship, ...] = ()
) -> ProgramPlan:
    return ProgramPlan(
        name="Critical path",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        work_items=items,
        relationships=relationships,
    )


def fork_join_plan(*, tied: bool = False) -> tuple[ProgramPlan, tuple[WorkItem, ...]]:
    first = work("A", date(2026, 1, 1), date(2026, 1, 2))
    longer = work("B", date(2026, 1, 3), date(2026, 1, 5))
    shorter = work(
        "C",
        date(2026, 1, 3),
        date(2026, 1, 5) if tied else date(2026, 1, 3),
    )
    finish = work("D", date(2026, 1, 6), date(2026, 1, 7))
    items = (first, longer, shorter, finish)
    return (
        make_plan(
            items,
            (
                blocks(first, longer),
                blocks(first, shorter),
                blocks(longer, finish),
                blocks(shorter, finish),
            ),
        ),
        items,
    )


def test_chain_returns_elapsed_offsets_float_and_critical_ids():
    first = work("A", date(2026, 1, 1), date(2026, 1, 2))
    second = work("B", date(2026, 1, 3), date(2026, 1, 5))
    finish = work("D", date(2026, 1, 6), date(2026, 1, 7))
    relationships = (blocks(first, second), blocks(second, finish))
    plan = make_plan((first, second, finish), relationships)

    result = calculate_critical_path(plan)

    assert result.status == CriticalPathStatus.COMPLETE
    assert result.complete
    assert result.scope_ids == (first.id, second.id, finish.id)
    assert result.origin == date(2026, 1, 1)
    assert result.finish_offset == 7
    assert [activity.duration_days for activity in result.activities] == [2, 3, 2]
    assert [
        (
            activity.early_start,
            activity.early_finish,
            activity.late_start,
            activity.late_finish,
            activity.total_float,
        )
        for activity in result.activities
    ] == [(0, 2, 0, 2, 0), (2, 5, 2, 5, 0), (5, 7, 5, 7, 0)]
    assert result.critical_node_ids == result.scope_ids
    assert result.critical_relationship_ids == tuple(link.id for link in relationships)
    assert all(link.critical for link in result.links)
    assert plan.work_items == (first, second, finish)


def test_parallel_and_disconnected_shorter_work_receives_float():
    plan, (first, longer, shorter, finish) = fork_join_plan()
    disconnected = work("Disconnected", date(2025, 11, 1), date(2025, 11, 1))
    plan = replace(plan, work_items=(*plan.work_items, disconnected))

    result = calculate_critical_path(plan)

    assert result.finish_offset == 7
    assert result.activity(shorter.id).total_float == 2
    assert not result.activity(shorter.id).critical
    assert result.activity(disconnected.id).total_float == 6
    assert result.critical_node_ids == (first.id, longer.id, finish.id)
    assert result.scope_ids[-1] == disconnected.id
    assert result.origin == disconnected.start


def test_tied_longest_branches_return_all_critical_nodes_and_tight_edges():
    plan, items = fork_join_plan(tied=True)

    result = calculate_critical_path(plan)

    assert result.critical_node_ids == tuple(item.id for item in items)
    assert result.critical_relationship_ids == tuple(
        relationship.id for relationship in plan.relationships
    )
    assert all(activity.total_float == 0 for activity in result.activities)
    assert all(link.critical for link in result.links)


def test_one_day_leaf_epic_is_a_duration_one_activity():
    epic = WorkItem(
        title="Leaf Epic",
        kind=WorkItemType.EPIC,
        start=date(2026, 1, 10),
        end=date(2026, 1, 10),
    )

    result = calculate_critical_path(make_plan((epic,)))

    assert result.finish_offset == 1
    assert result.activity(epic.id).duration_days == 1
    assert result.activity(epic.id).critical


def test_duplicate_reversed_storage_is_one_link_with_all_relationship_ids():
    first = work("A", date(2026, 1, 1), date(2026, 1, 1))
    second = work("B", date(2026, 1, 2), date(2026, 1, 2))
    forward = blocks(first, second)
    reversed_storage = Relationship(
        source_id=second.id,
        target_id=first.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    related = Relationship(
        source_id=first.id,
        target_id=second.id,
        kind=RelationshipType.RELATED_TO,
    )
    plan = make_plan((first, second), (forward, related))
    # Older or externally assembled snapshots may contain equivalent stored edges
    # even though new domain edits reject them.
    object.__setattr__(plan, "relationships", (forward, reversed_storage, related))

    result = calculate_critical_path(plan)

    assert len(result.links) == 1
    assert result.links[0].relationship_ids == (forward.id, reversed_storage.id)
    assert result.critical_relationship_ids == (forward.id, reversed_storage.id)


def test_hierarchy_adds_no_edge_but_explicit_container_dependency_is_unsupported():
    parent = WorkItem(title="Parent", kind=WorkItemType.EPIC)
    child = WorkItem(
        title="Child",
        kind=WorkItemType.TASK,
        parent_id=parent.id,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
    )
    independent = calculate_critical_path(make_plan((parent, child)))
    assert independent.status == CriticalPathStatus.COMPLETE
    assert independent.scope_ids == (child.id,)
    assert independent.links == ()

    relationship = blocks(parent, child)
    unsupported = calculate_critical_path(make_plan((parent, child), (relationship,)))
    assert unsupported.status == CriticalPathStatus.UNSUPPORTED
    assert not unsupported.complete
    assert unsupported.finish_offset is None
    assert unsupported.diagnostics[0].kind == CriticalPathDiagnosticKind.CONTAINER_DEPENDENCY
    assert unsupported.diagnostics[0].relationship_ids == (relationship.id,)


def test_missing_dates_return_durations_but_no_partial_offsets():
    dated = work("Dated", date(2026, 1, 1), date(2026, 1, 2))
    partial = work("Partial", date(2026, 1, 3), None)
    plan = make_plan((dated, partial), (blocks(dated, partial),))

    result = calculate_critical_path(plan)

    assert result.status == CriticalPathStatus.INCOMPLETE
    assert [value.duration_days for value in result.activities] == [2, None]
    assert all(value.early_start is None for value in result.activities)
    assert result.critical_node_ids == ()
    assert {value.kind for value in result.diagnostics} == {
        CriticalPathDiagnosticKind.MISSING_DATES
    }


def test_cycles_and_date_conflicts_prevent_a_partial_result():
    first = work("A", date(2026, 1, 1), date(2026, 1, 2))
    second = work("B", date(2026, 1, 2), date(2026, 1, 3))
    plan = make_plan((first, second), (blocks(first, second), blocks(second, first)))

    result = calculate_critical_path(plan)

    assert result.status == CriticalPathStatus.INCOMPLETE
    assert result.finish_offset is None
    assert result.critical_node_ids == ()
    assert {value.kind for value in result.diagnostics} == {
        CriticalPathDiagnosticKind.CYCLE,
        CriticalPathDiagnosticKind.DATE_CONFLICT,
    }
    cycle = next(
        value for value in result.diagnostics if value.kind == CriticalPathDiagnosticKind.CYCLE
    )
    assert cycle.work_item_ids == (first.id, second.id)
    assert cycle.relationship_ids == tuple(link.id for link in plan.relationships)


def test_conflicting_dates_without_a_cycle_prevent_analysis():
    first = work("A", date(2026, 1, 1), date(2026, 1, 3))
    second = work("B", date(2026, 1, 3), date(2026, 1, 5))
    relationship = blocks(first, second)

    result = calculate_critical_path(make_plan((first, second), (relationship,)))

    assert result.status == CriticalPathStatus.INCOMPLETE
    assert result.finish_offset is None
    assert [value.kind for value in result.diagnostics] == [
        CriticalPathDiagnosticKind.DATE_CONFLICT
    ]
    assert "1 conflicting calendar day" in result.diagnostics[0].message
    assert result.diagnostics[0].relationship_ids == (relationship.id,)


def test_unknown_dependency_endpoint_is_reported_defensively():
    item = work("Known", date(2026, 1, 1), date(2026, 1, 1))
    plan = make_plan((item,))
    broken = Relationship(
        source_id=item.id,
        target_id=uuid4(),
        kind=RelationshipType.BLOCKS,
    )
    object.__setattr__(plan, "relationships", (broken,))

    result = calculate_critical_path(plan)

    assert result.status == CriticalPathStatus.UNSUPPORTED
    assert result.diagnostics[0].kind == CriticalPathDiagnosticKind.UNKNOWN_ENDPOINT
    assert result.diagnostics[0].work_item_ids == (item.id,)
    assert result.diagnostics[0].relationship_ids == (broken.id,)


def test_horizon_priority_and_relationship_storage_order_do_not_change_calculation():
    first = work("Outside before", date(2025, 1, 1), date(2025, 1, 2))
    second = work("Outside after", date(2027, 1, 1), date(2027, 1, 3))
    relationship = blocks(first, second)
    plan = make_plan((first, second), (relationship,))
    baseline = calculate_critical_path(plan)
    priority_plan = replace(
        plan,
        work_items=(replace(first, priority=WorkPriority.HIGHEST), second),
    )

    assert baseline.status == CriticalPathStatus.COMPLETE
    assert baseline.scope_ids == (first.id, second.id)
    assert baseline == calculate_critical_path(priority_plan)


def test_empty_plan_reports_no_analysis_instead_of_zero_days():
    result = calculate_critical_path(make_plan(()))

    assert result.status == CriticalPathStatus.EMPTY
    assert not result.complete
    assert result.scope_ids == result.activities == result.links == ()
    assert result.finish_offset is None
    assert result.diagnostics[0].kind == CriticalPathDiagnosticKind.NO_WORK
