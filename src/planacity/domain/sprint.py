"""Canonical sprint inputs, independent of Jira boards and calendar UI."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from planacity.domain.horizon import PlanningHorizon


@dataclass(frozen=True, kw_only=True)
class Sprint:
    name: str
    period: PlanningHorizon
    id: UUID = field(default_factory=uuid4)
    external_reference: str | None = None
    work_group_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise ValueError("Sprint ID must be a UUID.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Sprint name must contain non-blank text.")
        if not isinstance(self.period, PlanningHorizon):
            raise ValueError("Sprint requires a valid inclusive period.")
        if self.external_reference is not None and (
            not isinstance(self.external_reference, str) or not self.external_reference.strip()
        ):
            raise ValueError("Sprint external reference must be non-blank text or None.")
        if self.work_group_id is not None and not isinstance(self.work_group_id, UUID):
            raise ValueError("Sprint WorkGroup ID must be a UUID or None.")


@dataclass(frozen=True, kw_only=True)
class SprintAssignment:
    sprint_id: UUID
    work_item_id: UUID
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.id, "Sprint assignment ID"),
            (self.sprint_id, "Sprint assignment sprint ID"),
            (self.work_item_id, "Sprint assignment work item ID"),
        ):
            if not isinstance(value, UUID):
                raise ValueError(f"{field_name} must be a UUID.")
