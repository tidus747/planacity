"""Explicit links between planned allocations and protected reservation capacity."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from planacity.domain.allocation import Allocation
from planacity.domain.reservations import ReservationRule


@dataclass(frozen=True, kw_only=True)
class ReservationCoverage:
    """State that one allocation is intended to use one reservation rule."""

    allocation_id: UUID
    reservation_rule_id: UUID
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        for name, value in (
            ("ID", self.id),
            ("allocation", self.allocation_id),
            ("reservation rule", self.reservation_rule_id),
        ):
            if not isinstance(value, UUID):
                raise ValueError(f"Reservation coverage {name} must be a UUID.")


def validate_reservation_coverage_references(
    coverages: tuple[ReservationCoverage, ...],
    allocations: tuple[Allocation, ...],
    reservation_rules: tuple[ReservationRule, ...],
) -> None:
    """Validate a complete candidate set without inferring or changing links."""
    if not isinstance(coverages, tuple) or any(
        not isinstance(coverage, ReservationCoverage) for coverage in coverages
    ):
        raise ValueError("Reservation coverages must be a tuple of ReservationCoverage objects.")
    if not isinstance(allocations, tuple) or any(
        not isinstance(allocation, Allocation) for allocation in allocations
    ):
        raise ValueError("Coverage allocations must be a tuple of Allocation objects.")
    if not isinstance(reservation_rules, tuple) or any(
        not isinstance(rule, ReservationRule) for rule in reservation_rules
    ):
        raise ValueError("Coverage rules must be a tuple of ReservationRule objects.")

    allocation_by_id = {allocation.id: allocation for allocation in allocations}
    rule_by_id = {rule.id: rule for rule in reservation_rules}
    if len(allocation_by_id) != len(allocations):
        raise ValueError("Coverage allocation IDs must be unique.")
    if len(rule_by_id) != len(reservation_rules):
        raise ValueError("Coverage reservation rule IDs must be unique.")

    coverage_ids: set[UUID] = set()
    covered_allocations: set[UUID] = set()
    for coverage in coverages:
        if coverage.id in coverage_ids:
            raise ValueError(f"Duplicate reservation coverage ID: {coverage.id}.")
        coverage_ids.add(coverage.id)
        if coverage.allocation_id in covered_allocations:
            raise ValueError(
                f"Allocation {coverage.allocation_id} already has a covering reservation."
            )
        covered_allocations.add(coverage.allocation_id)

        allocation = allocation_by_id.get(coverage.allocation_id)
        if allocation is None:
            raise ValueError(
                f"Reservation coverage {coverage.id} references an unknown allocation."
            )
        rule = rule_by_id.get(coverage.reservation_rule_id)
        if rule is None:
            raise ValueError(
                f"Reservation coverage {coverage.id} references an unknown reservation rule."
            )
        if allocation.person_id not in rule.person_ids:
            raise ValueError(
                f"Reservation coverage {coverage.id} links an allocation to a rule that does "
                "not include the allocated person."
            )
