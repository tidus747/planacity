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
