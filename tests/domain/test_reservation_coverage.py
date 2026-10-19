"""Canonical reservation-coverage links before persistence and capacity integration."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    PlanningHorizon,
    ReservationCoverage,
    ReservationRule,
    validate_reservation_coverage_references,
)


def candidates(hours: str = "8") -> tuple[Allocation, ReservationRule, ReservationCoverage]:
    person_id = uuid4()
    allocation = Allocation(
        work_item_id=uuid4(),
        person_id=person_id,
        hours=Decimal(hours),
    )
    rule = ReservationRule(
        name="Front Office",
        person_ids=(person_id,),
        hours_per_person=Decimal("8"),
        anchor=date(2026, 1, 5),
        interval_weeks=1,
        effective=PlanningHorizon(date(2026, 1, 1), date(2026, 3, 31)),
    )
    return (
        allocation,
        rule,
        ReservationCoverage(allocation_id=allocation.id, reservation_rule_id=rule.id),
    )


def test_valid_link_is_immutable_accepts_zero_hours_and_does_not_mutate_inputs() -> None:
    allocation, rule, coverage = candidates("0")
    before = (repr(allocation), repr(rule), repr(coverage))

    validate_reservation_coverage_references((coverage,), (allocation,), (rule,))

    assert (repr(allocation), repr(rule), repr(coverage)) == before
    with pytest.raises(FrozenInstanceError):
        coverage.allocation_id = uuid4()


@pytest.mark.parametrize("field", ("id", "allocation_id", "reservation_rule_id"))
def test_link_requires_uuid_fields(field: str) -> None:
    _, _, coverage = candidates()

    with pytest.raises(ValueError, match="must be a UUID"):
        replace(coverage, **{field: "not-a-uuid"})


@pytest.mark.parametrize(
    ("coverages", "allocations", "rules", "message"),
    (
        ([], (), (), "Reservation coverages must be a tuple"),
        (("coverage",), (), (), "Reservation coverages must be a tuple"),
        ((), [], (), "Coverage allocations must be a tuple"),
        ((), ("allocation",), (), "Coverage allocations must be a tuple"),
        ((), (), [], "Coverage rules must be a tuple"),
        ((), (), ("rule",), "Coverage rules must be a tuple"),
    ),
)
def test_validator_requires_typed_tuples(coverages, allocations, rules, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_reservation_coverage_references(coverages, allocations, rules)


def test_validation_is_independent_of_candidate_order() -> None:
    first_allocation, first_rule, first = candidates()
    second_allocation, second_rule, second = candidates()

    validate_reservation_coverage_references(
        (second, first),
        (first_allocation, second_allocation),
        (second_rule, first_rule),
    )
    validate_reservation_coverage_references(
        (first, second),
        (second_allocation, first_allocation),
        (first_rule, second_rule),
    )


def test_duplicate_coverage_ids_and_allocation_links_are_rejected() -> None:
    allocation, rule, coverage = candidates()
    other_rule = replace(rule, id=uuid4(), name="Meetings")

    with pytest.raises(ValueError, match="Duplicate reservation coverage ID"):
        validate_reservation_coverage_references(
            (coverage, replace(coverage, reservation_rule_id=other_rule.id)),
            (allocation,),
            (rule, other_rule),
        )
    with pytest.raises(ValueError, match="already has a covering reservation"):
        validate_reservation_coverage_references(
            (coverage, replace(coverage, id=uuid4(), reservation_rule_id=other_rule.id)),
            (allocation,),
            (rule, other_rule),
        )


def test_unknown_allocation_and_rule_references_are_rejected() -> None:
    allocation, rule, coverage = candidates()

    with pytest.raises(ValueError, match="unknown allocation"):
        validate_reservation_coverage_references((coverage,), (), (rule,))
    with pytest.raises(ValueError, match="unknown reservation rule"):
        validate_reservation_coverage_references((coverage,), (allocation,), ())


def test_rule_must_include_the_allocated_person() -> None:
    allocation, rule, coverage = candidates()
    incompatible = replace(rule, person_ids=(uuid4(),))

    with pytest.raises(ValueError, match="does not include the allocated person"):
        validate_reservation_coverage_references((coverage,), (allocation,), (incompatible,))


def test_candidate_allocation_and_rule_ids_must_be_unique() -> None:
    allocation, rule, coverage = candidates()

    with pytest.raises(ValueError, match="allocation IDs must be unique"):
        validate_reservation_coverage_references(
            (coverage,),
            (allocation, replace(allocation)),
            (rule,),
        )
    with pytest.raises(ValueError, match="rule IDs must be unique"):
        validate_reservation_coverage_references(
            (coverage,),
            (allocation,),
            (rule, replace(rule)),
        )
