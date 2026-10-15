"""Accessible, theme-aware Timeline lanes for shared program events."""

from datetime import timedelta
from math import ceil

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QPlainTextEdit,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from planacity.planning.program_calendar import (
    CalendarProjectionState,
    ProgramCalendarEntry,
    ProgramCalendarProjection,
)
from planacity.planning.timeline_axis import TimelineAxis, TimelinePeriod, TimelineScale, bar_span
from planacity.ui.pages import label
from planacity.ui.program_calendar import impact_label, kind_label
from planacity.ui.theme import Theme

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
ENTRY_ROLE = int(Qt.ItemDataRole.UserRole) + 30
PERIOD_ROLE = int(Qt.ItemDataRole.UserRole) + 31
ROW_HEIGHT = 36


def state_label(state: CalendarProjectionState) -> str:
    return {
        CalendarProjectionState.INSIDE: "Inside horizon",
        CalendarProjectionState.PARTIAL: "Partly outside horizon",
        CalendarProjectionState.OUTSIDE: "Outside horizon",
    }[state]


def entry_text(entry: ProgramCalendarEntry) -> str:
    return (
        f"{entry.name}; {kind_label(entry.kind)}; {entry.start.isoformat()} to "
        f"{entry.end.isoformat()}; {impact_label(entry.unavailable_fraction)}; "
        f"{state_label(entry.state)}"
    )


class CalendarLabelsModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: ProgramCalendarProjection | None = None

    def set_projection(self, projection: ProgramCalendarProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return (
            0
            if parent.isValid() or self.projection is None
            else len(self.projection.visible_entries)
        )

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else 1

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or not index.isValid():
            return None
        entry = self.projection.visible_entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{entry.name} ({kind_label(entry.kind)})"
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return entry_text(entry)
        if role == Qt.ItemDataRole.UserRole:
            return str(entry.id)
        if role == ENTRY_ROLE:
            return entry
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "Program Calendar" if section == 0 else None
        return None


class CalendarScheduleModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: ProgramCalendarProjection | None = None
        self.scale = TimelineScale.DAY
        self.axis: TimelineAxis | None = None

    def set_projection(self, projection: ProgramCalendarProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.axis = TimelineAxis(projection.horizon, self.scale) if projection else None
        self.endResetModel()

    def set_scale(self, scale: TimelineScale) -> None:
        self.scale = scale
        self.set_projection(self.projection)

    def rowCount(self, parent: Index = ROOT) -> int:
        return (
            0
            if parent.isValid() or self.projection is None
            else len(self.projection.visible_entries)
        )

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.axis is None else self.axis.columns

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or self.axis is None or not index.isValid():
            return None
        entry = self.projection.visible_entries[index.row()]
        period = self.axis.period(index.column())
        if role == Qt.ItemDataRole.UserRole:
            return str(entry.id)
        if role == ENTRY_ROLE:
            return entry
        if role == PERIOD_ROLE:
            return period
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            first = self.projection.horizon.start + timedelta(days=period.start_day)
            last = self.projection.horizon.start + timedelta(days=period.end_day)
            dates = (
                first.isoformat() if first == last else f"{first.isoformat()} to {last.isoformat()}"
            )
            return f"{dates}: {entry_text(entry)}"
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if (
            self.axis is None
            or orientation != Qt.Orientation.Horizontal
            or not 0 <= section < self.axis.columns
        ):
            return None
        return self.axis.period(section).label if role == Qt.ItemDataRole.DisplayRole else None


class CalendarDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        super().paint(painter, option, index)
        entry, period = index.data(ENTRY_ROLE), index.data(PERIOD_ROLE)
        if not isinstance(entry, ProgramCalendarEntry) or not isinstance(period, TimelinePeriod):
            return
        assert entry.visible_start_day is not None and entry.visible_end_day is not None
        span = bar_span(entry.visible_start_day, entry.visible_end_day, period)
        if span is None:
            return
        dark = getattr(option.widget.window(), "theme", Theme.LIGHT) == Theme.DARK
        colors = {
            "public_holiday": "#f0a34a" if dark else "#ad5100",
            "customer_visit": "#55c8e8" if dark else "#087c9d",
            "company_event": "#d58cff" if dark else "#8544ad",
            "program_event": "#72d7a2" if dark else "#187c4c",
            "other": "#aab4c3" if dark else "#526173",
        }
        color = QColor(colors[entry.kind.value])
        left, right = span
        bounds = QRectF(
            option.rect.left() + left * option.rect.width(),
            option.rect.top() + 7,
            max(1.0, (right - left) * option.rect.width()),
            option.rect.height() - 14,
        )
        painter.save()
        painter.setPen(
            QPen(
                color,
                2,
                Qt.PenStyle.DashLine if entry.unavailable_fraction == 0 else Qt.PenStyle.SolidLine,
            )
        )
        painter.setBrush(
            Qt.BrushStyle.NoBrush
            if entry.unavailable_fraction == 0
            else QBrush(color, Qt.BrushStyle.Dense4Pattern)
        )
        painter.drawRoundedRect(bounds, 3, 3)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(QPen(option.palette.text().color(), 2))
            painter.drawRect(QRectF(option.rect).adjusted(1, 1, -1, -1))
        painter.restore()


class TimelineCalendarPanel(QFrame):
    def __init__(self, scale: TimelineScale) -> None:
        super().__init__()
        self.projection: ProgramCalendarProjection | None = None
        self._syncing_selection = False
        self._resized_columns: set[int] = set()
        self.setProperty("role", "panel")
        self.setAccessibleName("Shared program events")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        self.message = label("No shared events intersect this horizon.", "muted")
        layout.addWidget(self.message)
        self.labels, self.schedule = QTableView(), QTableView()
        self.label_model, self.schedule_model = (
            CalendarLabelsModel(self.labels),
            CalendarScheduleModel(self.schedule),
        )
        self.schedule_model.set_scale(scale)
        self.labels.setModel(self.label_model)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(CalendarDelegate(self.schedule))
        self.labels.horizontalHeader().setStretchLastSection(True)
        header = self.schedule.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(1)
        for view in (self.labels, self.schedule):
            view.setAlternatingRowColors(True)
            view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.verticalHeader().hide()
            view.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
            view.horizontalHeader().setFixedHeight(38)
        self.labels.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.splitter = QSplitter()
        self.splitter.addWidget(self.labels)
        self.splitter.addWidget(self.schedule)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Selected program event details")
        self.details.setMaximumHeight(54)
        layout.addWidget(self.details)
        self.setMaximumHeight(260)
        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)

    def set_projection(self, projection: ProgramCalendarProjection | None) -> None:
        self.projection = projection
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        visible = len(projection.visible_entries) if projection else 0
        outside = projection.outside_count if projection else 0
        self.message.setText(
            f"{visible} event lane{'s' if visible != 1 else ''}; {outside} outside the "
            "horizon. Solid patterned bars affect capacity; dashed outlines are context only."
        )
        if visible:
            self._select(0)
        else:
            self.details.setPlainText("No shared events intersect this horizon.")

    def set_scale(self, scale: TimelineScale) -> None:
        self.schedule_model.set_scale(scale)

    def size_periods(self, width: int) -> None:
        axis, header = self.schedule_model.axis, self.schedule.horizontalHeader()
        header.setDefaultSectionSize(width)
        if axis is not None:
            for column in self._resized_columns:
                if column < axis.columns:
                    header.resizeSection(column, width)
            self._resized_columns.update((0, axis.columns - 1))
            for column in {0, axis.columns - 1}:
                period = axis.period(column)
                visible_width = (
                    width if axis.columns == 1 else ceil(width * period.days / period.full_days)
                )
                header.resizeSection(column, max(1, visible_width))

    def select_first(self) -> None:
        self._select(0)

    def _select(self, row: int, column: int = 0) -> None:
        if (
            self._syncing_selection
            or self.projection is None
            or not 0 <= row < len(self.projection.visible_entries)
        ):
            return
        self._syncing_selection = True
        entry = self.projection.visible_entries[row]
        self.details.setPlainText(entry_text(entry))
        self.labels.setCurrentIndex(self.label_model.index(row, 0))
        if self.schedule_model.columnCount():
            self.schedule.setCurrentIndex(
                self.schedule_model.index(row, min(column, self.schedule_model.columnCount() - 1))
            )
        self._syncing_selection = False

    def _labels_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self._select(current.row())

    def _schedule_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self._select(current.row(), current.column())
