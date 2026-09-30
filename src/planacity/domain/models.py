"""Immutable canonical entities for a manually structured Program Plan."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from planacity.domain.availability import AvailabilityEvent
from planacity.domain.horizon import PlanningHorizon as PlanningHorizon
from planacity.domain.work_calendar import PersonCalendar, WorkCalendar


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must contain a non-blank name.")


def _require_id(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise ValueError(f"{field_name} must be a UUID.")


class WorkItemType(StrEnum):
    EPIC = "epic"
    TASK = "task"
    SUBTASK = "subtask"


@dataclass(frozen=True, kw_only=True)
class Person:
    """A roster entry; work allocation is a separate future concept."""

    name: str
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_id(self.id, "Person ID")
        _require_text(self.name, "Person name")


@dataclass(frozen=True, kw_only=True)
class WorkGroup:
    """Organize Epics independently from their parent/child hierarchy."""

    name: str
    id: UUID = field(default_factory=uuid4)
    epic_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        _require_id(self.id, "WorkGroup ID")
        _require_text(self.name, "WorkGroup name")
        if not isinstance(self.epic_ids, tuple):
            raise ValueError("WorkGroup epic_ids must be a tuple of UUIDs.")
        for epic_id in self.epic_ids:
            _require_id(epic_id, "WorkGroup Epic ID")
        if len(set(self.epic_ids)) != len(self.epic_ids):
            raise ValueError("WorkGroup Epic IDs must be unique within the group.")


class RelationshipType(StrEnum):
    RELATED_TO = "related_to"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"


@dataclass(frozen=True, kw_only=True)
class Relationship:
    """An explicit link; depends_on points from dependent to prerequisite."""

    source_id: UUID
    target_id: UUID
    kind: RelationshipType
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        for label, value in (
            ("ID", self.id),
            ("source", self.source_id),
            ("target", self.target_id),
        ):
            _require_id(value, f"Relationship {label}")
        if not isinstance(self.kind, RelationshipType):
            raise ValueError("Relationship kind must be related_to, depends_on, or blocks.")
        if self.source_id == self.target_id:
            raise ValueError("A relationship cannot link a work item to itself.")


@dataclass(frozen=True, kw_only=True)
class WorkItem:
    """A named unit of work; parent references are validated within a ProgramPlan."""

    title: str
    kind: WorkItemType
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    estimate_hours: Decimal | None = None
    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        _require_id(self.id, "Work item ID")
        _require_text(self.title, "Work item title")
        if not isinstance(self.kind, WorkItemType):
            raise ValueError("Work item kind must be Epic, Task, or Subtask.")
        if self.parent_id is not None:
            _require_id(self.parent_id, "Parent ID")
            if self.parent_id == self.id:
                raise ValueError(f"Work item '{self.title}' cannot be its own parent.")
        if self.estimate_hours is not None:
            if not isinstance(self.estimate_hours, Decimal):
                raise ValueError("Estimate must be a Decimal number of hours or None (unknown).")
            if not self.estimate_hours.is_finite() or self.estimate_hours < 0:
                raise ValueError("Estimate must be finite and non-negative.")
        for label, value in (("start", self.start), ("end", self.end)):
            if value is not None and type(value) is not date:
                raise ValueError(f"Work item {label} must be a date without a time or None.")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("Work item end must be on or after its start.")


@dataclass(frozen=True, kw_only=True)
class ImportedWork:
    """Original work and external identity, independent of subsequent local edits."""

    item: WorkItem
    external_reference: str
    external_person: str = ""
    person: Person | None = None
    status: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.item, WorkItem):
            raise ValueError("Imported work requires a valid work item.")
        _require_text(self.external_reference, "External reference")
        if not isinstance(self.external_person, str) or not isinstance(self.status, str):
            raise ValueError("External person and status must be text.")
        if self.person is not None and not isinstance(self.person, Person):
            raise ValueError("Imported person must be a Person snapshot.")


@dataclass(frozen=True, kw_only=True)
class ImportSnapshot:
    """A local source baseline; raw cells include fields not represented in the plan."""

    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    records: tuple[ImportedWork, ...]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_id(self.id, "Import snapshot ID")
        _require_text(self.name, "Import source name")
        if (
            not isinstance(self.headers, tuple)
            or not self.headers
            or any(not isinstance(cell, str) for cell in self.headers)
        ):
            raise ValueError("Source headers must be a nonempty tuple of text.")
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, tuple)
            or len(row) != len(self.headers)
            or any(not isinstance(cell, str) for cell in row)
            for row in self.rows
        ):
            raise ValueError("Source rows must match the headers and contain text.")
        if (
            not isinstance(self.records, tuple)
            or any(not isinstance(record, ImportedWork) for record in self.records)
            or len(self.records) != len(self.rows)
        ):
            raise ValueError("Every source row requires an imported work record.")
        if len({r.external_reference for r in self.records}) != len(self.records):
            raise ValueError("External references must be unique in a source.")
        _validate_hierarchy(tuple(r.item for r in self.records))


@dataclass(frozen=True, kw_only=True)
class ProgramPlan:
    """A validated plan snapshot whose work-item order defines sibling order."""

    name: str
    horizon: PlanningHorizon
    description: str = ""
    id: UUID = field(default_factory=uuid4)
    work_items: tuple[WorkItem, ...] = ()
    people: tuple[Person, ...] = ()
    work_groups: tuple[WorkGroup, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    imports: tuple[ImportSnapshot, ...] = ()
    work_calendars: tuple[WorkCalendar, ...] = ()
    person_calendars: tuple[PersonCalendar, ...] = ()
    availability_events: tuple[AvailabilityEvent, ...] = ()

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
        if not isinstance(self.people, tuple) or any(
            not isinstance(person, Person) for person in self.people
        ):
            raise ValueError("Program Plan people must be a tuple of Person objects.")
        if len({person.id for person in self.people}) != len(self.people):
            raise ValueError("Person IDs must be unique within a plan.")
        _validate_groups_and_relationships(self)
        if not isinstance(self.work_calendars, tuple) or any(
            not isinstance(calendar, WorkCalendar) for calendar in self.work_calendars
        ):
            raise ValueError("Work calendars must be a tuple of WorkCalendar objects.")
        if len({calendar.id for calendar in self.work_calendars}) != len(self.work_calendars):
            raise ValueError("WorkCalendar IDs must be unique within a plan.")
        if not isinstance(self.person_calendars, tuple) or any(
            not isinstance(assignment, PersonCalendar) for assignment in self.person_calendars
        ):
            raise ValueError("Person calendars must be a tuple of PersonCalendar objects.")
        if len({assignment.person_id for assignment in self.person_calendars}) != len(
            self.person_calendars
        ):
            raise ValueError("Each person can have only one work calendar.")
        for assignment in self.person_calendars:
            self.person(assignment.person_id)
            self.work_calendar(assignment.calendar_id)
        if not isinstance(self.availability_events, tuple) or any(
            not isinstance(event, AvailabilityEvent) for event in self.availability_events
        ):
            raise ValueError("Availability events must be a tuple of AvailabilityEvent objects.")
        if len({event.id for event in self.availability_events}) != len(self.availability_events):
            raise ValueError("Availability event IDs must be unique within a plan.")
        for event in self.availability_events:
            self.person(event.person_id)
        if not isinstance(self.imports, tuple) or any(
            not isinstance(source, ImportSnapshot) for source in self.imports
        ):
            raise ValueError("Imports must be a tuple of ImportSnapshot objects.")
        if len({source.id for source in self.imports}) != len(self.imports):
            raise ValueError("Import snapshot IDs must be unique.")
        records = tuple(record for source in self.imports for record in source.records)
        if len({r.item.id for r in records}) != len(records):
            raise ValueError("A work item cannot belong to multiple import baselines.")
        if len({r.external_reference for r in records}) != len(records):
            raise ValueError(
                "External references already imported; reconciliation is not supported."
            )

    def work_group(self, group_id: UUID) -> WorkGroup:
        for group in self.work_groups:
            if group.id == group_id:
                return group
        raise ValueError(f"WorkGroup {group_id} does not exist in this plan.")

    def work_calendar(self, calendar_id: UUID) -> WorkCalendar:
        for calendar in self.work_calendars:
            if calendar.id == calendar_id:
                return calendar
        raise ValueError(f"WorkCalendar {calendar_id} does not exist in this plan.")

    def person(self, person_id: UUID) -> Person:
        for person in self.people:
            if person.id == person_id:
                return person
        raise ValueError(f"Person {person_id} does not exist in this plan.")

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


def _validate_groups_and_relationships(plan: ProgramPlan) -> None:
    by_id = {item.id: item for item in plan.work_items}
    if not isinstance(plan.work_groups, tuple) or any(
        not isinstance(group, WorkGroup) for group in plan.work_groups
    ):
        raise ValueError("Program Plan work_groups must be a tuple of WorkGroup objects.")
    if len({group.id for group in plan.work_groups}) != len(plan.work_groups):
        raise ValueError("WorkGroup IDs must be unique within a plan.")
    for group in plan.work_groups:
        for epic_id in group.epic_ids:
            if epic_id not in by_id or by_id[epic_id].kind != WorkItemType.EPIC:
                raise ValueError(f"WorkGroup '{group.name}' must reference existing Epics only.")
    if not isinstance(plan.relationships, tuple) or any(
        not isinstance(link, Relationship) for link in plan.relationships
    ):
        raise ValueError("Program Plan relationships must be a tuple of Relationship objects.")
    if len({link.id for link in plan.relationships}) != len(plan.relationships):
        raise ValueError("Relationship IDs must be unique within a plan.")
    seen: set[tuple[str, UUID, UUID]] = set()
    for link in plan.relationships:
        if link.source_id not in by_id or link.target_id not in by_id:
            raise ValueError("Relationship endpoints must reference existing work items.")
        source, target = link.source_id, link.target_id
        if link.kind == RelationshipType.RELATED_TO:
            source, target = sorted((source, target))
            key = ("related", source, target)
        else:
            if link.kind == RelationshipType.BLOCKS:
                source, target = target, source
            key = ("dependency", source, target)
        if key in seen:
            raise ValueError("Duplicate relationship: these items already have the same link.")
        seen.add(key)


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
