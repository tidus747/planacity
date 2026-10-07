"""Export planned structure for explicit field mapping in Jira's CSV importer."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal

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

DEFAULT_PRIORITY_LABELS = tuple((priority, priority.value.title()) for priority in WorkPriority)


@dataclass(frozen=True)
class ExportOptions:
    headers: tuple[str, ...] = DEFAULT_HEADERS
    estimate_unit: str = "seconds"
    date_format: str = "%Y-%m-%d"
    delimiter: str = ","
    priority_labels: tuple[tuple[WorkPriority, str], ...] = DEFAULT_PRIORITY_LABELS

    def __post_init__(self) -> None:
        if len(self.headers) != len(EXPORT_FIELDS) or any(not h.strip() for h in self.headers):
            raise ValueError("Provide one nonblank header per exported field.")
        if len(set(self.headers)) != len(self.headers):
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


def _ordered_work(plan: ProgramPlan) -> tuple[WorkItem, ...]:
    ordered: list[WorkItem] = []

    def visit(parent: WorkItem | None) -> None:
        for item in plan.children(None if parent is None else parent.id):
            ordered.append(item)
            visit(item)

    visit(None)
    return tuple(ordered)


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
    plan: ProgramPlan, options: ExportOptions | None = None
) -> tuple[PriorityExportPreview, ...]:
    options = options or ExportOptions()
    labels = dict(options.priority_labels)
    records = {r.item.id: r for source in plan.imports for r in source.records}
    rows = []
    for item in _ordered_work(plan):
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


def export_csv(plan: ProgramPlan, options: ExportOptions | None = None) -> str:
    options = options or ExportOptions()
    ordered = _ordered_work(plan)
    ids = {item.id: str(index) for index, item in enumerate(ordered, 1)}
    records = {r.item.id: r for source in plan.imports for r in source.records}
    priority_labels = dict(options.priority_labels)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=options.delimiter)
    writer.writerow(options.headers)
    for item in ordered:
        record = records.get(item.id)
        priority, _ = _export_priority(item, record, priority_labels)
        estimate = item.estimate_hours
        if estimate is not None and options.estimate_unit == "seconds":
            estimate *= Decimal(3600)
            # Division into hours can produce a repeating decimal. Restore integral
            # seconds when the only difference is decimal arithmetic precision.
            integral = estimate.to_integral_value()
            if abs(estimate - integral) < Decimal("1e-20"):
                estimate = integral
        writer.writerow(
            (
                record.external_reference if record else "",
                ids[item.id],
                {"epic": "Epic", "task": "Task", "subtask": "Sub-task"}[item.kind],
                item.title,
                priority,
                "" if item.parent_id is None else ids[item.parent_id],
                "" if estimate is None else format(estimate, "f"),
                "" if item.start is None else item.start.strftime(options.date_format),
                "" if item.end is None else item.end.strftime(options.date_format),
                record.external_person if record else "",
                record.status if record else "",
            )
        )
    return output.getvalue()
