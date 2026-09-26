"""Groups and links never silently change hierarchy or discard referenced work."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.structure import (
    add_relationship,
    add_work_group,
    remove_relationship,
    remove_work_group,
    rename_work_group,
    set_group_epics,
)
from planacity.planning.work_items import remove_work_item


@pytest.fixture
def plan() -> ProgramPlan:
    epic = WorkItem(title="Integration", kind=WorkItemType.EPIC)
    task = WorkItem(title="Assemble", kind=WorkItemType.TASK, parent_id=epic.id)
    subtask = WorkItem(title="Inspect", kind=WorkItemType.SUBTASK, parent_id=task.id)
    other = WorkItem(title="Validation", kind=WorkItemType.EPIC)
    return ProgramPlan(
        name="Aurora",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 3, 31)),
        work_items=(epic, task, subtask, other),
    )


def test_group_lifecycle_preserves_work_and_membership_order(plan: ProgramPlan) -> None:
    first, _, _, second = plan.work_items
    group = WorkGroup(name="Machine", epic_ids=(second.id, first.id))
    added = add_work_group(plan, group)
    renamed = rename_work_group(added, group.id, "Alpha machine")
    changed = set_group_epics(renamed, group.id, (first.id,))
    removed = remove_work_group(changed, group.id)
    assert added.work_group(group.id).epic_ids == (second.id, first.id)
    assert renamed.work_group(group.id).name == "Alpha machine"
    assert changed.work_group(group.id).epic_ids == (first.id,)
    assert removed == plan
    assert added.work_items == renamed.work_items == changed.work_items == plan.work_items
    assert added.work_groups == (group,)


def test_an_epic_can_belong_to_more_than_one_group(plan: ProgramPlan) -> None:
    first = WorkGroup(name="Machine", epic_ids=(plan.work_items[0].id,))
    second = WorkGroup(name="Customer", epic_ids=first.epic_ids)
    changed = add_work_group(add_work_group(plan, first), second)
    assert len(changed.work_groups) == 2
    assert remove_work_group(changed, first.id).work_groups == (second,)


def test_groups_reject_missing_or_non_epic_members_and_duplicate_ids(plan: ProgramPlan) -> None:
    for invalid_id in (uuid4(), plan.work_items[1].id):
        with pytest.raises(ValueError, match="existing Epics"):
            add_work_group(plan, WorkGroup(name="Invalid", epic_ids=(invalid_id,)))
    group = WorkGroup(name="Machine")
    with pytest.raises(ValueError, match="unique"):
        add_work_group(add_work_group(plan, group), replace(group, name="Duplicate ID"))
    assert plan.work_groups == ()


@pytest.mark.parametrize(
    "fields",
    [{"name": " "}, {"id": "invalid"}, {"epic_ids": []}, {"epic_ids": ("invalid",)}],
)
def test_invalid_group_fields(fields: dict) -> None:
    with pytest.raises(ValueError):
        WorkGroup(**({"name": "Machine"} | fields))


def test_duplicate_group_membership_is_rejected(plan: ProgramPlan) -> None:
    epic_id = plan.work_items[0].id
    with pytest.raises(ValueError, match="unique"):
        WorkGroup(name="Machine", epic_ids=(epic_id, epic_id))


@pytest.mark.parametrize("kind", list(RelationshipType))
def test_relationship_add_remove_preserves_dates_and_hierarchy(
    plan: ProgramPlan, kind: RelationshipType
) -> None:
    first, _, _, second = plan.work_items
    link = Relationship(source_id=first.id, target_id=second.id, kind=kind)
    added = add_relationship(plan, link)
    assert added.relationships == (link,)
    assert added.work_items == plan.work_items
    assert remove_relationship(added, link.id) == plan


@pytest.mark.parametrize("kind", list(RelationshipType))
def test_duplicate_links_are_rejected_even_with_new_ids(
    plan: ProgramPlan, kind: RelationshipType
) -> None:
    first, _, _, second = plan.work_items
    link = Relationship(source_id=first.id, target_id=second.id, kind=kind)
    with pytest.raises(ValueError, match="Duplicate relationship"):
        add_relationship(add_relationship(plan, link), replace(link, id=uuid4()))


@pytest.mark.parametrize(
    ("first_kind", "reverse_kind"),
    [
        (RelationshipType.RELATED_TO, RelationshipType.RELATED_TO),
        (RelationshipType.DEPENDS_ON, RelationshipType.BLOCKS),
    ],
)
def test_equivalent_reversed_links_are_duplicates(
    plan: ProgramPlan, first_kind: RelationshipType, reverse_kind: RelationshipType
) -> None:
    first, _, _, second = plan.work_items
    link = Relationship(source_id=first.id, target_id=second.id, kind=first_kind)
    reversed_link = Relationship(source_id=second.id, target_id=first.id, kind=reverse_kind)
    with pytest.raises(ValueError, match="Duplicate relationship"):
        add_relationship(add_relationship(plan, link), reversed_link)


def test_direction_is_preserved_and_different_link_kinds_can_coexist(plan: ProgramPlan) -> None:
    first, _, _, second = plan.work_items
    dependency = Relationship(
        source_id=first.id,
        target_id=second.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    related = replace(dependency, id=uuid4(), kind=RelationshipType.RELATED_TO)
    added = add_relationship(add_relationship(plan, dependency), related)
    assert added.relationships == (dependency, related)


def test_invalid_relationships_and_ids(plan: ProgramPlan) -> None:
    first, _, _, second = plan.work_items
    with pytest.raises(ValueError, match="itself"):
        Relationship(source_id=first.id, target_id=first.id, kind=RelationshipType.BLOCKS)
    with pytest.raises(ValueError, match="kind"):
        Relationship(source_id=first.id, target_id=second.id, kind="depends_on")
    with pytest.raises(ValueError, match="UUID"):
        Relationship(source_id="invalid", target_id=second.id, kind=RelationshipType.BLOCKS)
    missing = Relationship(source_id=uuid4(), target_id=second.id, kind=RelationshipType.BLOCKS)
    with pytest.raises(ValueError, match="existing work items"):
        add_relationship(plan, missing)
    link = replace(missing, source_id=first.id)
    with pytest.raises(ValueError, match="IDs must be unique"):
        add_relationship(
            add_relationship(plan, link), replace(link, kind=RelationshipType.RELATED_TO)
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("work_groups", []),
        ("work_groups", ("bad",)),
        ("relationships", []),
        ("relationships", ("bad",)),
    ],
)
def test_malformed_aggregate_collections(plan: ProgramPlan, field: str, value: object) -> None:
    with pytest.raises(ValueError, match="tuple"):
        replace(plan, **{field: value})


def test_subtree_removal_requires_both_confirmations_and_cleans_references(
    plan: ProgramPlan,
) -> None:
    epic, task, subtask, other = plan.work_items
    link = Relationship(source_id=subtask.id, target_id=other.id, kind=RelationshipType.DEPENDS_ON)
    incoming = Relationship(
        source_id=other.id,
        target_id=task.id,
        kind=RelationshipType.RELATED_TO,
    )
    # Both relationship endpoints inside the removed subtree are handled as well.
    internal = Relationship(source_id=task.id, target_id=subtask.id, kind=RelationshipType.BLOCKS)
    group = WorkGroup(name="Machine", epic_ids=(epic.id, other.id))
    linked = add_work_group(
        add_relationship(add_relationship(add_relationship(plan, link), incoming), internal), group
    )
    with pytest.raises(ValueError, match="descendant"):
        remove_work_item(linked, epic.id, remove_references=True)
    with pytest.raises(ValueError, match="3 relationship.*1 group membership"):
        remove_work_item(linked, epic.id, delete_descendants=True)
    removed = remove_work_item(linked, epic.id, delete_descendants=True, remove_references=True)
    assert removed.work_items == (other,)
    assert removed.relationships == ()
    assert removed.work_groups == (replace(group, epic_ids=(other.id,)),)
    assert len(linked.work_items) == 4
    assert linked.relationships == (link, incoming, internal)


def test_leaf_removal_preserves_unaffected_links_and_groups(plan: ProgramPlan) -> None:
    epic, task, subtask, other = plan.work_items
    keep = Relationship(source_id=epic.id, target_id=other.id, kind=RelationshipType.BLOCKS)
    discard = Relationship(
        source_id=task.id, target_id=subtask.id, kind=RelationshipType.RELATED_TO
    )
    group = WorkGroup(name="Machine", epic_ids=(epic.id, other.id))
    linked = add_work_group(add_relationship(add_relationship(plan, keep), discard), group)
    with pytest.raises(ValueError, match="relationship"):
        remove_work_item(linked, subtask.id)
    removed = remove_work_item(linked, subtask.id, remove_references=True)
    assert removed.relationships == (keep,)
    assert removed.work_groups == (group,)
    assert removed.work_items == (epic, task, other)


@pytest.mark.parametrize("confirmation", ["false", 1, None])
def test_reference_confirmation_must_be_boolean(plan: ProgramPlan, confirmation: object) -> None:
    with pytest.raises(ValueError, match="explicit boolean"):
        remove_work_item(plan, plan.work_items[2].id, remove_references=confirmation)


def test_unknown_structure_edits_leave_plan_unchanged(plan: ProgramPlan) -> None:
    missing = uuid4()
    for edit in (
        lambda: rename_work_group(plan, missing, "Name"),
        lambda: set_group_epics(plan, missing, ()),
        lambda: remove_work_group(plan, missing),
        lambda: remove_relationship(plan, missing),
    ):
        with pytest.raises(ValueError, match="does not exist"):
            edit()
    assert plan.work_groups == plan.relationships == ()
