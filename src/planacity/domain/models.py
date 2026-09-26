"""Immutable canonical entities for a manually structured Program Plan."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from uuid import UUID, uuid4


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must contain a non-blank name.")


def _require_id(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise ValueError(f"{field_name} must be a UUID.")


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


class WorkItemType(StrEnum):
    EPIC = "epic"
    TASK = "task"
    SUBTASK = "subtask"


@dataclass(frozen=True, kw_only=True)
class WorkItem:
    """A named unit of work; parent references are validated within a ProgramPlan."""

    title: str
    kind: WorkItemType
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_id(self.id, "Work item ID")
        _require_text(self.title, "Work item title")
        if not isinstance(self.kind, WorkItemType):
            raise ValueError("Work item kind must be Epic, Task, or Subtask.")
        if self.parent_id is not None:
            _require_id(self.parent_id, "Parent ID")
            if self.parent_id == self.id:
                raise ValueError(f"Work item '{self.title}' cannot be its own parent.")


@dataclass(frozen=True, kw_only=True)
class ProgramPlan:
    """A validated plan snapshot whose work-item order defines sibling order."""

    name: str
    horizon: PlanningHorizon
    description: str = ""
    id: UUID = field(default_factory=uuid4)
    work_items: tuple[WorkItem, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.id, "Program Plan ID")
        _require_text(self.name, "Program Plan name")
        if not isinstance(self.description, str):
            raise ValueError("Program Plan description must be text.")
        if not isinstance(self.horizon, PlanningHorizon):
            raise ValueError("Program Plan requires a valid PlanningHorizon.")
        if not isinstance(self.work_items, tuple) or any(
            not isinstance(item, WorkItem) for item in self.work_items
        ):
            raise ValueError("Program Plan work_items must be a tuple of WorkItem objects.")
        _validate_hierarchy(self.work_items)

    def work_item(self, item_id: UUID) -> WorkItem:
        """Find a work item or identify the unresolved reference."""
        for item in self.work_items:
            if item.id == item_id:
                return item
        raise ValueError(f"Work item {item_id} does not exist in this plan.")

    def children(self, parent_id: UUID | None = None) -> tuple[WorkItem, ...]:
        """Return direct children in order; None selects the root items."""
        if parent_id is not None:
            self.work_item(parent_id)
        return tuple(item for item in self.work_items if item.parent_id == parent_id)


def _validate_hierarchy(items: tuple[WorkItem, ...]) -> None:
    """Validate the whole aggregate, including data constructed by a file loader."""
    by_id: dict[UUID, WorkItem] = {}
    for item in items:
        if item.id in by_id:
            raise ValueError(
                f"Work item ID {item.id} is duplicated. Use a unique ID for each item."
            )
        by_id[item.id] = item
    for item in items:
        if item.parent_id is not None and item.parent_id not in by_id:
            raise ValueError(
                f"Parent {item.parent_id} of '{item.title}' does not exist in this plan."
            )

    # Detect cycles before checking parent types so malformed imports get a clear error.
    completed: set[UUID] = set()
    for item in items:
        path: set[UUID] = set()
        current: UUID | None = item.id
        while current is not None and current not in completed:
            if current in path:
                raise ValueError(f"Hierarchy contains a cycle at '{by_id[current].title}'.")
            path.add(current)
            current = by_id[current].parent_id
        completed.update(path)

    for item in items:
        parent = by_id.get(item.parent_id) if item.parent_id is not None else None
        if item.kind == WorkItemType.EPIC and parent is not None:
            raise ValueError(f"Epic '{item.title}' must be at the root of the plan.")
        if item.kind == WorkItemType.TASK and parent is not None:
            if parent.kind != WorkItemType.EPIC:
                raise ValueError(f"Task '{item.title}' requires an Epic parent or no parent.")
        if item.kind == WorkItemType.SUBTASK:
            if parent is None or parent.kind != WorkItemType.TASK:
                raise ValueError(f"Subtask '{item.title}' requires a Task parent.")
