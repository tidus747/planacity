"""Canonical work ownership, separate from capacity hours and external identities."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItemType
from planacity.planning.assignment_policy import assignment_policy_conflicts


def effective_assignee_id(plan: ProgramPlan, item_id: UUID) -> UUID | None:
    """Return stored ownership, or one unambiguous legacy leaf allocation."""
    item = plan.work_item(item_id)
    if item.assignee_id is not None:
        return item.assignee_id
    if item.kind == WorkItemType.EPIC or plan.children(item_id):
        return None
    people = {
        allocation.person_id
        for allocation in plan.allocations
        if allocation.work_item_id == item_id
    }
    return next(iter(people)) if len(people) == 1 else None


def set_work_assignee(plan: ProgramPlan, item_id: UUID, person_id: UUID | None) -> ProgramPlan:
    """Set one owner and reassign one executable allocation without changing hours."""
    item = plan.work_item(item_id)
    if person_id is not None:
        plan.person(person_id)
    conflict = next(
        (value for value in assignment_policy_conflicts(plan) if value.work_item_id == item_id),
        None,
    )
    if conflict is not None and person_id != item.assignee_id:
        raise ValueError(
            f"Resolve the multiple assignments on '{item.title}' before changing its assignee."
        )

    updated_item = replace(item, assignee_id=person_id)
    allocations = plan.allocations
    direct = tuple(allocation for allocation in allocations if allocation.work_item_id == item_id)
    if (
        person_id is None
        and item.kind != WorkItemType.EPIC
        and not plan.children(item_id)
        and len(direct) == 1
    ):
        raise ValueError(
            f"Remove the Allocation from '{item.title}' explicitly before clearing its assignee."
        )
    if (
        person_id is not None
        and item.kind != WorkItemType.EPIC
        and not plan.children(item_id)
        and len(direct) == 1
        and direct[0].person_id != person_id
    ):
        allocations = tuple(
            replace(allocation, person_id=person_id)
            if allocation.id == direct[0].id
            else allocation
            for allocation in allocations
        )
    return replace(
        plan,
        work_items=tuple(
            updated_item if current.id == item_id else current for current in plan.work_items
        ),
        allocations=allocations,
    )
