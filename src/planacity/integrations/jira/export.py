"""Export planned structure for explicit field mapping in Jira's CSV importer."""

import csv
import io
from dataclasses import dataclass
from decimal import Decimal

from planacity.domain import ProgramPlan, WorkItem
from planacity.integrations.jira.csv_io import DATE_FORMATS

EXPORT_FIELDS = (
    "reference",
    "row_id",
    "type",
    "title",
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
    "Parent",
    "Original Estimate",
    "Start Date",
    "Due Date",
    "Assignee",
    "Status",
)


@dataclass(frozen=True)
class ExportOptions:
    headers: tuple[str, ...] = DEFAULT_HEADERS
    estimate_unit: str = "seconds"
    date_format: str = "%Y-%m-%d"
    delimiter: str = ","

    def __post_init__(self) -> None:
        if len(self.headers) != len(EXPORT_FIELDS) or any(not h.strip() for h in self.headers):
            raise ValueError("Provide one nonblank header per exported field.")
        if len(set(self.headers)) != len(self.headers):
            raise ValueError("Export column headers must be unique.")
        if self.estimate_unit not in ("seconds", "hours"):
            raise ValueError("Estimate units must be seconds or hours.")
        if self.date_format not in DATE_FORMATS or self.delimiter not in (",", ";", "\t"):
            raise ValueError("Choose a supported date format and delimiter.")


def export_csv(plan: ProgramPlan, options: ExportOptions | None = None) -> str:
    options = options or ExportOptions()
    ordered: list[WorkItem] = []

    def visit(parent: WorkItem | None) -> None:
        for item in plan.children(None if parent is None else parent.id):
            ordered.append(item)
            visit(item)

    visit(None)
    ids = {item.id: str(index) for index, item in enumerate(ordered, 1)}
    records = {r.item.id: r for source in plan.imports for r in source.records}
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=options.delimiter)
    writer.writerow(options.headers)
    for item in ordered:
        record = records.get(item.id)
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
                "" if item.parent_id is None else ids[item.parent_id],
                "" if estimate is None else format(estimate, "f"),
                "" if item.start is None else item.start.strftime(options.date_format),
                "" if item.end is None else item.end.strftime(options.date_format),
                record.external_person if record else "",
                record.status if record else "",
            )
        )
    return output.getvalue()
