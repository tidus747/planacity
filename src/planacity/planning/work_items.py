"""Validated editing operations; each returns a new plan and preserves the input."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.dependency_validation import validate_dependency_change


def set_work_estimate(
    plan: ProgramPlan, item_id: UUID, estimate_hours: Decimal | None
) -> ProgramPlan:
    """Set exact hours, including zero; None explicitly clears an unknown estimate."""
    updated = replace(plan.work_item(item_id), estimate_hours=estimate_hours)
    return replace(
        plan,
        work_items=tuple(updated if item.id == item_id else item for item in plan.work_items),
    )


def set_work_dates(
    plan: ProgramPlan, item_id: UUID, *, start: date | None, end: date | None
) -> ProgramPlan:
    """Set both optional dates together, preserving dates outside the horizon."""
    updated = replace(plan.work_item(item_id), start=start, end=end)
    candidate = replace(
        plan,
        work_items=tuple(updated if item.id == item_id else item for item in plan.work_items),
    )
    validate_dependency_change(plan, candidate, affected_item_ids=(item_id,))
    return candidate


def work_outside_horizon(plan: ProgramPlan) -> tuple[WorkItem, ...]:
    """Return items with any known date outside the inclusive planning horizon.

    Missing dates are not inferred. Callers can display this finding without
    rejecting or silently changing the user's schedule.
    """
    return tuple(
        item
        for item in plan.work_items
        if any(
            value is not None and not plan.horizon.start <= value <= plan.horizon.end
            for value in (item.start, item.end)
        )
    )


def _direct_allocations(plan: ProgramPlan, item_id: UUID) -> tuple[Allocation, ...]:
    return tuple(
        allocation for allocation in plan.allocations if allocation.work_item_id == item_id
    )


def _transfer_effort_to_child(plan: ProgramPlan, parent: WorkItem, child: WorkItem) -> ProgramPlan:
    if child.estimate_hours is not None:
        raise ValueError("The resolution leaf must not already have an estimate.")
    direct = _direct_allocations(plan, parent.id)
    people = {allocation.person_id for allocation in direct}
    assignee_id = next(iter(people)) if len(people) == 1 else child.assignee_id
    moved_child = replace(
        child,
        assignee_id=assignee_id,
        estimate_hours=parent.estimate_hours,
    )
    cleared_parent = replace(parent, estimate_hours=None)
    work_items = tuple(
        cleared_parent if current.id == parent.id else current for current in plan.work_items
    )
    return replace(
        plan,
        work_items=(*work_items, moved_child),
        allocations=tuple(
            replace(allocation, work_item_id=moved_child.id)
            if allocation.work_item_id == parent.id
            else allocation
            for allocation in plan.allocations
        ),
    )


def add_work_item(
    plan: ProgramPlan, item: WorkItem, *, transfer_parent_effort: bool = False
) -> ProgramPlan:
    """Append an item, explicitly resolving an allocated leaf when requested."""
    if type(transfer_parent_effort) is not bool:
        raise ValueError("Transferring parent effort requires an explicit boolean value.")
    candidate = replace(plan, work_items=(*plan.work_items, item))
    if item.parent_id is None:
        return candidate
    parent = plan.work_item(item.parent_id)
    allocated_leaf = not plan.children(parent.id) and bool(_direct_allocations(plan, parent.id))
    if allocated_leaf and not transfer_parent_effort:
        raise ValueError(
            f"'{parent.title}' has direct allocations. Move its estimate and allocations "
            "to the new leaf or cancel."
        )
    if allocated_leaf:
        return _transfer_effort_to_child(plan, parent, item)
    return candidate


def rename_work_item(plan: ProgramPlan, item_id: UUID, title: str) -> ProgramPlan:
    current = plan.work_item(item_id)
    updated = replace(current, title=title)
    return replace(
        plan,
        work_items=tuple(updated if item.id == item_id else item for item in plan.work_items),
    )


def move_work_item(
    plan: ProgramPlan,
    item_id: UUID,
    parent_id: UUID | None,
    *,
    resolve_parent_effort: bool = False,
) -> ProgramPlan:
    """Move work with its descendants, appending it after the new parent's children.

    Moving to the existing parent is a no-op and keeps the sibling order.
    Descendants retain their parent IDs and sibling order.
    """
    if type(resolve_parent_effort) is not bool:
        raise ValueError("Resolving parent effort requires an explicit boolean value.")
    current = plan.work_item(item_id)
    if current.parent_id == parent_id:
        return plan
    candidate = plan
    if parent_id is not None:
        parent = plan.work_item(parent_id)
        allocated_leaf = not plan.children(parent.id) and bool(_direct_allocations(plan, parent.id))
        if allocated_leaf and not resolve_parent_effort:
            raise ValueError(
                f"'{parent.title}' has direct allocations. Move them to a new leaf "
                "before making it a container, or cancel."
            )
        if allocated_leaf:
            child_kind = (
                WorkItemType.TASK if parent.kind == WorkItemType.EPIC else WorkItemType.SUBTASK
            )
            resolution = WorkItem(
                title=f"{parent.title} effort", kind=child_kind, parent_id=parent.id
            )
            candidate = _transfer_effort_to_child(plan, parent, resolution)
    updated = replace(current, parent_id=parent_id)
    others = tuple(item for item in candidate.work_items if item.id != item_id)
    return replace(candidate, work_items=(*others, updated))


def resolve_container_effort(plan: ProgramPlan, item_id: UUID, leaf_title: str) -> ProgramPlan:
    """Move a container's entered estimate and direct allocations to a new leaf."""
    parent = plan.work_item(item_id)
    allocations = _direct_allocations(plan, item_id)
    if not plan.children(item_id):
        raise ValueError(f"'{parent.title}' is already leaf work.")
    if not allocations:
        raise ValueError(f"'{parent.title}' has no direct allocations to resolve.")
    if parent.kind == WorkItemType.SUBTASK:
        raise ValueError("A Subtask cannot contain resolution work.")
    child_kind = WorkItemType.TASK if parent.kind == WorkItemType.EPIC else WorkItemType.SUBTASK
    child = WorkItem(title=leaf_title, kind=child_kind, parent_id=parent.id)
    return _transfer_effort_to_child(plan, parent, child)


