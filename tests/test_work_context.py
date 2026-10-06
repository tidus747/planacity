"""Work context remains canonical, immutable, and useful to shared projections."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest

from planacity.domain import PlanningHorizon, ProgramPlan, WorkGroup, WorkItem, WorkItemType
from planacity.planning.plan_filters import filter_plan
from planacity.planning.timeline import project_timeline
from planacity.planning.timeline_view import TimelineFilters
from planacity.planning.work_context import (
    TopicState,
    effective_group_ids,
    resolve_topic,
    update_work_context,
)


@pytest.fixture
def plan() -> ProgramPlan:
    epic = WorkItem(title="Integration", kind=WorkItemType.EPIC)
    task = WorkItem(title="Build", kind=WorkItemType.TASK, parent_id=epic.id)
    subtask = WorkItem(title="Verify", kind=WorkItemType.SUBTASK, parent_id=task.id)
    standalone = WorkItem(title="Release notes", kind=WorkItemType.TASK)
    alpha = WorkGroup(name="Alpha", epic_ids=(epic.id,))
    beta = WorkGroup(name="Beta", epic_ids=(epic.id,))
    return ProgramPlan(
        name="Context",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 3, 31)),
        work_items=(epic, task, subtask, standalone),
        work_groups=(alpha, beta),
    )


def test_context_edit_is_atomic_and_preserves_text_label_order(plan: ProgramPlan) -> None:
    task = plan.work_items[1]
    alpha = plan.work_groups[0]

    changed = update_work_context(
        plan,
        task.id,
        description="First line\n\nSecond line",
        labels=("firmware", "Customer-A"),
        primary_group_id=alpha.id,
    )

    assert plan.work_items[1] is task
    assert changed.work_items[1] == replace(
        task,
        description="First line\n\nSecond line",
        labels=("firmware", "Customer-A"),
        primary_group_id=alpha.id,
    )
    assert changed.work_items[0] is plan.work_items[0]


@pytest.mark.parametrize(
    "fields",
    [
        {"description": 1},
        {"labels": ["firmware"]},
        {"labels": ("",)},
        {"labels": (" firmware",)},
        {"labels": ("firmware", "Firmware")},
        {"labels": (1,)},
        {"primary_group_id": "alpha"},
    ],
)
def test_work_context_rejects_noncanonical_values(fields: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkItem(title="Build", kind=WorkItemType.TASK, **fields)


def test_primary_group_must_belong_to_the_same_plan(plan: ProgramPlan) -> None:
    with pytest.raises(ValueError, match="existing WorkGroup"):
        replace(
            plan,
            work_items=(replace(plan.work_items[0], primary_group_id=uuid4()),),
        )
    with pytest.raises(ValueError, match="does not exist"):
        update_work_context(
            plan,
            plan.work_items[0].id,
            description="",
            labels=(),
            primary_group_id=uuid4(),
        )


def test_topic_resolution_distinguishes_legacy_ambiguity_and_no_group(
    plan: ProgramPlan,
) -> None:
    epic, task, _, standalone = plan.work_items
    assert resolve_topic(plan, epic.id) == replace(resolve_topic(plan, task.id), item_id=epic.id)
    resolution = resolve_topic(plan, task.id)
    assert resolution.state == TopicState.AMBIGUOUS
    assert resolution.group_id is None
    assert resolution.candidate_group_ids == tuple(group.id for group in plan.work_groups)
    assert resolve_topic(plan, standalone.id).state == TopicState.UNGROUPED

    one_group = replace(plan, work_groups=plan.work_groups[:1])
    inherited = resolve_topic(one_group, task.id)
    assert inherited.state == TopicState.RESOLVED
    assert inherited.group_id == plan.work_groups[0].id


def test_nearest_explicit_topic_wins_and_standalone_work_is_classifiable(
    plan: ProgramPlan,
) -> None:
    epic, task, subtask, standalone = plan.work_items
    alpha, beta = plan.work_groups
    explicit = replace(
        plan,
        work_items=(
            replace(epic, primary_group_id=alpha.id),
            replace(task, primary_group_id=beta.id),
            subtask,
            replace(standalone, primary_group_id=beta.id),
        ),
    )

    assert resolve_topic(explicit, epic.id).group_id == alpha.id
    assert resolve_topic(explicit, task.id).group_id == beta.id
    assert resolve_topic(explicit, subtask.id).group_id == beta.id
    assert resolve_topic(explicit, standalone.id).group_id == beta.id


def test_effective_filters_keep_legacy_memberships_and_add_primary_topic(
    plan: ProgramPlan,
) -> None:
    epic, task, subtask, standalone = plan.work_items
    alpha, beta = plan.work_groups
    gamma = WorkGroup(name="Gamma")
    changed = replace(
        plan,
        work_items=(epic, replace(task, primary_group_id=gamma.id), subtask, standalone),
        work_groups=(alpha, beta, gamma),
    )

    assert effective_group_ids(changed, subtask.id) == (alpha.id, beta.id, gamma.id)
    rows = {row.item_id: row for row in project_timeline(changed).rows}
    assert rows[subtask.id].group_ids == (alpha.id, beta.id, gamma.id)
    assert filter_plan(changed, TimelineFilters(group_id=gamma.id)).matches == {
        task.id,
        subtask.id,
    }
