"""Allocation lifecycle preserves identities, order, and unrelated plan data."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan
from planacity.planning.assignment_policy import validate_assignment_transition


def allocation_by_id(plan: ProgramPlan, allocation_id: UUID) -> Allocation:
    for allocation in plan.allocations:
        if allocation.id == allocation_id:
            return allocation
    raise ValueError("Allocation does not exist in this plan.")


def add_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    if plan.children(allocation.work_item_id):
        raise ValueError(
            "Allocate effort to leaf work. Container totals are derived from their children."
        )
    candidate = replace(plan, allocations=(*plan.allocations, allocation))
    validate_assignment_transition(plan, candidate)
    return candidate


def update_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    original = allocation_by_id(plan, allocation.id)
    if allocation.work_item_id != original.work_item_id and plan.children(allocation.work_item_id):
        raise ValueError(
            "Allocate effort to leaf work. Container totals are derived from their children."
        )
    candidate = replace(
        plan,
        allocations=tuple(
            allocation if current.id == allocation.id else current for current in plan.allocations
        ),
    )
    validate_assignment_transition(plan, candidate)
    return candidate


def remove_allocation(plan: ProgramPlan, allocation_id: UUID) -> ProgramPlan:
    allocation_by_id(plan, allocation_id)
    candidate = replace(
        plan, allocations=tuple(a for a in plan.allocations if a.id != allocation_id)
    )
    validate_assignment_transition(plan, candidate)
    return candidate
