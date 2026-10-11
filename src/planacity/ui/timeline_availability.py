"""Accessible table models and painting for the optional Timeline availability lanes."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
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

from planacity.planning.timeline_availability import (
    TimelineUnavailabilityEntry,
    TimelineUnavailabilityLane,
    TimelineUnavailabilityProjection,
)
from planacity.planning.timeline_axis import TimelineAxis, TimelinePeriod, TimelineScale, bar_span
from planacity.ui.pages import label
from planacity.ui.theme import Theme

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
LANE_ROLE = int(Qt.ItemDataRole.UserRole) + 20
PERIOD_ROLE = int(Qt.ItemDataRole.UserRole) + 21
ROW_HEIGHT = 36


def _share_text(value: Decimal) -> str:
    state = "full" if value == 1 else "partial"
    return f"Unavailable share {value} ({state})"


def entry_text(entry: TimelineUnavailabilityEntry) -> str:
    """Describe canonical dates rather than the clipped display coordinates."""
    return (
        f"{entry.start.isoformat()} to {entry.end.isoformat()}: "
        f"{_share_text(entry.unavailable_fraction)}"
    )


def lane_text(lane: TimelineUnavailabilityLane) -> str:
    return f"{lane.person_name}: " + "; ".join(entry_text(entry) for entry in lane.entries)


class TimelineAvailabilityLabelsModel(QAbstractTableModel):
    """Expose one stable, named row for each person with visible unavailability."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TimelineUnavailabilityProjection | None = None

    def set_projection(self, projection: TimelineUnavailabilityProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else len(self.projection.lanes)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else 1

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or not index.isValid():
            return None
        lane = self.projection.lanes[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return lane.person_name
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return lane_text(lane)
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.person_id)
        if role == LANE_ROLE:
            return lane
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "Recorded unavailability" if section == 0 else None
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )


class TimelineAvailabilityScheduleModel(QAbstractTableModel):
    """Expose unavailability lanes over the same calendar-aligned scale as work."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TimelineUnavailabilityProjection | None = None
        self.scale = TimelineScale.DAY
        self.axis: TimelineAxis | None = None

    def set_projection(self, projection: TimelineUnavailabilityProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.axis = TimelineAxis(projection.horizon, self.scale) if projection else None
        self.endResetModel()

    def set_scale(self, scale: TimelineScale) -> None:
        self.scale = scale
        self.set_projection(self.projection)

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else len(self.projection.lanes)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.axis is None else self.axis.columns

    def _events(
        self, lane: TimelineUnavailabilityLane, period: TimelinePeriod
    ) -> tuple[TimelineUnavailabilityEntry, ...]:
        return tuple(
            entry
            for entry in lane.entries
            if bar_span(entry.visible_start_day, entry.visible_end_day, period) is not None
        )

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or self.axis is None or not index.isValid():
            return None
        lane = self.projection.lanes[index.row()]
        period = self.axis.period(index.column())
        events = self._events(lane, period)
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.person_id)
        if role == LANE_ROLE:
            return lane
        if role == PERIOD_ROLE:
            return period
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            first = self.projection.horizon.start + timedelta(days=period.start_day)
            last = self.projection.horizon.start + timedelta(days=period.end_day)
            dates = (
                first.isoformat() if first == last else f"{first.isoformat()} to {last.isoformat()}"
            )
            details = "; ".join(entry_text(entry) for entry in events)
            return f"{lane.person_name}, {dates}: {details or 'No recorded unavailability'}"
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
        period = self.axis.period(section)
        if role == Qt.ItemDataRole.DisplayRole:
            return period.label
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )


class TimelineAvailabilityDelegate(QStyledItemDelegate):
    """Paint clipped hatched blocks whose height distinguishes partial from full absence."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        super().paint(painter, option, index)
        lane = index.data(LANE_ROLE)
        period = index.data(PERIOD_ROLE)
        if not isinstance(lane, TimelineUnavailabilityLane) or not isinstance(
            period, TimelinePeriod
        ):
            return
        theme = getattr(option.widget.window(), "theme", Theme.LIGHT)
        if not isinstance(theme, Theme):
            theme = Theme.LIGHT
        color = QColor("#ad5100" if theme == Theme.LIGHT else "#f0a34a")
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        for entry in lane.entries:
            span = bar_span(entry.visible_start_day, entry.visible_end_day, period)
            if span is None:
                continue
            left, right = span
            available_height = option.rect.height() - 10
            height = max(6.0, available_height * float(entry.unavailable_fraction))
            bounds = QRectF(
                option.rect.left() + left * option.rect.width(),
                option.rect.bottom() - 5 - height,
                max(1.0, (right - left) * option.rect.width()),
                height,
            )
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color, Qt.BrushStyle.Dense4Pattern))
            painter.drawRect(bounds)
        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(option.palette.text().color(), 2))
            painter.drawRect(QRectF(option.rect).adjusted(1, 1, -1, -1))
        painter.restore()


