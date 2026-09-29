"""Inclusive planning dates shared by plans and availability events."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PlanningHorizon:
    """An inclusive date range; times and timezone conversion are not inferred."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if type(self.start) is not date or type(self.end) is not date:
            raise ValueError("Planning horizon start and end must be dates without a time.")
        if self.end < self.start:
            raise ValueError("Planning horizon end must be on or after its start.")
