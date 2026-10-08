"""Explicit CSV mapping and validation, independent of Qt and Jira APIs."""

import csv
import io
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, DecimalException
from uuid import uuid4

from planacity.domain import Person, ProgramPlan, WorkItem, WorkItemType, WorkPriority
from planacity.domain.models import ImportedWork, ImportSnapshot

FIELDS = (
    "title",
    "type",
    "reference",
    "row_id",
    "parent",
    "estimate",
    "start",
    "end",
    "person",
    "status",
    "priority",
)
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d/%b/%y")


@dataclass(frozen=True)
class CsvTable:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Mapping:
    columns: tuple[tuple[str, int], ...]
    estimate_unit: str = "seconds"
    date_format: str = "%Y-%m-%d"
    types: tuple[tuple[str, WorkItemType], ...] = (
        ("Epic", WorkItemType.EPIC),
        ("Task", WorkItemType.TASK),
        ("Sub-task", WorkItemType.SUBTASK),
        ("Subtask", WorkItemType.SUBTASK),
    )
    priorities: tuple[tuple[str, WorkPriority | None], ...] = ()

    def __post_init__(self) -> None:
        names = [name for name, _ in self.columns]
        indices = [index for _, index in self.columns]
        if any(name not in FIELDS for name in names) or len(set(names)) != len(names):
            raise ValueError("Map each supported field at most once.")
        if len(set(indices)) != len(indices) or any(type(i) is not int or i < 0 for i in indices):
            raise ValueError("Map each CSV column to at most one field.")
        if not {"title", "type", "reference"}.issubset(names):
            raise ValueError("Map title, type, and external reference before continuing.")
        if self.estimate_unit not in ("seconds", "hours"):
            raise ValueError("Choose seconds or hours; story points are not hours.")
        if self.date_format not in DATE_FORMATS:
            raise ValueError("Choose a supported date format.")
        if len({name for name, _ in self.types}) != len(self.types) or any(
            not name.strip() or not isinstance(kind, WorkItemType) for name, kind in self.types
        ):
            raise ValueError("Map each external work type exactly once.")
        if len({name for name, _ in self.priorities}) != len(self.priorities) or any(
            not name.strip() or (priority is not None and not isinstance(priority, WorkPriority))
            for name, priority in self.priorities
        ):
            raise ValueError("Map each nonblank external priority at most once.")


def read_csv(text: str, delimiter: str = ",") -> CsvTable:
    if delimiter not in (",", ";", "\t"):
        raise ValueError("Choose comma, semicolon, or tab as the delimiter.")
    reader = csv.reader(
        io.StringIO(text.removeprefix("\ufeff"), newline=""), delimiter=delimiter, strict=True
    )
    try:
        headers = tuple(next(reader, ()))
        if not headers or any(not header.strip() for header in headers):
            raise ValueError("CSV requires nonblank column headers.")
        rows = []
        for row in reader:
            if len(row) != len(headers):
                raise ValueError(
                    f"CSV line {reader.line_num}: expected {len(headers)} cells, "
                    f"found {len(row)}. Check the delimiter and quoting."
                )
            rows.append(tuple(row))
    except csv.Error as error:
        raise ValueError(f"CSV line {reader.line_num}: {error}.") from error
    if not rows:
        raise ValueError("The CSV has no work rows.")
    return CsvTable(headers, tuple(rows))


def validate_columns(table: CsvTable, mapping: Mapping) -> None:
    if any(index >= len(table.headers) for _, index in mapping.columns):
        raise ValueError("A mapped column is missing. Review the field mapping.")


def external_people(table: CsvTable, mapping: Mapping) -> tuple[str, ...]:
    validate_columns(table, mapping)
    index = dict(mapping.columns).get("person")
    return (
        ()
        if index is None
        else tuple(dict.fromkeys(row[index] for row in table.rows if row[index].strip()))
    )


def external_priorities(table: CsvTable, mapping: Mapping) -> tuple[str, ...]:
    """Return distinct nonblank source labels in first-seen order."""
    validate_columns(table, mapping)
    index = dict(mapping.columns).get("priority")
    return (
        ()
        if index is None
        else tuple(dict.fromkeys(row[index] for row in table.rows if row[index].strip()))
    )


def _validate_parent_type(
    kind: WorkItemType,
    title: str,
    parent: str,
    parent_kind: WorkItemType | None,
) -> None:
    """Add CSV row context before aggregate hierarchy validation runs."""
    if kind == WorkItemType.EPIC and parent:
        raise ValueError(f"Epic {title!r} must be at the root of the plan.")
    if kind == WorkItemType.TASK and parent and parent_kind != WorkItemType.EPIC:
        raise ValueError(f"Task {title!r} requires an Epic parent or no parent.")
    if kind == WorkItemType.SUBTASK and (not parent or parent_kind != WorkItemType.TASK):
        raise ValueError(f"Subtask {title!r} requires a Task parent.")


