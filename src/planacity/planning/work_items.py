"""Validated editing operations; each returns a new plan and preserves the input."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItem


def add_work_item(plan: ProgramPlan, item: WorkItem) -> ProgramPlan:
    """Append an item after its siblings; all references must resolve in the plan."""
    return replace(plan, work_items=(*plan.work_items, item))


def rename_work_item(plan: ProgramPlan, item_id: UUID, title: str) -> ProgramPlan:
    current = plan.work_item(item_id)
    updated = replace(current, title=title)
    return replace(
        plan,
        work_items=tuple(updated if item.id == item_id else item for item in plan.work_items),
    )


def move_work_item(plan: ProgramPlan, item_id: UUID, parent_id: UUID | None) -> ProgramPlan:
    """Move work with its descendants, appending it after the new parent's children.

    Moving to the existing parent is a no-op and keeps the sibling order.
    Descendants retain their parent IDs and sibling order.
    """
    current = plan.work_item(item_id)
    if current.parent_id == parent_id:
        return plan
    updated = replace(current, parent_id=parent_id)
    others = tuple(item for item in plan.work_items if item.id != item_id)
    return replace(plan, work_items=(*others, updated))


def remove_work_item(
    plan: ProgramPlan, item_id: UUID, *, delete_descendants: bool = False
) -> ProgramPlan:
    """Refuse to discard descendants unless their removal is explicitly requested."""
    if type(delete_descendants) is not bool:
        raise ValueError("Confirming removal of descendants requires an explicit boolean value.")
    current = plan.work_item(item_id)
    by_parent: dict[UUID | None, list[UUID]] = {}
    for item in plan.work_items:
        by_parent.setdefault(item.parent_id, []).append(item.id)
    removed: set[UUID] = set()
    pending = [item_id]
    while pending:
        candidate = pending.pop()
        removed.add(candidate)
        pending.extend(by_parent.get(candidate, ()))
    if len(removed) > 1 and not delete_descendants:
        raise ValueError(
            f"'{current.title}' has {len(removed) - 1} descendant(s). "
            "Remove them first or explicitly confirm removal of the whole subtree."
        )
    return replace(
        plan, work_items=tuple(item for item in plan.work_items if item.id not in removed)
    )
