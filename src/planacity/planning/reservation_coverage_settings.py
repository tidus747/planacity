"""Reservation coverage lifecycle preserves explicit links and unrelated plan data."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import ProgramPlan, ReservationCoverage


def reservation_coverage(plan: ProgramPlan, coverage_id: UUID) -> ReservationCoverage:
    for coverage in plan.reservation_coverages:
        if coverage.id == coverage_id:
            return coverage
    raise ValueError("Reservation coverage does not exist in this plan.")


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
