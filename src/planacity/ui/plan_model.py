"""Qt hierarchy adapter over the canonical immutable plan."""

from datetime import date
from typing import cast, overload
from uuid import UUID

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    Signal,
)

from planacity.domain import ProgramPlan, WorkItem
from planacity.planning.allocations import WorkAllocationSummary, summarize_allocations
from planacity.planning.estimate_units import conversion_description, estimate_text, parse_estimate
from planacity.planning.work_items import rename_work_item, set_work_dates, set_work_estimate
from planacity.ui.session import Session

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()


class PlanModel(QAbstractItemModel):
    error = Signal(str)
    headers = (
        "Work item",
        "Type",
        "Estimate (h)",
        "Start",
        "End",
        "Planning notes",
        "External reference",
    )

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.session = session
        self.plan = session.document.plan
        self.effort: dict[UUID, WorkAllocationSummary] = {}
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
        self.effort = (
            {
                summary.work_item_id: summary
                for summary in summarize_allocations(self.plan, self.plan.allocations).work
            }
            if self.plan is not None
            else {}
        )

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
            return cast(QObject, super().parent())
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
        values = (
            item.title,
            item.kind.value.title(),
            estimate,
            "" if item.start is None else item.start.isoformat(),
            "" if item.end is None else item.end.isoformat(),
            "Outside planning horizon" if outside else "",
            reference,
        )
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = values[index.column()]
            if role == Qt.ItemDataRole.DisplayRole and index.column() in (2, 3, 4) and not value:
                return "Not set"
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 2:
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
                        "Container estimates are read-only. "
                        + conversion_description(self.plan)
                    )
                return (
                    f"Stored estimate: {item.estimate_hours} h. "
                    if item.estimate_hours is not None
                    else "Estimate is not set. "
                ) + conversion_description(self.plan)
            return (
                values[5]
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
            if section == 2 and self.plan is not None:
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
        if index.column() in (0, 3, 4) or (index.column() == 2 and estimate_is_editable):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def candidate(self, index: Index, text: str) -> ProgramPlan:
        item = self.item(index)
        if item is None or self.plan is None:
            raise ValueError("Select an existing work item first.")
        if index.column() == 0:
            return rename_work_item(self.plan, item.id, text)
        if index.column() == 2:
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
        if index.column() in (3, 4):
            try:
                value = date.fromisoformat(text) if text.strip() else None
            except ValueError as error:
                raise ValueError("Enter dates as YYYY-MM-DD.") from error
            if value is not None and value.isoformat() != text:
                raise ValueError("Enter dates as YYYY-MM-DD.")
            return set_work_dates(
                self.plan,
                item.id,
                start=value if index.column() == 3 else item.start,
                end=value if index.column() == 4 else item.end,
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
        self.dataChanged.emit(
            self.index(index.row(), 0, self.parent(index)),
            self.index(index.row(), len(self.headers) - 1, self.parent(index)),
        )
        parent_id = edited_item.parent_id
        while parent_id is not None:
            parent_index = self.index_for_id(parent_id).siblingAtColumn(2)
            self.dataChanged.emit(parent_index, parent_index)
            parent_id = self.plan.work_item(parent_id).parent_id
        self.error.emit("")
        return True
