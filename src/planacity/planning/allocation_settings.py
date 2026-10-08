"""Allocation lifecycle preserves identities, order, and unrelated plan data."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan, WorkItemType
from planacity.planning.assignment_policy import validate_assignment_transition


def allocation_by_id(plan: ProgramPlan, allocation_id: UUID) -> Allocation:
    for allocation in plan.allocations:
        if allocation.id == allocation_id:
            return allocation
    raise ValueError("Allocation does not exist in this plan.")


def add_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    item = plan.work_item(allocation.work_item_id)
    if item.kind == WorkItemType.EPIC:
        raise ValueError(
            "Epic assignees are feature owners. Allocate capacity to Tasks or Subtasks."
        )
    if plan.children(allocation.work_item_id):
        raise ValueError(
            "Allocate effort to leaf work. Container totals are derived from their children."
        )
    allocation_candidate = replace(plan, allocations=(*plan.allocations, allocation))
    validate_assignment_transition(plan, allocation_candidate)
    if item.assignee_id is not None and item.assignee_id != allocation.person_id:
        raise ValueError(
            f"'{item.title}' is assigned to '{plan.person(item.assignee_id).name}'. "
            "Reassign the work before allocating it to another person."
        )
    updated_item = replace(item, assignee_id=allocation.person_id)
    candidate = replace(
        plan,
        work_items=tuple(
            updated_item if current.id == item.id else current for current in plan.work_items
        ),
        allocations=allocation_candidate.allocations,
    )
    return candidate


def update_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    original = allocation_by_id(plan, allocation.id)
    item = plan.work_item(allocation.work_item_id)
    if allocation.work_item_id != original.work_item_id:
        if item.kind == WorkItemType.EPIC:
            raise ValueError(
                "Epic assignees are feature owners. Allocate capacity to Tasks or Subtasks."
            )
    if allocation.work_item_id != original.work_item_id and plan.children(allocation.work_item_id):
        raise ValueError(
            "Allocate effort to leaf work. Container totals are derived from their children."
        )
    changed_allocations = tuple(
        allocation if current.id == allocation.id else current for current in plan.allocations
    )
    allocation_candidate = replace(plan, allocations=changed_allocations)
    validate_assignment_transition(plan, allocation_candidate)
    updated_items = plan.work_items
    direct = tuple(
        entry for entry in changed_allocations if entry.work_item_id == allocation.work_item_id
    )
    if item.kind != WorkItemType.EPIC and not plan.children(item.id) and len(direct) == 1:
        updated_item = replace(item, assignee_id=allocation.person_id)
        updated_items = tuple(
            updated_item if current.id == item.id else current for current in plan.work_items
        )
    candidate = replace(
        plan,
        work_items=updated_items,
        allocations=changed_allocations,
    )
    return candidate


def remove_allocation(plan: ProgramPlan, allocation_id: UUID) -> ProgramPlan:
    allocation_by_id(plan, allocation_id)
    candidate = replace(
        plan, allocations=tuple(a for a in plan.allocations if a.id != allocation_id)
    )
    validate_assignment_transition(plan, candidate)
    return candidate