class TimelineAvailabilityPanel(QFrame):
    """Own the optional lanes, selection details, and calendar column sizing."""

    def __init__(self, scale: TimelineScale) -> None:
        super().__init__()
        self.projection: TimelineUnavailabilityProjection | None = None
        self._syncing_selection = False
        self._resized_columns: set[int] = set()
        self.setProperty("role", "panel")
        self.setAccessibleName("Recorded personal unavailability")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        self.message = label("No recorded unavailability in this horizon.", "muted")
        layout.addWidget(self.message)

        self.labels = QTableView()
        self.labels.setAccessibleName("People with recorded unavailability")
        self.label_model = TimelineAvailabilityLabelsModel(self.labels)
        self.labels.setModel(self.label_model)
        self.labels.horizontalHeader().setStretchLastSection(True)

        self.schedule = QTableView()
        self.schedule.setAccessibleName("Unavailability by day")
        self.schedule_model = TimelineAvailabilityScheduleModel(self.schedule)
        self.schedule_model.set_scale(scale)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(TimelineAvailabilityDelegate(self.schedule))
        header = self.schedule.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(1)
        header.setTextElideMode(Qt.TextElideMode.ElideRight)
        for view in (self.labels, self.schedule):
            view.setAlternatingRowColors(True)
            view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            view.setWordWrap(False)
            view.verticalHeader().hide()
            view.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
            view.verticalHeader().setMinimumSectionSize(ROW_HEIGHT)
            view.horizontalHeader().setFixedHeight(38)
        self.labels.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.splitter = QSplitter()
        self.splitter.setAccessibleName("Unavailability labels and dates")
        self.splitter.addWidget(self.labels)
        self.splitter.addWidget(self.schedule)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Selected unavailability details")
        self.details.setMaximumHeight(54)
        layout.addWidget(self.details)
        self.setMaximumHeight(235)

        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)

    def set_projection(self, projection: TimelineUnavailabilityProjection | None) -> None:
        selected_person = self.labels.currentIndex().data(Qt.ItemDataRole.UserRole)
        selected_column = max(0, self.schedule.currentIndex().column())
        self.projection = projection
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        count = len(projection.lanes) if projection is not None else 0
        lane_label = "person lane" if count == 1 else "person lanes"
        self.message.setText(
            f"{count} {lane_label}. Hatched height shows the unavailable share."
            if count
            else "No positive recorded unavailability intersects this horizon."
        )
        self.labels.setEnabled(bool(count))
        self.schedule.setEnabled(bool(count))
        if projection is not None and projection.lanes:
            row = next(
                (
                    index
                    for index, lane in enumerate(projection.lanes)
                    if str(lane.person_id) == selected_person
                ),
                0,
            )
            self._select_row(row, selected_column)
        else:
            self._update_details()

    def set_scale(self, scale: TimelineScale) -> None:
        selected_person = self.labels.currentIndex().data(Qt.ItemDataRole.UserRole)
        self.schedule_model.set_scale(scale)
        if self.projection is not None and self.projection.lanes:
            row = next(
                (
                    index
                    for index, lane in enumerate(self.projection.lanes)
                    if str(lane.person_id) == selected_person
                ),
                0,
            )
            self._select_row(row, 0)

    def size_periods(self, width: int) -> None:
        axis = self.schedule_model.axis
        header = self.schedule.horizontalHeader()
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
        self.schedule.setAccessibleName(f"Unavailability by {self.schedule_model.scale.value}")

    def select_first(self) -> None:
        if self.projection is not None and self.projection.lanes:
            self._select_row(0)

    def _select_row(self, row: int, schedule_column: int | None = None) -> None:
        if self.projection is None or not 0 <= row < len(self.projection.lanes):
            return
        self._syncing_selection = True
        flags = (
            self.labels.selectionModel().SelectionFlag.ClearAndSelect
            | self.labels.selectionModel().SelectionFlag.Rows
        )
        label_index = self.label_model.index(row, 0)
        if schedule_column is None:
            schedule_column = max(0, self.schedule.currentIndex().column())
        schedule_column = min(schedule_column, self.schedule_model.columnCount() - 1)
        schedule_index = self.schedule_model.index(row, schedule_column)
        self.labels.selectionModel().setCurrentIndex(label_index, flags)
        self.schedule.selectionModel().setCurrentIndex(schedule_index, flags)
        self.labels.scrollTo(label_index)
        self.schedule.scrollTo(schedule_index)
        self._syncing_selection = False
        self._update_details()

    def _labels_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row())

    def _schedule_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row(), current.column())

    def _update_details(self) -> None:
        lane = self.labels.currentIndex().data(LANE_ROLE)
        self.details.setPlainText(
            lane_text(lane) if isinstance(lane, TimelineUnavailabilityLane) else self.message.text()
        )
