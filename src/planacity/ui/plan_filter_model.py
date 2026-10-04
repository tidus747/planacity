"""A filtering proxy over the editable canonical Plan model, never a second copy."""

from dataclasses import replace
from uuid import UUID

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QFont

from planacity.domain import ProgramPlan, WorkItem
from planacity.planning.plan_filters import filter_plan
from planacity.planning.timeline_view import TimelineFilters
from planacity.ui.plan_model import Index, PlanModel


class PlanFilterModel(QSortFilterProxyModel):
    error = Signal(str)
    filters_about_to_change = Signal()
    filters_changed = Signal()

    def __init__(self, source: PlanModel) -> None:
        super().__init__(source)
        self.source = source
        self.filters = TimelineFilters()
        self.result = filter_plan(source.plan, self.filters)
        self.plan_id = source.plan.id if source.plan else None
        self.pending = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh_filters)
        self.setDynamicSortFilter(False)
        # Recompute acceptance before Qt completes its source-reset handling.
        source.modelReset.connect(self._source_reset)
        self.setSourceModel(source)
        source.error.connect(self.error.emit)
        source.dataChanged.connect(self._queue_refresh)

    @property
    def plan(self) -> ProgramPlan | None:
        return self.source.plan

    def item(self, index: Index) -> WorkItem | None:
        return self.source.item(self.mapToSource(index))

    def index_for_id(self, item_id: UUID | None) -> QModelIndex:
        return self.mapFromSource(self.source.index_for_id(item_id))

    def _source_reset(self) -> None:
        incoming_id = self.plan.id if self.plan else None
        if incoming_id != self.plan_id:
            self.filters = TimelineFilters()
        elif (
            self.filters.group_id
            and self.plan
            and not any(group.id == self.filters.group_id for group in self.plan.work_groups)
        ):
            self.filters = replace(self.filters, group_id=None)
        self.plan_id = incoming_id
        self.result = filter_plan(self.plan, self.filters)

    def _queue_refresh(self) -> None:
        if not self.pending:
            self.pending = True
            self.refresh_timer.start(0)

    def refresh_filters(self) -> None:
        self.refresh_timer.stop()
        self.pending = False
        self.filters_about_to_change.emit()
        result = filter_plan(self.plan, self.filters)
        visibility_changed = result.visible != self.result.visible
        self.result = result
        # Cell edits that keep the same rows must preserve their proxy indexes.
        # Invalidating them unnecessarily can leave editors with stale Qt pointers.
        if visibility_changed:
            self.invalidate()
        self.filters_changed.emit()

    def set_filters(self, filters: TimelineFilters) -> None:
        self.filters = filters
        self.refresh_filters()

    def filterAcceptsRow(self, source_row: int, source_parent: Index) -> bool:
        item = self.source.item(self.source.index(source_row, 0, source_parent))
        return item is not None and item.id in self.result.visible

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        item = self.item(index)
        context = item is not None and item.id not in self.result.matches
        if context:
            if role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setItalic(True)
                return font
            if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleDescriptionRole):
                return (
                    "Ancestor context, not a filter match. Clear or change filters to edit cells."
                )
            if role == Qt.ItemDataRole.DisplayRole and index.column() == 5:
                original = super().data(index, role)
                return "Context only" + (f"; {original}" if original else "")
        return super().data(index, role)

    def flags(self, index: Index) -> Qt.ItemFlag:
        flags = super().flags(index)
        item = self.item(index)
        if item is not None and item.id not in self.result.matches:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        return flags

    def candidate(self, index: Index, text: str) -> ProgramPlan:
        item = self.item(index)
        if item is not None and item.id not in self.result.matches:
            raise ValueError(
                "This ancestor is shown for context. Clear or change filters to edit it."
            )
        return self.source.candidate(self.mapToSource(index), text)

    def setData(self, index: Index, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:
        item = self.item(index)
        if item is not None and item.id not in self.result.matches:
            self.error.emit(
                "This ancestor is shown for context. Clear or change filters to edit it."
            )
            return False
        # Filtering is deferred until the delegate has finished committing/closing.
        return self.source.setData(self.mapToSource(index), value, role)
