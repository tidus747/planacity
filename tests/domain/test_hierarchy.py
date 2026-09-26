"""Exercise hierarchy rules, ordering, and atomic edits on realistic small plans."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.work_items import (
    add_work_item,
    move_work_item,
    remove_work_item,
    rename_work_item,
)


@pytest.fixture
def plan() -> ProgramPlan:
    integration = WorkItem(title="Integration", kind=WorkItemType.EPIC)
    validation = WorkItem(title="Validation", kind=WorkItemType.EPIC)
    task = WorkItem(title="Build bench", kind=WorkItemType.TASK, parent_id=integration.id)
    subtask = WorkItem(title="Wire sensors", kind=WorkItemType.SUBTASK, parent_id=task.id)
    review = WorkItem(title="Review protocol", kind=WorkItemType.TASK, parent_id=validation.id)
    standalone = WorkItem(title="Documentation", kind=WorkItemType.TASK)
    return ProgramPlan(
        name="Aurora",
        horizon=PlanningHorizon(date(2026, 5, 13), date(2026, 6, 24)),
        work_items=(integration, task, subtask, validation, review, standalone),
    )


def test_hierarchy_order_and_out_of_order_loading(plan: ProgramPlan) -> None:
    epic, task, subtask, other, review, standalone = plan.work_items
    assert plan.children() == (epic, other, standalone)
    assert plan.children(epic.id) == (task,)
    assert plan.children(task.id) == (subtask,)
    assert plan.children(subtask.id) == ()
    # A loader can resolve parent references after receiving the whole snapshot.
    restored = replace(plan, work_items=(subtask, task, epic, other, review, standalone))
    assert restored.children(epic.id) == (task,)
    assert restored.children(task.id) == (subtask,)


@pytest.mark.parametrize("title", ["", "  ", None])
def test_rejects_blank_work_titles(title: object) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        WorkItem(title=title, kind=WorkItemType.TASK)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("id", "bad", "UUID"), ("parent_id", "bad", "UUID"), ("kind", "task", "kind")],
)
def test_rejects_malformed_work_fields(field: str, value: object, message: str) -> None:
    item = WorkItem(title="Work", kind=WorkItemType.TASK)
    with pytest.raises(ValueError, match=message):
        replace(item, **{field: value})


def test_rejects_duplicate_and_unknown_parent_ids(plan: ProgramPlan) -> None:
    with pytest.raises(ValueError, match="duplicated"):
        add_work_item(plan, plan.work_items[0])
    missing = WorkItem(title="Unresolved", kind=WorkItemType.TASK, parent_id=uuid4())
    with pytest.raises(ValueError, match="Parent.*does not exist"):
        add_work_item(plan, missing)


@pytest.mark.parametrize(
    ("kind", "parent_index"),
    [
        (WorkItemType.EPIC, 0),
        (WorkItemType.TASK, 1),
        (WorkItemType.TASK, 2),
        (WorkItemType.SUBTASK, 0),
        (WorkItemType.SUBTASK, 2),
        (WorkItemType.SUBTASK, None),
    ],
)
def test_rejects_invalid_parent_type_combinations(
    plan: ProgramPlan, kind: WorkItemType, parent_index: int | None
) -> None:
    parent_id = None if parent_index is None else plan.work_items[parent_index].id
    item = WorkItem(title="Invalid child", kind=kind, parent_id=parent_id)
    before = plan.work_items
    with pytest.raises(ValueError):
        add_work_item(plan, item)
    assert plan.work_items == before


def test_rejects_self_parent_and_multi_item_cycles(plan: ProgramPlan) -> None:
    epic, task = plan.work_items[:2]
    with pytest.raises(ValueError, match="own parent"):
        move_work_item(plan, task.id, task.id)
    with pytest.raises(ValueError, match="cycle"):
        move_work_item(plan, epic.id, task.id)


def test_rename_preserves_id_position_and_original(plan: ProgramPlan) -> None:
    task = plan.work_items[1]
    changed = rename_work_item(plan, task.id, "Assemble test bench")
    assert changed.work_items[1].title == "Assemble test bench"
    assert [item.id for item in changed.work_items] == [item.id for item in plan.work_items]
    assert changed.id == plan.id
    assert plan.work_items[1].title == "Build bench"
    with pytest.raises(ValueError):
        rename_work_item(plan, task.id, " ")
    assert plan.work_items[1] == task


def test_add_and_move_append_to_target_siblings_preserving_descendants(plan: ProgramPlan) -> None:
    epic, task, subtask, other, review, standalone = plan.work_items
    second_subtask = WorkItem(title="Check wiring", kind=WorkItemType.SUBTASK, parent_id=task.id)
    extended = add_work_item(plan, second_subtask)
    moved = move_work_item(extended, task.id, other.id)
    assert moved.children(epic.id) == ()
    assert moved.children(other.id) == (review, replace(task, parent_id=other.id))
    assert moved.children(task.id) == (subtask, second_subtask)
    assert moved.children() == (epic, other, standalone)
    assert extended.children(epic.id) == (task,)
    assert move_work_item(moved, task.id, other.id) is moved


def test_task_can_move_between_root_and_epic(plan: ProgramPlan) -> None:
    epic, task, _, other, _, standalone = plan.work_items
    rooted = move_work_item(plan, task.id, None)
    assert [item.id for item in rooted.children()] == [epic.id, other.id, standalone.id, task.id]
    restored = move_work_item(rooted, task.id, epic.id)
    assert restored.children(epic.id) == (task,)


def test_delete_requires_confirmation_for_the_whole_subtree(plan: ProgramPlan) -> None:
    epic, task, subtask, other, review, standalone = plan.work_items
    with pytest.raises(ValueError, match="2 descendant"):
        remove_work_item(plan, epic.id)
    assert plan.children(task.id) == (subtask,)
    changed = remove_work_item(plan, epic.id, delete_descendants=True)
    assert changed.work_items == (other, review, standalone)
    assert plan.work_items == (epic, task, subtask, other, review, standalone)


def test_delete_leaf_preserves_other_items_and_order(plan: ProgramPlan) -> None:
    subtask = plan.work_items[2]
    changed = remove_work_item(plan, subtask.id)
    assert changed.work_items == plan.work_items[:2] + plan.work_items[3:]


@pytest.mark.parametrize("confirmation", [1, "false", None])
def test_delete_does_not_treat_non_boolean_values_as_confirmation(
    plan: ProgramPlan, confirmation: object
) -> None:
    with pytest.raises(ValueError, match="explicit boolean"):
        remove_work_item(plan, plan.work_items[0].id, delete_descendants=confirmation)
    assert len(plan.work_items) == 6


def test_unknown_item_operations_fail_without_changing_plan(plan: ProgramPlan) -> None:
    unknown = uuid4()
    before = plan.work_items
    for action in (
        lambda: plan.children(unknown),
        lambda: rename_work_item(plan, unknown, "New name"),
        lambda: move_work_item(plan, unknown, None),
        lambda: remove_work_item(plan, unknown),
        lambda: move_work_item(plan, plan.work_items[1].id, unknown),
    ):
        with pytest.raises(ValueError, match="does not exist"):
            action()
        assert plan.work_items == before
