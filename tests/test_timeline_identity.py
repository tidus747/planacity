"""Timeline visual identity is stable, derived, and independent from Qt."""

from dataclasses import replace
from datetime import date
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan, WorkGroup, WorkItem, WorkItemType
from planacity.persistence.codec import dumps, loads
from planacity.planning.timeline import project_timeline
from planacity.planning.work_context import TopicState
from planacity.ui.theme import Theme
from planacity.ui.timeline_identity import (
    GROUP_PALETTES,
    TimelineBarShape,
    bar_identity,
    palette_slot,
    work_shape,
)


def _identity_plan() -> tuple[ProgramPlan, WorkGroup, WorkGroup]:
    explicit_group = WorkGroup(
        id=UUID("10000000-0000-0000-0000-000000000001"),
        name="Launch Systems",
    )
    inherited_group = WorkGroup(
        id=UUID("20000000-0000-0000-0000-000000000002"),
        name="Surface Operations",
    )
    explicit = WorkItem(
        title="Explicit topic",
        kind=WorkItemType.TASK,
        primary_group_id=explicit_group.id,
    )
    epic = WorkItem(title="Inherited topic", kind=WorkItemType.EPIC)
    inherited = WorkItem(
        title="Inherited child",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
    )
    ungrouped = WorkItem(title="Ungrouped", kind=WorkItemType.TASK)
    inherited_group = replace(inherited_group, epic_ids=(epic.id,))
    return (
        ProgramPlan(
            name="Visual identity",
            horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
            work_items=(explicit, epic, inherited, ungrouped),
            work_groups=(explicit_group, inherited_group),
        ),
        explicit_group,
        inherited_group,
    )


def test_bar_identity_uses_canonical_explicit_inherited_and_neutral_topics() -> None:
    plan, explicit_group, inherited_group = _identity_plan()
    projection = project_timeline(plan)
    identities = {row.title: bar_identity(row, projection.groups) for row in projection.rows}

    assert identities["Explicit topic"].group_id == explicit_group.id
    assert identities["Explicit topic"].label == "Launch Systems"
    assert identities["Inherited topic"].group_id == inherited_group.id
    assert identities["Inherited child"].group_id == inherited_group.id
    assert identities["Ungrouped"].state == TopicState.UNGROUPED
    assert identities["Ungrouped"].label == "Ungrouped"
    assert not identities["Ungrouped"].patterned


def test_ambiguous_legacy_membership_uses_named_patterned_identity() -> None:
    epic = WorkItem(title="Shared epic", kind=WorkItemType.EPIC)
    plan = ProgramPlan(
        name="Ambiguous",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        work_items=(epic,),
        work_groups=(
            WorkGroup(name="One", epic_ids=(epic.id,)),
            WorkGroup(name="Two", epic_ids=(epic.id,)),
        ),
    )
    projection = project_timeline(plan)

    identity = bar_identity(projection.rows[0], projection.groups)
    assert identity.state == TopicState.AMBIGUOUS
    assert identity.label == "Ambiguous group"
    assert identity.patterned


def test_palette_slot_survives_rename_reorder_new_groups_and_roundtrip() -> None:
    plan, explicit_group, inherited_group = _identity_plan()
    expected = palette_slot(explicit_group.id)
    renamed = replace(explicit_group, name="Renamed Launch Systems")
    added = WorkGroup(name="New group")
    changed = replace(plan, work_groups=(added, inherited_group, renamed))
    reopened = loads(dumps(changed))

    projection = project_timeline(reopened)
    row = next(row for row in projection.rows if row.title == "Explicit topic")
    identity = bar_identity(row, projection.groups)
    assert identity.palette_slot == expected
    assert identity.label == "Renamed Launch Systems"
    assert identity.color(Theme.LIGHT) == GROUP_PALETTES[Theme.LIGHT][expected]
    assert identity.color(Theme.DARK) == GROUP_PALETTES[Theme.DARK][expected]
    assert identity.color(Theme.LIGHT) != identity.color(Theme.DARK)


def test_palette_collisions_keep_group_names_authoritative() -> None:
    by_slot: dict[int, UUID] = {}
    collision: tuple[UUID, UUID] | None = None
    for value in range(1, 20):
        candidate = UUID(int=value)
        slot = palette_slot(candidate)
        if slot in by_slot:
            collision = (by_slot[slot], candidate)
            break
        by_slot[slot] = candidate

    assert collision is not None
    first, second = collision
    assert first != second
    assert palette_slot(first) == palette_slot(second)

    groups = (WorkGroup(id=first, name="Alpha"), WorkGroup(id=second, name="Beta"))
    items = tuple(
        WorkItem(title=group.name, kind=WorkItemType.TASK, primary_group_id=group.id)
        for group in groups
    )
    plan = ProgramPlan(
        name="Collision",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 2)),
        work_items=items,
        work_groups=groups,
    )
    projection = project_timeline(plan)
    identities = [bar_identity(row, projection.groups) for row in projection.rows]
    assert [identity.label for identity in identities] == ["Alpha", "Beta"]
    assert identities[0].palette_slot == identities[1].palette_slot


def test_work_types_have_distinct_stable_shapes() -> None:
    assert work_shape(WorkItemType.EPIC) == TimelineBarShape.EPIC
    assert work_shape(WorkItemType.TASK) == TimelineBarShape.TASK
    assert work_shape(WorkItemType.SUBTASK) == TimelineBarShape.SUBTASK
    assert len({work_shape(kind) for kind in WorkItemType}) == 3
