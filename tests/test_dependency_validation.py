"""Dependency rules are shared, directional, repairable, and independent from Qt."""

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
from planacity.planning.dependency_validation import (
    DependencyFindingKind,
    dependency_conflict_days,
    dependency_cycle_relationship_ids,
    dependency_edges,
    dependency_findings,
    normalize_dependency,
)
from planacity.planning.structure import add_relationship
from planacity.planning.work_items import set_work_dates


def dependency_plan() -> ProgramPlan:
    build = WorkItem(
        title="Build", kind=WorkItemType.TASK, start=date(2026, 1, 1), end=date(2026, 1, 4)
    )
    verify = WorkItem(
        title="Verify", kind=WorkItemType.TASK, start=date(2026, 1, 7), end=date(2026, 1, 9)
    )
    link = Relationship(
        source_id=verify.id,
        target_id=build.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    return ProgramPlan(
        name="Dependency plan",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 2, 28)),
        work_items=(build, verify),
        relationships=(link,),
    )


def test_depends_on_and_blocks_normalize_to_the_same_direction() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    depends = plan.relationships[0]
    blocks = Relationship(
        source_id=build.id,
        target_id=verify.id,
        kind=RelationshipType.BLOCKS,
    )

    depends_edge = normalize_dependency(depends)
    blocks_edge = normalize_dependency(blocks)
    assert depends_edge is not None and blocks_edge is not None
    assert (depends_edge.predecessor_id, depends_edge.successor_id) == (build.id, verify.id)
    assert (blocks_edge.predecessor_id, blocks_edge.successor_id) == (build.id, verify.id)
    assert normalize_dependency(replace(depends, kind=RelationshipType.RELATED_TO)) is None


def test_equal_dates_conflict_and_partial_dates_remain_unevaluated() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    equal = replace(plan, work_items=(build, replace(verify, start=build.end)))
    (edge,) = dependency_edges(equal)
    assert dependency_conflict_days(equal, edge) == 1
    (conflict,) = dependency_findings(equal)
    assert conflict.kind == DependencyFindingKind.CONFLICT
    assert conflict.conflict_days == 1
    assert '"Build" must end on or before 2026-01-03' in conflict.message
    assert '"Verify" must start on or after 2026-01-05' in conflict.message

    partial = replace(plan, work_items=(replace(build, end=None), verify))
    (finding,) = dependency_findings(partial)
    assert finding.kind == DependencyFindingKind.UNEVALUATED
    assert '"Build" end' in finding.message


def test_date_edits_reject_new_conflicts_with_actionable_boundaries() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items

    with pytest.raises(ValueError) as predecessor_error:
        set_work_dates(plan, build.id, start=build.start, end=verify.start)
    assert '"Build" ends 2026-01-07' in str(predecessor_error.value)
    assert "end on or before 2026-01-06" in str(predecessor_error.value)

    with pytest.raises(ValueError) as successor_error:
        set_work_dates(plan, verify.id, start=build.end, end=verify.end)
    assert '"Verify" starts 2026-01-04' in str(successor_error.value)
    assert "start on or after 2026-01-05" in str(successor_error.value)
    assert plan.work_items == (build, verify)


def test_all_prerequisites_are_checked_for_one_successor() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    design = WorkItem(
        title="Design", kind=WorkItemType.TASK, start=date(2026, 1, 1), end=date(2026, 1, 6)
    )
    second_link = Relationship(
        source_id=design.id,
        target_id=verify.id,
        kind=RelationshipType.BLOCKS,
    )
    plan = replace(
        plan,
        work_items=(build, design, verify),
        relationships=(*plan.relationships, second_link),
    )

    with pytest.raises(ValueError) as error:
        set_work_dates(plan, verify.id, start=date(2026, 1, 4), end=verify.end)
    assert '"Build" ends' in str(error.value)
    assert '"Design" ends' in str(error.value)
    assert "start on or after 2026-01-07" in str(error.value)


def test_legacy_conflicts_can_be_preserved_reduced_or_made_unevaluated() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    legacy = replace(plan, work_items=(replace(build, end=date(2026, 1, 8)), verify))
    original_days = dependency_findings(legacy)[0].conflict_days

    preserved = set_work_dates(legacy, build.id, start=date(2026, 1, 2), end=date(2026, 1, 8))
    reduced = set_work_dates(legacy, build.id, start=build.start, end=date(2026, 1, 7))
    unevaluated = set_work_dates(legacy, build.id, start=build.start, end=None)

    assert dependency_findings(preserved)[0].conflict_days == original_days
    assert dependency_findings(reduced)[0].conflict_days < original_days
    assert dependency_findings(unevaluated)[0].kind == DependencyFindingKind.UNEVALUATED


def test_unrelated_existing_conflict_does_not_block_another_date_repair() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    note = WorkItem(title="Release notes", kind=WorkItemType.TASK)
    legacy = replace(
        plan,
        work_items=(replace(build, end=date(2026, 1, 8)), verify, note),
    )

    changed = set_work_dates(
        legacy,
        note.id,
        start=date(2026, 1, 10),
        end=date(2026, 1, 11),
    )
    assert changed.work_item(note.id).start == date(2026, 1, 10)
    assert dependency_findings(changed)[0].kind == DependencyFindingKind.CONFLICT


def test_relationship_addition_rejects_conflicts_and_new_cycles() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    without_links = replace(
        plan,
        work_items=(build, replace(verify, start=build.end)),
        relationships=(),
    )
    conflict = Relationship(
        source_id=build.id,
        target_id=verify.id,
        kind=RelationshipType.BLOCKS,
    )
    with pytest.raises(ValueError, match="conflicting calendar day"):
        add_relationship(without_links, conflict)

    reverse = Relationship(
        source_id=build.id,
        target_id=verify.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    with pytest.raises(ValueError, match="New dependency cycle"):
        add_relationship(plan, reverse)
    assert plan.relationships == (plan.relationships[0],)


def test_legacy_cycles_remain_visible_while_unrelated_links_can_be_added() -> None:
    plan = dependency_plan()
    build, verify = plan.work_items
    reverse = Relationship(
        source_id=build.id,
        target_id=verify.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    legacy = replace(plan, relationships=(*plan.relationships, reverse))
    assert dependency_cycle_relationship_ids(legacy) == {
        plan.relationships[0].id,
        reverse.id,
    }
    assert sum(f.kind == DependencyFindingKind.CYCLE for f in dependency_findings(legacy)) == 2

    note = WorkItem(title="Release notes", kind=WorkItemType.TASK)
    review = WorkItem(title="Review notes", kind=WorkItemType.TASK)
    legacy = replace(legacy, work_items=(*legacy.work_items, note, review))
    related = Relationship(
        source_id=note.id,
        target_id=review.id,
        kind=RelationshipType.RELATED_TO,
    )
    changed = add_relationship(legacy, related)
    assert changed.relationships[-1] == related
