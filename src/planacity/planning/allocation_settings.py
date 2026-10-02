"""Allocation lifecycle preserves identities, order, and unrelated plan data."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan


def allocation_by_id(plan: ProgramPlan, allocation_id: UUID) -> Allocation:
    for allocation in plan.allocations:
        if allocation.id == allocation_id:
            return allocation
    raise ValueError("Allocation does not exist in this plan.")


def add_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    return replace(plan, allocations=(*plan.allocations, allocation))


def update_allocation(plan: ProgramPlan, allocation: Allocation) -> ProgramPlan:
    allocation_by_id(plan, allocation.id)
    return replace(
        plan,
        allocations=tuple(
            allocation if current.id == allocation.id else current for current in plan.allocations
        ),
    )


def remove_allocation(plan: ProgramPlan, allocation_id: UUID) -> ProgramPlan:
    allocation_by_id(plan, allocation_id)
    return replace(plan, allocations=tuple(a for a in plan.allocations if a.id != allocation_id))
