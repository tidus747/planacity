"""Validate explicit allocations and summarize hours without modifying the plan."""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from uuid import UUID

from planacity.domain import ProgramPlan
from planacity.domain.allocation import Allocation, validate_allocation_references


@dataclass(frozen=True)
class WorkAllocationSummary:
    work_item_id: UUID
    entered_estimate_hours: Decimal | None
    known_estimate_hours: Decimal
    missing_estimate_count: int
    leaf_count: int
    is_container: bool
    direct_allocation_count: int
    descendant_allocation_count: int
    direct_allocated_hours: Decimal
    descendant_allocated_hours: Decimal
    allocated_hours: Decimal
    remaining_hours: Decimal | None

    @property
    def missing_estimate(self) -> bool:
        return self.missing_estimate_count > 0

    @property
    def estimate_hours(self) -> Decimal | None:
        """Return the complete effective estimate, or None when a leaf is unknown."""
        return None if self.missing_estimate else self.known_estimate_hours

    @property
    def has_direct_container_allocations(self) -> bool:
        return self.is_container and self.direct_allocation_count > 0

    @property
    def mixed_level_effort(self) -> bool:
        return self.has_direct_container_allocations and self.descendant_allocation_count > 0

    @property
    def incomplete(self) -> bool:
        return self.missing_estimate or self.has_direct_container_allocations

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
    validate_allocation_references(
        allocations, {item.id for item in plan.work_items}, {person.id for person in plan.people}
    )


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
    """Return exact leaf-effort and allocation rollups in canonical order.

    Stored container estimates remain entered reference values. Effective estimates
    sum descendant leaves once, while allocation IDs are likewise counted once per
    subtree. No date distribution or capacity assessment is implied.
    """
    validate_allocations(plan, allocations)
    by_work: dict[UUID, list[Allocation]] = {item.id: [] for item in plan.work_items}
    by_person: dict[UUID, list[Decimal]] = {person.id: [] for person in plan.people}
    for allocation in allocations:
        by_work[allocation.work_item_id].append(allocation)
        by_person[allocation.person_id].append(allocation.hours)

    summaries: dict[UUID, WorkAllocationSummary] = {}

    def summarize(item_id: UUID) -> WorkAllocationSummary:
        existing = summaries.get(item_id)
        if existing is not None:
            return existing
        item = plan.work_item(item_id)
        children = tuple(summarize(child.id) for child in plan.children(item_id))
        direct_entries = tuple(by_work[item_id])
        direct = _sum_hours(tuple(allocation.hours for allocation in direct_entries))
        descendant = _sum_hours(tuple(child.allocated_hours for child in children))
        allocated = _sum_hours((direct, descendant))
        if children:
            known = _sum_hours(tuple(child.known_estimate_hours for child in children))
            missing = sum(child.missing_estimate_count for child in children)
            leaves = sum(child.leaf_count for child in children)
        else:
            known = item.estimate_hours if item.estimate_hours is not None else Decimal(0)
            missing = int(item.estimate_hours is None)
            leaves = 1
        direct_count = len(direct_entries)
        descendant_count = sum(
            child.direct_allocation_count + child.descendant_allocation_count for child in children
        )
        incomplete = missing > 0 or (bool(children) and direct_count > 0)
        remaining = None if incomplete else _sum_hours((known, allocated.copy_negate()))
        result = WorkAllocationSummary(
            work_item_id=item.id,
            entered_estimate_hours=item.estimate_hours,
            known_estimate_hours=known,
            missing_estimate_count=missing,
            leaf_count=leaves,
            is_container=bool(children),
            direct_allocation_count=direct_count,
            descendant_allocation_count=descendant_count,
            direct_allocated_hours=direct,
            descendant_allocated_hours=descendant,
            allocated_hours=allocated,
            remaining_hours=remaining,
        )
        summaries[item_id] = result
        return result

    work = tuple(summarize(item.id) for item in plan.work_items)
    return AllocationSummary(
        work=work,
        people=tuple(
            PersonAllocationSummary(person.id, _sum_hours(tuple(by_person[person.id])))
            for person in plan.people
        ),
    )
