"""Qt hierarchy adapter over the canonical immutable plan."""

from datetime import date
from typing import overload
from uuid import UUID

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QApplication, QStyle

from planacity.domain import ProgramPlan, WorkItem, WorkPriority
from planacity.planning.allocations import WorkAllocationSummary, summarize_allocations
from planacity.planning.estimate_units import conversion_description, estimate_text, parse_estimate
from planacity.planning.findings import PlanningFinding, findings_for_work, planning_findings
from planacity.planning.work_context import set_work_priority
from planacity.planning.work_items import rename_work_item, set_work_dates, set_work_estimate
from planacity.ui.planning_findings import finding_details, finding_note
from planacity.ui.priority import priority_icon, priority_label
from planacity.ui.session import Session

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()


class PlanModel(QAbstractItemModel):
    error = Signal(str)
    headers = (
        "Work item",
        "Type",
        "Priority",
        "Estimate (h)",
        "Start",
        "End",
        "Planning notes",
        "External reference",
    )
    TITLE_COLUMN = 0
    TYPE_COLUMN = 1
    PRIORITY_COLUMN = 2
    ESTIMATE_COLUMN = 3
    START_COLUMN = 4
    END_COLUMN = 5
    NOTES_COLUMN = 6
    EXTERNAL_COLUMN = 7

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.session = session
        self.plan = session.document.plan
        self.effort: dict[UUID, WorkAllocationSummary] = {}
        self.findings: dict[UUID, tuple[PlanningFinding, ...]] = {}
        self.tokens: dict[UUID, int] = {}
        self.ids: dict[int, UUID] = {}
        self._refresh_effort()
        self._remember()
        session.changed.connect(self.refresh)

    def _remember(self) -> None:
        if self.plan:
            for item in self.plan.work_items:
                if item.id not in self.tokens:
                    token = len(self.tokens) + 1
                    self.tokens[item.id] = token
                    self.ids[token] = item.id

    def refresh(self) -> None:
        incoming = self.session.document.plan
        if incoming == self.plan:
            return
        self.beginResetModel()
        self.plan = incoming
        self._refresh_effort()
        self._remember()
        self.endResetModel()

    def _refresh_effort(self) -> None:
        if self.plan is not None:
            self.effort = {
                summary.work_item_id: summary
                for summary in summarize_allocations(self.plan, self.plan.allocations).work
            }
            calculated = planning_findings(self.plan)
            self.findings = {
                item.id: findings_for_work(self.plan, calculated, item.id)
                for item in self.plan.work_items
            }
        else:
            self.effort = {}
            self.findings = {}

    def item(self, index: Index) -> WorkItem | None:
        if self.plan is None or not index.isValid():
            return None
        item_id = self.ids.get(index.internalId())
        return None if item_id is None else self.plan.work_item(item_id)

    def rowCount(self, parent: Index = ROOT) -> int:
        if self.plan is None or (parent.isValid() and parent.column() != 0):
            return 0
        item = self.item(parent)
        return len(self.plan.children(item.id if item else None))

    def columnCount(self, parent: Index = ROOT) -> int:
        return len(self.headers)

    def index(self, row: int, column: int, parent: Index = ROOT) -> QModelIndex:
        if self.plan is None or not self.hasIndex(row, column, parent):
            return QModelIndex()
        item = self.item(parent)
        child = self.plan.children(item.id if item else None)[row]
        return self.createIndex(row, column, self.tokens[child.id])

    def index_for_id(self, item_id: UUID | None) -> QModelIndex:
        if self.plan is None or item_id is None:
            return QModelIndex()
        item = next((i for i in self.plan.work_items if i.id == item_id), None)
        if item is None:
            return QModelIndex()
        row = self.plan.children(item.parent_id).index(item)
        return self.createIndex(row, 0, self.tokens[item.id])

    @overload
    def parent(self) -> QObject: ...

    @overload
    def parent(self, index: Index) -> QModelIndex: ...

    def parent(self, index: Index | None = None) -> QObject | QModelIndex:
        if index is None:
            owner = super().parent()
            assert owner is not None
            return owner
        item = self.item(index)
        return self.index_for_id(item.parent_id) if item else QModelIndex()

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        item = self.item(index)
        if item is None or self.plan is None:
            return None
        outside = any(
            d is not None and not self.plan.horizon.start <= d <= self.plan.horizon.end
            for d in (item.start, item.end)
        )
        reference = next(
            (
                r.external_reference
                for source in self.plan.imports
                for r in source.records
                if r.item.id == item.id
            ),
            "",
        )
        effort = self._effort(item.id)
        estimate = estimate_text(
            self.plan,
            effort.known_estimate_hours if effort.is_container else item.estimate_hours,
            editing=role == Qt.ItemDataRole.EditRole,
        )
        if effort.is_container and effort.missing_estimate_count:
            estimate = (
                f"{estimate} known; {effort.missing_estimate_count} "
                f"estimate{'s' if effort.missing_estimate_count != 1 else ''} missing"
            )
        item_findings = self.findings.get(item.id, ())
        notes = [
            value
            for value in (
                "Outside planning horizon" if outside else "",
                finding_note(item_findings),
            )
            if value
        ]
        values = (
            item.title,
            item.kind.value.title(),
            priority_label(item.priority),
            estimate,
            "" if item.start is None else item.start.isoformat(),
            "" if item.end is None else item.end.isoformat(),
            "; ".join(notes),
            reference,
        )
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = values[index.column()]
            if role == Qt.ItemDataRole.EditRole and index.column() == self.PRIORITY_COLUMN:
                return "" if item.priority is None else item.priority.value
            if (
                role == Qt.ItemDataRole.DisplayRole
                and index.column()
                in (
                    self.ESTIMATE_COLUMN,
                    self.START_COLUMN,
                    self.END_COLUMN,
                )
                and not value
            ):
                return "Not set"
            return value
        if role == Qt.ItemDataRole.DecorationRole and index.column() == self.PRIORITY_COLUMN:
            return priority_icon(item.priority)
        if (
            role == Qt.ItemDataRole.DecorationRole
            and index.column() == self.NOTES_COLUMN
            and values[self.NOTES_COLUMN]
        ):
            return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole):
            if index.column() == self.PRIORITY_COLUMN:
                return "Explicit planning priority. It does not change dates, effort, or capacity."
            if index.column() == self.ESTIMATE_COLUMN:
                if effort.is_container:
                    reference = (
                        f"Entered reference estimate: {item.estimate_hours} h. "
                        if item.estimate_hours is not None
                        else "No entered reference estimate. "
                    )
                    missing = (
                        f" {effort.missing_estimate_count} leaf estimate(s) are missing."
                        if effort.missing_estimate_count
                        else ""
                    )
                    return (
                        f"Derived from {effort.leaf_count} leaf item(s): "
                        f"{effort.known_estimate_hours} h known.{missing} {reference}"
                        "Container estimates are read-only. " + conversion_description(self.plan)
                    )
                return (
                    f"Stored estimate: {item.estimate_hours} h. "
                    if item.estimate_hours is not None
                    else "Estimate is not set. "
                ) + conversion_description(self.plan)
            return (
                (finding_details(item_findings) if item_findings else values[self.NOTES_COLUMN])
                or "Dates: calendar button or YYYY-MM-DD. Estimates: use the column unit. "
                "Clear a cell to leave it unset."
            )
        return None

    def _effort(self, item_id: UUID) -> WorkAllocationSummary:
        if self.plan is None:
            raise ValueError("Open a plan before calculating effort.")
        return self.effort[item_id]

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == self.ESTIMATE_COLUMN and self.plan is not None:
                return f"Estimate ({self.plan.estimate_preferences.unit.symbol})"
            return self.headers[section] if 0 <= section < len(self.headers) else None
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        item = self.item(index)
        estimate_is_editable = bool(
            item is not None and self.plan is not None and not self.plan.children(item.id)
        )
        if index.column() in (
            self.TITLE_COLUMN,
            self.PRIORITY_COLUMN,
            self.START_COLUMN,
            self.END_COLUMN,
        ) or (index.column() == self.ESTIMATE_COLUMN and estimate_is_editable):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def candidate(self, index: Index, text: str) -> ProgramPlan:
        item = self.item(index)
        if item is None or self.plan is None:
            raise ValueError("Select an existing work item first.")
        if index.column() == self.TITLE_COLUMN:
            return rename_work_item(self.plan, item.id, text)
        if index.column() == self.PRIORITY_COLUMN:
            try:
                priority = WorkPriority(text) if text else None
            except ValueError as error:
                raise ValueError(
                    "Work priority must be Highest, High, Medium, Low, Lowest, or unset."
                ) from error
            return set_work_priority(self.plan, item.id, priority)
        if index.column() == self.ESTIMATE_COLUMN:
            if self.plan.children(item.id):
                raise ValueError(
                    "Container estimates are derived from leaf work and cannot be edited."
                )
            hours = parse_estimate(self.plan, text)
            return (
                self.plan
                if hours == item.estimate_hours
                else set_work_estimate(self.plan, item.id, hours)
            )
        if index.column() in (self.START_COLUMN, self.END_COLUMN):
            try:
                value = date.fromisoformat(text) if text.strip() else None
            except ValueError as error:
                raise ValueError("Enter dates as YYYY-MM-DD.") from error
            if value is not None and value.isoformat() != text:
                raise ValueError("Enter dates as YYYY-MM-DD.")
            return set_work_dates(
                self.plan,
                item.id,
                start=value if index.column() == self.START_COLUMN else item.start,
                end=value if index.column() == self.END_COLUMN else item.end,
            )
        raise ValueError("This column is read-only.")

    def setData(self, index: Index, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not isinstance(value, str):
            return False
        edited_item = self.item(index)
        if edited_item is None:
            return False
        try:
            updated = self.candidate(index, value)
        except ValueError as error:
            self.error.emit(str(error))
            return False
        self.plan = updated  # Cell edits preserve indexes and the current editor.
        self._refresh_effort()
        self.session.apply(updated)
        # Notify the edited row first so the filtering proxy can schedule its
        # established post-editor refresh before concurrent findings update.
        ordered = (
            edited_item,
            *(item for item in self.plan.work_items if item.id != edited_item.id),
        )
        for item in ordered:
            first = self.index_for_id(item.id)
            self.dataChanged.emit(first, first.siblingAtColumn(len(self.headers) - 1))
        self.error.emit("")
        return True