def remove_work_item(
    plan: ProgramPlan,
    item_id: UUID,
    *,
    delete_descendants: bool = False,
    remove_references: bool = False,
    remove_allocations: bool = False,
) -> ProgramPlan:
    """Refuse to discard descendants unless their removal is explicitly requested."""
    if type(delete_descendants) is not bool:
        raise ValueError("Confirming removal of descendants requires an explicit boolean value.")
    if type(remove_allocations) is not bool:
        raise ValueError("Confirming allocation removal requires an explicit boolean.")
    if type(remove_references) is not bool:
        raise ValueError("Confirming removal of references requires an explicit boolean value.")
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
    links = tuple(
        link
        for link in plan.relationships
        if link.source_id in removed or link.target_id in removed
    )
    allocations = tuple(a for a in plan.allocations if a.work_item_id in removed)
    if allocations and not remove_allocations:
        raise ValueError(
            f"Removal affects {len(allocations)} work allocation(s). "
            "Explicitly confirm removal of these allocations first."
        )
    memberships = sum(len(removed.intersection(group.epic_ids)) for group in plan.work_groups)
    if (links or memberships) and not remove_references:
        raise ValueError(
            f"Removal affects {len(links)} relationship(s) and {memberships} group membership(s). "
            "Unlink them first or explicitly confirm removal of these references."
        )
    return replace(
        plan,
        work_items=tuple(item for item in plan.work_items if item.id not in removed),
        allocations=tuple(a for a in plan.allocations if a.work_item_id not in removed),
        relationships=tuple(
            link
            for link in plan.relationships
            if link.source_id not in removed and link.target_id not in removed
        ),
        work_groups=tuple(
            replace(
                group,
                epic_ids=tuple(epic_id for epic_id in group.epic_ids if epic_id not in removed),
            )
            for group in plan.work_groups
        ),
    )
