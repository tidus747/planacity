"""Validate explicit allocations and summarize hours without modifying the plan."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.domain.allocation import Allocation


@dataclass(frozen=True)
class WorkAllocationSummary:
    work_item_id: UUID
    estimate_hours: Decimal | None
    allocated_hours: Decimal
    remaining_hours: Decimal | None

    @property
    def missing_estimate(self) -> bool:
        return self.estimate_hours is None

    @property
    def unassigned(self) -> bool:
        return self.allocated_hours == 0


@dataclass(frozen=True)
class PersonAllocationSummary:
    person_id: UUID
    allocated_hours: Decimal


@dataclass(frozen=True)
class AllocationSummary:
    work: tuple[WorkAllocationSummary, ...]
    people: tuple[PersonAllocationSummary, ...]


def validate_allocations(plan: ProgramPlan, allocations: tuple[Allocation, ...]) -> None:
    """Validate the whole candidate set; one allocation per work/person pair.

    Zero hours is explicit but does not count as positively allocated work.
    Estimates need not be known or fully covered: discrepancies are findings,
    not invalid references, and are never repaired by changing the user's hours.
    """
    if not isinstance(allocations, tuple) or any(
        not isinstance(a, Allocation) for a in allocations
    ):
        raise ValueError("Allocations must be a tuple of Allocation objects.")
    people = {person.id for person in plan.people}
    work = {item.id for item in plan.work_items}
    ids: set[UUID] = set()
    pairs: set[tuple[UUID, UUID]] = set()
    for allocation in allocations:
        if allocation.id in ids:
            raise ValueError(f"Duplicate allocation ID: {allocation.id}.")
        ids.add(allocation.id)
        if allocation.work_item_id not in work:
            raise ValueError(f"Allocation {allocation.id} references an unknown work item.")
        if allocation.person_id not in people:
            raise ValueError(f"Allocation {allocation.id} references an unknown person.")
        pair = (allocation.work_item_id, allocation.person_id)
        if pair in pairs:
            raise ValueError(
                "More than one allocation references the same work/person pair. "
                "Edit the existing allocation instead."
            )
        pairs.add(pair)


def _sum_hours(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        return Decimal(0)
    places = max(0, *(-int(value.as_tuple().exponent) for value in values))
    integer_digits = max(1, *(value.adjusted() + 1 for value in values))
    with localcontext() as context:
        context.prec = max(28, integer_digits + places + len(str(len(values))) + 1)
        return sum(values, Decimal(0))


def summarize_allocations(
    plan: ProgramPlan, allocations: tuple[Allocation, ...]
) -> AllocationSummary:
    """Return canonical work/roster order with exact totals and signed remainders.

    Parent and child work remain independent; neither estimates nor allocations
    roll up or inherit. No date distribution, horizon clipping, availability, or
    capacity overload assessment is implied by these whole-work effort totals.
    """
    validate_allocations(plan, allocations)
    by_work: dict[UUID, list[Decimal]] = {item.id: [] for item in plan.work_items}
    by_person: dict[UUID, list[Decimal]] = {person.id: [] for person in plan.people}
    for allocation in allocations:
        by_work[allocation.work_item_id].append(allocation.hours)
        by_person[allocation.person_id].append(allocation.hours)
    work = []
    for item in plan.work_items:
        allocated = _sum_hours(tuple(by_work[item.id]))
        remaining = (
            None
            if item.estimate_hours is None
            else _sum_hours((item.estimate_hours, allocated.copy_negate()))
        )
        work.append(WorkAllocationSummary(item.id, item.estimate_hours, allocated, remaining))
    return AllocationSummary(
        work=tuple(work),
        people=tuple(
            PersonAllocationSummary(person.id, _sum_hours(tuple(by_person[person.id])))
            for person in plan.people
        ),
    )