def preview_import(
    plan: ProgramPlan,
    table: CsvTable,
    mapping: Mapping,
    people: dict[str, Person],
    source_name: str,
) -> ProgramPlan:
    """Return a complete candidate; never mutate the current plan or its baseline."""
    validate_columns(table, mapping)
    columns = dict(mapping.columns)

    def cell(row: tuple[str, ...], field: str) -> str:
        return row[columns[field]] if field in columns else ""

    missing = set(external_people(table, mapping)) - people.keys()
    if missing:
        raise ValueError(
            "Map these external people before importing: " + ", ".join(sorted(missing))
        )
    references = [cell(row, "reference") for row in table.rows]
    identities = [
        cell(row, "row_id") if "row_id" in columns else ref
        for row, ref in zip(table.rows, references, strict=True)
    ]
    for label, values in (("external reference", references), ("row ID", identities)):
        seen: set[str] = set()
        for number, value in enumerate(values, 2):
            if not value.strip() or value in seen:
                raise ValueError(
                    f"CSV row {number}: {label} must be nonblank and unique: {value!r}."
                )
            seen.add(value)
    mapped_types = tuple(dict(mapping.types).get(cell(row, "type")) for row in table.rows)
    priority_values = dict(mapping.priorities)
    types_by_identity = dict(zip(identities, mapped_types, strict=True))
    imported = {r.external_reference for source in plan.imports for r in source.records}
    if imported.intersection(references):
        raise ValueError(
            "Some references are already imported. Re-import reconciliation is not "
            "supported yet; use a new plan or a distinct CSV source."
        )
    ids = {key: uuid4() for key in identities}
    records = []
    errors = []
    for number, (row, key, reference, kind) in enumerate(
        zip(table.rows, identities, references, mapped_types, strict=True), 2
    ):
        try:
            if kind is None:
                raise ValueError(f"Map work type {cell(row, 'type')!r} explicitly.")
            parent = cell(row, "parent")
            if parent and parent not in ids:
                raise ValueError(
                    f"Parent {parent!r} is not in this CSV. Include its row and "
                    "map row ID if parents use numeric IDs."
                )
            _validate_parent_type(kind, cell(row, "title"), parent, types_by_identity.get(parent))
            value = cell(row, "estimate")
            estimate = None if not value.strip() else Decimal(value)
            if estimate is not None and (not estimate.is_finite() or estimate < 0):
                raise ValueError("Estimate must be finite and non-negative.")
            if estimate is not None and mapping.estimate_unit == "seconds":
                estimate /= Decimal(3600)
            dates = [
                None
                if not cell(row, f).strip()
                else datetime.strptime(cell(row, f), mapping.date_format).date()
                for f in ("start", "end")
            ]
            external_person = cell(row, "person")
            mapped_person = people.get(external_person)
            item = WorkItem(
                id=ids[key],
                title=cell(row, "title"),
                kind=kind,
                parent_id=ids.get(parent),
                assignee_id=None if mapped_person is None else mapped_person.id,
                estimate_hours=estimate,
                start=dates[0],
                end=dates[1],
                priority=priority_values.get(cell(row, "priority")),
            )
            records.append(
                ImportedWork(
                    item=item,
                    external_reference=reference,
                    external_person=external_person,
                    person=mapped_person,
                    status=cell(row, "status"),
                    external_priority=cell(row, "priority"),
                )
            )
        except DecimalException:
            errors.append(
                f"CSV row {number} ({reference}): estimate must be a finite number "
                "within the supported decimal range, in the selected units."
            )
        except ValueError as error:
            errors.append(f"CSV row {number} ({reference}): {error}")
    if errors:
        raise ValueError("\n".join(errors))
    snapshot = ImportSnapshot(
        name=source_name, headers=table.headers, rows=table.rows, records=tuple(records)
    )
    roster = {person.id: person for person in plan.people}
    for mapped_person in people.values():
        if mapped_person.id in roster and roster[mapped_person.id] != mapped_person:
            raise ValueError("A mapped person differs from the current roster. Review the mapping.")
        roster[mapped_person.id] = mapped_person
    return replace(
        plan,
        work_items=plan.work_items + tuple(r.item for r in records),
        people=tuple(roster.values()),
        imports=plan.imports + (snapshot,),
    )
