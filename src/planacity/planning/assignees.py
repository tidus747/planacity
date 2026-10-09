"""Canonical work ownership, separate from capacity hours and external identities."""

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan, WorkItemType
from planacity.planning.allocations import sum_hours_exact
from planacity.planning.assignment_policy import assignment_policy_conflicts


@dataclass(frozen=True)
class WorkContributor:
    """One person's exact allocated hours within a work subtree."""

    person_id: UUID
    hours: Decimal


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


def set_work_assignment(
    plan: ProgramPlan,
    item_id: UUID,
    person_id: UUID | None,
    hours: Decimal | None,
) -> ProgramPlan:
    """Atomically set one executable owner and optional explicit capacity hours.

    A blank hours value means ownership without capacity demand. Clearing the
    person removes the sole Allocation as an explicit part of this operation.
    Existing Allocation identity and order are preserved when editing or
    reassigning it.
    """
    item = plan.work_item(item_id)
    if item.kind == WorkItemType.EPIC:
        if hours is not None:
            raise ValueError("Epic feature owners do not have allocated hours.")
        return set_work_assignee(plan, item_id, person_id)
    if plan.children(item_id):
        raise ValueError(
            "Container assignments are derived from their leaves. "
            "Assign each Task or Subtask separately."
        )
    if person_id is not None:
        plan.person(person_id)
    if person_id is None and hours is not None:
        raise ValueError("Choose an assignee before entering allocated hours.")
    if hours is not None and (not isinstance(hours, Decimal) or not hours.is_finite() or hours < 0):
        raise ValueError("Allocated hours must be a finite, non-negative number.")

    direct = tuple(
        allocation for allocation in plan.allocations if allocation.work_item_id == item_id
    )
    conflict = next(
        (value for value in assignment_policy_conflicts(plan) if value.work_item_id == item_id),
        None,
    )
    if conflict is not None or len(direct) > 1:
        raise ValueError(
            f"Resolve the multiple assignments on '{item.title}' before editing its assignment."
        )

    updated_item = replace(item, assignee_id=person_id)
    if person_id is None or hours is None:
        allocations = tuple(
            allocation for allocation in plan.allocations if allocation.work_item_id != item_id
        )
    elif direct:
        changed = replace(direct[0], person_id=person_id, hours=hours)
        allocations = tuple(
            changed if allocation.id == changed.id else allocation
            for allocation in plan.allocations
        )
    else:
        allocations = (
            *plan.allocations,
            Allocation(work_item_id=item_id, person_id=person_id, hours=hours),
        )
    return replace(
        plan,
        work_items=tuple(
            updated_item if current.id == item_id else current for current in plan.work_items
        ),
        allocations=allocations,
    )


def work_contributors(plan: ProgramPlan, item_id: UUID) -> tuple[WorkContributor, ...]:
    """Return exact person totals for an item and all of its descendants."""
    plan.work_item(item_id)
    work_ids = {item_id}
    pending = [item_id]
    while pending:
        children = plan.children(pending.pop())
        work_ids.update(child.id for child in children)
        pending.extend(child.id for child in children)

    by_person: dict[UUID, list[Decimal]] = {}
    for allocation in plan.allocations:
        if allocation.work_item_id in work_ids:
            by_person.setdefault(allocation.person_id, []).append(allocation.hours)
    return tuple(
        WorkContributor(person.id, sum_hours_exact(tuple(by_person[person.id])))
        for person in plan.people
        if person.id in by_person
    )
