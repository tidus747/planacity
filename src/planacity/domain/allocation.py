"""Explicit planned effort shared between work and people, independent of ownership."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4


@dataclass(frozen=True, kw_only=True)
class Allocation:
    work_item_id: UUID
    person_id: UUID
    hours: Decimal
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        for name, value in (
            ("ID", self.id),
            ("work item", self.work_item_id),
            ("person", self.person_id),
        ):
            if not isinstance(value, UUID):
                raise ValueError(f"Allocation {name} must be a UUID.")
        if not isinstance(self.hours, Decimal) or not self.hours.is_finite() or self.hours < 0:
            raise ValueError("Allocation hours must be a finite, non-negative Decimal.")


def validate_allocation_references(
    allocations: tuple[Allocation, ...], work: set[UUID], people: set[UUID]
) -> None:
    """Validate a complete candidate set against canonical reference IDs."""
    if not isinstance(allocations, tuple) or any(
        not isinstance(a, Allocation) for a in allocations
    ):
        raise ValueError("Allocations must be a tuple of Allocation objects.")
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
