"""Privacy-minimal, date-based reductions to a person's nominal availability."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID, uuid4

from planacity.domain.models import PlanningHorizon


@dataclass(frozen=True, kw_only=True)
class AvailabilityEvent:
    """An unavailable share on every date of an inclusive period.

    1 means fully unavailable; 0.5 means half of that date's calendar hours.
    No absence reason, time of day, or implicit workday length is recorded.
    Overlapping events describe availability limits, not additive duties.
    """

    person_id: UUID
    period: PlanningHorizon
    unavailable_fraction: Decimal
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.person_id, UUID):
            raise ValueError("Availability event and person IDs must be UUIDs.")
        if not isinstance(self.period, PlanningHorizon):
            raise ValueError("Availability period must be a PlanningHorizon.")
        fraction = self.unavailable_fraction
        if not isinstance(fraction, Decimal) or not fraction.is_finite() or not 0 <= fraction <= 1:
            raise ValueError("Unavailable fraction must be a finite Decimal between 0 and 1.")
