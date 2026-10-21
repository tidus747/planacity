"""Reservation coverage lifecycle preserves explicit links and unrelated plan data."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from planacity.domain import Allocation, ProgramPlan, ReservationCoverage
from planacity.planning.allocation_settings import update_allocation
from planacity.planning.assignees import set_work_assignment


def reservation_coverage(plan: ProgramPlan, coverage_id: UUID) -> ReservationCoverage:
    for coverage in plan.reservation_coverages:
        if coverage.id == coverage_id:
            return coverage
    raise ValueError("Reservation coverage does not exist in this plan.")


def coverage_for_allocation(plan: ProgramPlan, allocation_id: UUID) -> ReservationCoverage | None:
    """Return the allocation's unique explicit coverage link, if present."""
    return next(
        (
            coverage
            for coverage in plan.reservation_coverages
            if coverage.allocation_id == allocation_id
        ),
        None,
    )


def add_reservation_coverage(plan: ProgramPlan, coverage: ReservationCoverage) -> ProgramPlan:
    return replace(
        plan,
        reservation_coverages=(*plan.reservation_coverages, coverage),
    )


def update_reservation_coverage(plan: ProgramPlan, coverage: ReservationCoverage) -> ProgramPlan:
    reservation_coverage(plan, coverage.id)
    return replace(
        plan,
        reservation_coverages=tuple(
            coverage if current.id == coverage.id else current
            for current in plan.reservation_coverages
        ),
    )


def remove_reservation_coverage(plan: ProgramPlan, coverage_id: UUID) -> ProgramPlan:
    reservation_coverage(plan, coverage_id)
    return replace(
        plan,
        reservation_coverages=tuple(
            coverage for coverage in plan.reservation_coverages if coverage.id != coverage_id
        ),
    )


def _without_allocation_coverage(
    plan: ProgramPlan, allocation_id: UUID
) -> tuple[ProgramPlan, ReservationCoverage | None]:
    existing = coverage_for_allocation(plan, allocation_id)
    if existing is None:
        return plan, None
    return (
        replace(
            plan,
            reservation_coverages=tuple(
                coverage for coverage in plan.reservation_coverages if coverage.id != existing.id
            ),
        ),
        existing,
    )


def update_allocation_coverage(
    plan: ProgramPlan,
    allocation: Allocation,
    reservation_rule_id: UUID | None,
) -> ProgramPlan:
    """Atomically edit one Allocation and its optional explicit coverage."""
    candidate, existing = _without_allocation_coverage(plan, allocation.id)
    candidate = update_allocation(candidate, allocation)
    if reservation_rule_id is None:
        return candidate
    if existing is None:
        coverage = ReservationCoverage(
            allocation_id=allocation.id,
            reservation_rule_id=reservation_rule_id,
        )
    else:
        coverage = ReservationCoverage(
            allocation_id=allocation.id,
            reservation_rule_id=reservation_rule_id,
            id=existing.id,
        )
    return replace(candidate, reservation_coverages=(*candidate.reservation_coverages, coverage))


def set_work_assignment_coverage(
    plan: ProgramPlan,
    work_item_id: UUID,
    person_id: UUID | None,
    hours: Decimal | None,
    reservation_rule_id: UUID | None,
) -> ProgramPlan:
    """Atomically set one compact assignment and its optional coverage link."""
    direct = tuple(
        allocation for allocation in plan.allocations if allocation.work_item_id == work_item_id
    )
    existing_allocation = direct[0] if direct else None
    existing_coverage = (
        coverage_for_allocation(plan, existing_allocation.id)
        if existing_allocation is not None
        else None
    )
    candidate = plan
    if existing_coverage is not None:
        candidate = replace(
            plan,
            reservation_coverages=tuple(
                coverage
                for coverage in plan.reservation_coverages
                if coverage.id != existing_coverage.id
            ),
        )
    candidate = set_work_assignment(candidate, work_item_id, person_id, hours)
    if reservation_rule_id is None:
        return candidate
    assigned = tuple(
        allocation
        for allocation in candidate.allocations
        if allocation.work_item_id == work_item_id
    )
    if len(assigned) != 1:
        raise ValueError(
            "Choose an assignee and explicit allocated hours before selecting reservation coverage."
        )
    if existing_coverage is None:
        coverage = ReservationCoverage(
            allocation_id=assigned[0].id,
            reservation_rule_id=reservation_rule_id,
        )
    else:
        coverage = ReservationCoverage(
            allocation_id=assigned[0].id,
            reservation_rule_id=reservation_rule_id,
            id=existing_coverage.id,
        )
    return replace(candidate, reservation_coverages=(*candidate.reservation_coverages, coverage))
