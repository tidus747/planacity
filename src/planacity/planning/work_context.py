"""Immutable work metadata edits and reporting-topic resolution."""

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItem, WorkItemType


class TopicState(StrEnum):
    """Whether one WorkGroup can receive this work in additive reporting."""

    RESOLVED = "resolved"
    UNGROUPED = "ungrouped"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, kw_only=True)
class TopicResolution:
    """A resolved primary topic or a reviewable exception bucket."""

    item_id: UUID
    state: TopicState
    group_id: UUID | None
    candidate_group_ids: tuple[UUID, ...] = ()


def update_work_context(
    plan: ProgramPlan,
    item_id: UUID,
    *,
    description: str,
    labels: tuple[str, ...],
    primary_group_id: UUID | None,
) -> ProgramPlan:
    """Replace editable context atomically, preserving the original plan."""
    if primary_group_id is not None:
        plan.work_group(primary_group_id)
    updated = replace(
        plan.work_item(item_id),
        description=description,
        labels=labels,
        primary_group_id=primary_group_id,
    )
    return replace(
        plan,
        work_items=tuple(updated if item.id == item_id else item for item in plan.work_items),
    )


def resolve_topic(plan: ProgramPlan, item_id: UUID) -> TopicResolution:
    """Resolve the nearest explicit topic, then the legacy Epic memberships."""
    current = plan.work_item(item_id)
    while True:
        if current.primary_group_id is not None:
            return TopicResolution(
                item_id=item_id,
                state=TopicState.RESOLVED,
                group_id=current.primary_group_id,
                candidate_group_ids=(current.primary_group_id,),
            )
        if current.parent_id is None:
            break
        current = plan.work_item(current.parent_id)

    epic_id = current.id if current.kind == WorkItemType.EPIC else None
    candidates = tuple(
        group.id for group in plan.work_groups if epic_id is not None and epic_id in group.epic_ids
    )
    if len(candidates) == 1:
        return TopicResolution(
            item_id=item_id,
            state=TopicState.RESOLVED,
            group_id=candidates[0],
            candidate_group_ids=candidates,
        )
    if not candidates:
        return TopicResolution(
            item_id=item_id,
            state=TopicState.UNGROUPED,
            group_id=None,
        )
    return TopicResolution(
        item_id=item_id,
        state=TopicState.AMBIGUOUS,
        group_id=None,
        candidate_group_ids=candidates,
    )


def effective_group_ids(plan: ProgramPlan, item_id: UUID) -> tuple[UUID, ...]:
    """Return filter context in canonical group order without duplicating state."""
    current: WorkItem = plan.work_item(item_id)
    while current.parent_id is not None:
        current = plan.work_item(current.parent_id)
    inherited = {
        group.id
        for group in plan.work_groups
        if current.kind == WorkItemType.EPIC and current.id in group.epic_ids
    }
    resolution = resolve_topic(plan, item_id)
    if resolution.group_id is not None:
        inherited.add(resolution.group_id)
    return tuple(group.id for group in plan.work_groups if group.id in inherited)
