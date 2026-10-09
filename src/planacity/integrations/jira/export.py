"""Export planned structure for explicit field mapping in Jira's CSV importer."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from planacity.domain import ProgramPlan, WorkItem, WorkPriority
from planacity.domain.models import ImportedWork
from planacity.integrations.jira.csv_io import DATE_FORMATS

EXPORT_FIELDS = (
    "reference",
    "row_id",
    "type",
    "title",
    "priority",
    "parent",
    "estimate",
    "start",
    "end",
    "person",
    "status",
)
DEFAULT_HEADERS = (
    "Issue key",
    "Issue ID",
    "Issue Type",
    "Summary",
    "Priority",
    "Parent",
    "Original Estimate",
    "Start Date",
    "Due Date",
    "Assignee",
    "Status",
)
REQUIRED_EXPORT_FIELDS = frozenset(EXPORT_FIELDS) - {"reference", "row_id", "parent"}

DEFAULT_PRIORITY_LABELS = tuple((priority, priority.value.title()) for priority in WorkPriority)


@dataclass(frozen=True)
class ExportOptions:
    headers: tuple[str, ...] = DEFAULT_HEADERS
    estimate_unit: str = "seconds"
    date_format: str = "%Y-%m-%d"
    delimiter: str = ","
    priority_labels: tuple[tuple[WorkPriority, str], ...] = DEFAULT_PRIORITY_LABELS
    fields: tuple[str, ...] = EXPORT_FIELDS

    def __post_init__(self) -> None:
        if len(self.headers) != len(EXPORT_FIELDS):
            raise ValueError("Provide one nonblank header per exported field.")
        if not self.fields or len(set(self.fields)) != len(self.fields):
            raise ValueError("Export fields must be nonempty and unique.")
        unknown = set(self.fields) - set(EXPORT_FIELDS)
        if unknown:
            raise ValueError("Export fields must use supported Planacity field names.")
        if not REQUIRED_EXPORT_FIELDS.issubset(self.fields):
            raise ValueError("Only Jira issue key, Work item ID, and Parent are optional.")
        if ("row_id" in self.fields) != ("parent" in self.fields):
            raise ValueError("Work item ID and Parent must be enabled together.")
        selected_headers = [self.headers[EXPORT_FIELDS.index(field)] for field in self.fields]
        if any(not header.strip() for header in selected_headers):
            raise ValueError("Provide a nonblank header for each exported field.")
        if len(set(selected_headers)) != len(selected_headers):
            raise ValueError("Export column headers must be unique.")
        if self.estimate_unit not in ("seconds", "hours"):
            raise ValueError("Estimate units must be seconds or hours.")
        if self.date_format not in DATE_FORMATS or self.delimiter not in (",", ";", "\t"):
            raise ValueError("Choose a supported date format and delimiter.")
        labels = dict(self.priority_labels)
        if set(labels) != set(WorkPriority) or len(labels) != len(self.priority_labels):
            raise ValueError("Provide one target label for each Planacity priority.")
        if any(not isinstance(label, str) or not label.strip() for label in labels.values()):
            raise ValueError("Priority target labels must be nonblank text.")
        folded = [label.strip().casefold() for label in labels.values()]
        if len(set(folded)) != len(folded):
            raise ValueError("Priority target labels must be unique, ignoring case.")


@dataclass(frozen=True)
class PriorityExportPreview:
    reference: str
    title: str
    planacity_priority: str
    csv_priority: str
    result: str


@dataclass(frozen=True)
class AssigneeExportPreview:
    reference: str
    title: str
    person_id: UUID | None
    planacity_assignee: str
    csv_assignee: str
    result: str


@dataclass(frozen=True)
class IdentityExportPreview:
    item_id: UUID
    included: bool
    jira_key: str
    csv_id: str
    parent_reference: str
    importer: str
    result: str


def _ordered_work(plan: ProgramPlan) -> tuple[WorkItem, ...]:
    ordered: list[WorkItem] = []

    def visit(parent: WorkItem | None) -> None:
        for item in plan.children(None if parent is None else parent.id):
            ordered.append(item)
            visit(item)

    visit(None)
    return tuple(ordered)


def _included_ids(plan: ProgramPlan, included_item_ids: tuple[UUID, ...] | None) -> frozenset[UUID]:
    ordered = _ordered_work(plan)
    if included_item_ids is None:
        return frozenset(item.id for item in ordered)
    if len(set(included_item_ids)) != len(included_item_ids):
        raise ValueError("Each work item can be included at most once.")
    known = {item.id for item in ordered}
    unknown = set(included_item_ids) - known
    if unknown:
        raise ValueError("Export selection contains work that is not in the current plan.")
    return frozenset(included_item_ids)


def identity_export_preview(
    plan: ProgramPlan,
    options: ExportOptions | None = None,
    included_item_ids: tuple[UUID, ...] | None = None,
) -> tuple[IdentityExportPreview, ...]:
    """Preview genuine Jira keys and temporary CSV hierarchy references separately."""
    options = options or ExportOptions()
    ordered = _ordered_work(plan)
    included = _included_ids(plan, included_item_ids)
    selected = tuple(item for item in ordered if item.id in included)
    ids = {item.id: str(index) for index, item in enumerate(selected, 1)}
    records = {record.item.id: record for source in plan.imports for record in source.records}
    hierarchical = "row_id" in options.fields
    known = {item.id for item in ordered}
    rows = []
    for item in ordered:
        is_included = item.id in included
        record = records.get(item.id)
        jira_key = record.external_reference if record else ""
        csv_id = ids[item.id] if is_included and hierarchical else ""
        parent_reference = ""
        result = "Ready"
        if not is_included:
            result = "Excluded from this CSV only"
        elif not hierarchical:
            result = "Hierarchy omitted"
        elif item.parent_id is not None:
            if item.parent_id not in known:
                result = "Blocked - parent is missing from the plan"
            elif item.parent_id not in included:
                result = "Blocked - parent is excluded"
            else:
                parent_reference = ids[item.parent_id]
        rows.append(
            IdentityExportPreview(
                item_id=item.id,
                included=is_included,
                jira_key=jira_key if is_included and "reference" in options.fields else "",
                csv_id=csv_id,
                parent_reference=parent_reference,
                importer=("External system import" if hierarchical else "Flat CSV import"),
                result=result,
            )
        )
    return tuple(rows)


def _validate_identity_export(rows: tuple[IdentityExportPreview, ...]) -> None:
    if not any(row.included for row in rows):
        raise ValueError("Select at least one work item to export.")
    blocked = next((row for row in rows if row.included and row.result.startswith("Blocked")), None)
    if blocked is not None:
        raise ValueError(
            f"{blocked.result}. Include its parent, exclude the child, or choose flat CSV "
            "export to omit hierarchy."
        )
    csv_ids = [row.csv_id for row in rows if row.included and row.csv_id]
    if len(csv_ids) != len(set(csv_ids)):
        raise ValueError("Generated CSV Work item IDs must be unique.")


def _export_priority(
    item: WorkItem,
    record: ImportedWork | None,
    labels: dict[WorkPriority, str],
) -> tuple[str, str]:
    if record is not None and item.priority == record.item.priority and record.external_priority:
        if item.priority is None:
            return record.external_priority, "Unresolved source preserved"
        return record.external_priority, "Original source preserved"
    if item.priority is None:
        return "", "Unset - blank output"
    result = labels[item.priority]
    if record is not None and item.priority != record.item.priority:
        return result, "Edited - target label"
    return result, "Canonical target label"


def priority_export_preview(
    plan: ProgramPlan,
    options: ExportOptions | None = None,
    included_item_ids: tuple[UUID, ...] | None = None,
) -> tuple[PriorityExportPreview, ...]:
    options = options or ExportOptions()
    labels = dict(options.priority_labels)
    records = {r.item.id: r for source in plan.imports for r in source.records}
    rows = []
    included = _included_ids(plan, included_item_ids)
    for item in _ordered_work(plan):
        if item.id not in included:
            continue
        record = records.get(item.id)
        value, result = _export_priority(item, record, labels)
        rows.append(
            PriorityExportPreview(
                record.external_reference if record else "",
                item.title,
                "Unset" if item.priority is None else item.priority.value.title(),
                value,
                result,
            )
        )
    return tuple(rows)


def _export_assignee(
    item: WorkItem,
    record: ImportedWork | None,
    mappings: dict[UUID, str],
) -> tuple[str, str]:
    if item.assignee_id is None:
        if (
            record is not None
            and record.item.assignee_id is None
            and record.person is not None
            and record.external_person
        ):
            return record.external_person, "Legacy source preserved"
        return "", "Unassigned - blank output"
    if (
        record is not None
        and record.external_person
        and (
            item.assignee_id == record.item.assignee_id
            or (
                record.item.assignee_id is None
                and record.person is not None
                and item.assignee_id == record.person.id
            )
        )
    ):
        return record.external_person, "Original source preserved"
    value = mappings.get(item.assignee_id, "").strip()
    if not value:
        return "", "External identity required"
    return value, "Explicit identity mapping"


def assignee_export_preview(
    plan: ProgramPlan,
    person_mappings: tuple[tuple[UUID, str], ...] = (),
    included_item_ids: tuple[UUID, ...] | None = None,
) -> tuple[AssigneeExportPreview, ...]:
    """Explain the Jira Assignee value without guessing from display names."""
    mappings = dict(person_mappings)
    if len(mappings) != len(person_mappings):
        raise ValueError("Provide at most one Jira identity for each roster person.")
    unknown = set(mappings) - {person.id for person in plan.people}
    if unknown:
        raise ValueError("Jira identity mappings must reference roster people.")
    records = {record.item.id: record for source in plan.imports for record in source.records}
    rows = []
    included = _included_ids(plan, included_item_ids)
    for item in _ordered_work(plan):
        if item.id not in included:
            continue
        record = records.get(item.id)
        value, result = _export_assignee(item, record, mappings)
        person = plan.person(item.assignee_id) if item.assignee_id is not None else None
        rows.append(
            AssigneeExportPreview(
                reference=record.external_reference if record else "",
                title=item.title,
                person_id=item.assignee_id,
                planacity_assignee="Unassigned" if person is None else person.name,
                csv_assignee=value,
                result=result,
            )
        )
    return tuple(rows)


def export_csv(
    plan: ProgramPlan,
    options: ExportOptions | None = None,
    person_mappings: tuple[tuple[UUID, str], ...] = (),
    included_item_ids: tuple[UUID, ...] | None = None,
) -> str:
    options = options or ExportOptions()
    included = _included_ids(plan, included_item_ids)
    ordered = tuple(item for item in _ordered_work(plan) if item.id in included)
    identity_rows = identity_export_preview(plan, options, tuple(included))
    _validate_identity_export(identity_rows)
    assignee_rows = assignee_export_preview(plan, person_mappings, tuple(included))
    assignees = {item.id: row for item, row in zip(ordered, assignee_rows, strict=True)}
    ids = {item.id: str(index) for index, item in enumerate(ordered, 1)}
    records = {r.item.id: r for source in plan.imports for r in source.records}
    priority_labels = dict(options.priority_labels)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=options.delimiter)
    field_indexes = tuple(EXPORT_FIELDS.index(field) for field in options.fields)
    writer.writerow(tuple(options.headers[index] for index in field_indexes))
    for item in ordered:
        record = records.get(item.id)
        priority, _ = _export_priority(item, record, priority_labels)
        assignee_row = assignees[item.id]
        assignee, assignee_result = assignee_row.csv_assignee, assignee_row.result
        if assignee_result == "External identity required":
            if item.assignee_id is None:
                raise AssertionError("Missing assignee cannot require an external identity.")
            person = plan.person(item.assignee_id)
            raise ValueError(
                f"Provide an explicit Jira identity for '{person.name}' before exporting "
                f"'{item.title}'."
            )
        estimate = item.estimate_hours
        if estimate is not None and options.estimate_unit == "seconds":
            estimate *= Decimal(3600)
            # Division into hours can produce a repeating decimal. Restore integral
            # seconds when the only difference is decimal arithmetic precision.
            integral = estimate.to_integral_value()
            if abs(estimate - integral) < Decimal("1e-20"):
                estimate = integral
        values = (
            record.external_reference if record else "",
            ids[item.id],
            {"epic": "Epic", "task": "Task", "subtask": "Sub-task"}[item.kind],
            item.title,
            priority,
            "" if "parent" not in options.fields or item.parent_id is None else ids[item.parent_id],
            "" if estimate is None else format(estimate, "f"),
            "" if item.start is None else item.start.strftime(options.date_format),
            "" if item.end is None else item.end.strftime(options.date_format),
            assignee,
            record.status if record else "",
        )
        writer.writerow(tuple(values[index] for index in field_indexes))
    return output.getvalue()
