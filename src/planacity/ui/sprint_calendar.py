"""Accessible, theme-aware sprint lanes for the Program Calendar."""

from datetime import timedelta
from math import ceil
from uuid import UUID

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from planacity.planning.estimate_units import format_fraction
from planacity.planning.sprint_calendar import (
    SprintCalendarLane,
    SprintCalendarProjection,
    SprintCalendarState,
)
from planacity.planning.sprints import SprintLoadState
from planacity.planning.timeline_axis import TimelineAxis, TimelinePeriod, TimelineScale, bar_span
from planacity.ui.pages import label
from planacity.ui.theme import Theme

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
LANE_ROLE = int(Qt.ItemDataRole.UserRole) + 50
PERIOD_ROLE = int(Qt.ItemDataRole.UserRole) + 51
ROW_HEIGHT = 54


def _load_label(state: SprintLoadState) -> str:
    return {
        SprintLoadState.EMPTY_SCOPE: "Empty scope",
        SprintLoadState.UNKNOWN: "Unknown capacity",
        SprintLoadState.INCOMPLETE: "Incomplete",
        SprintLoadState.OVERLOADED: "Overloaded",
        SprintLoadState.NO_ASSIGNED_WORK: "No assigned work",
        SprintLoadState.WITHIN_CAPACITY: "Within capacity",
    }[state]


def _state_label(state: SprintCalendarState) -> str:
    return {
        SprintCalendarState.INSIDE: "Inside horizon",
        SprintCalendarState.PARTIAL: "Partly outside horizon",
        SprintCalendarState.OUTSIDE: "Outside horizon",
    }[state]


def lane_text(lane: SprintCalendarLane) -> str:
    exact = lane.load
    work = (
        ", ".join(
            f"{value.title} "
            + (
                "(dates incomplete)"
                if value.start is None or value.end is None
                else f"({value.start.isoformat()} to {value.end.isoformat()})"
            )
            for value in lane.work
        )
        or "None"
    )
    messages = " ".join(exact.messages)
    return (
        f"{lane.name}; {lane.start.isoformat()} to {lane.end.isoformat()}; "
        f"{_state_label(lane.state)}; {_load_label(exact.state)}; "
        f"planning {format_fraction(exact.planning_hours)} h; "
        f"sprint work {format_fraction(exact.sprint_hours)} h; "
        f"remaining {format_fraction(exact.remaining_hours)} h; assigned work: {work}."
        + (f" {messages}" if messages else "")
    )


class SprintLabelsModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: SprintCalendarProjection | None = None

    def set_projection(self, projection: SprintCalendarProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return (
            0 if parent.isValid() or self.projection is None else len(self.projection.visible_lanes)
        )

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else 1

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or not index.isValid():
            return None
        lane = self.projection.visible_lanes[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{lane.name} ({len(lane.work)} work)"
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return lane_text(lane)
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.id)
        if role == LANE_ROLE:
            return lane
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "Sprint" if section == 0 else None
        return None


class SprintScheduleModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: SprintCalendarProjection | None = None
        self.scale = TimelineScale.WEEK
        self.axis: TimelineAxis | None = None

    def set_projection(self, projection: SprintCalendarProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.axis = TimelineAxis(projection.horizon, self.scale) if projection else None
        self.endResetModel()

    def set_scale(self, scale: TimelineScale) -> None:
        self.scale = scale
        self.set_projection(self.projection)

    def rowCount(self, parent: Index = ROOT) -> int:
        return (
            0 if parent.isValid() or self.projection is None else len(self.projection.visible_lanes)
        )

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.axis is None else self.axis.columns

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or self.axis is None or not index.isValid():
            return None
        lane = self.projection.visible_lanes[index.row()]
        period = self.axis.period(index.column())
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.id)
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
            return f"{dates}: {lane_text(lane)}"
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


class SprintLayerDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        super().paint(painter, option, index)
        lane, period = index.data(LANE_ROLE), index.data(PERIOD_ROLE)
        if not isinstance(lane, SprintCalendarLane) or not isinstance(period, TimelinePeriod):
            return
        if lane.visible_start_day is None or lane.visible_end_day is None:
            return
        span = bar_span(lane.visible_start_day, lane.visible_end_day, period)
        dark = getattr(option.widget.window(), "theme", Theme.LIGHT) == Theme.DARK
        warning = QColor("#f0a34a" if dark else "#ad5100")
        overload = QColor("#ef7180" if dark else "#b5283c")
        accent = QColor("#55c8e8" if dark else "#087c9d")
        state_color = (
            overload
            if lane.load.state == SprintLoadState.OVERLOADED
            else warning
            if lane.load.state
            in {
                SprintLoadState.EMPTY_SCOPE,
                SprintLoadState.UNKNOWN,
                SprintLoadState.INCOMPLETE,
            }
            else accent
        )
        painter.save()
        if span is not None:
            left, right = span
            bounds = QRectF(
                option.rect.left() + left * option.rect.width(),
                option.rect.top() + 6,
                max(1.0, (right - left) * option.rect.width()),
                18,
            )
            painter.setPen(QPen(state_color, 2, Qt.PenStyle.SolidLine))
            painter.setBrush(QBrush(state_color, Qt.BrushStyle.Dense4Pattern))
            painter.drawRoundedRect(bounds, 3, 3)

        visible_work = tuple(
            value
            for value in lane.work
            if value.visible_start_day is not None and value.visible_end_day is not None
        )
        for work_index, work in enumerate(visible_work):
            work_start, work_end = work.visible_start_day, work.visible_end_day
            assert work_start is not None and work_end is not None
            work_span = bar_span(work_start, work_end, period)
            if work_span is None:
                continue
            work_left, work_right = work_span
            work_bounds = QRectF(
                option.rect.left() + work_left * option.rect.width(),
                option.rect.top() + 30 + (work_index % 4) * 5,
                max(1.0, (work_right - work_left) * option.rect.width()),
                4,
            )
            outside = work.inside_sprint is False
            painter.setPen(
                QPen(
                    warning if outside else state_color,
                    1,
                    Qt.PenStyle.DashLine if outside else Qt.PenStyle.SolidLine,
                )
            )
            painter.setBrush(
                QBrush(
                    warning if outside else state_color,
                    Qt.BrushStyle.Dense4Pattern if outside else Qt.BrushStyle.SolidPattern,
                )
            )
            painter.drawRect(work_bounds)
        painter.restore()


class SprintCalendarPanel(QFrame):
    sprintSelected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.projection: SprintCalendarProjection | None = None
        self._syncing_selection = False
        self._resized_columns: set[int] = set()
        self.setProperty("role", "panel")
        self.setAccessibleName("Graphical sprint calendar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        controls = QHBoxLayout()
        self.message = label("No sprint lanes intersect this horizon.", "muted")
        controls.addWidget(self.message, 1)
        controls.addWidget(label("Scale"))
        self.scale = QComboBox()
        self.scale.setAccessibleName("Sprint calendar scale")
        for value in TimelineScale:
            self.scale.addItem(value.value.title(), value.value)
        self.scale.setCurrentIndex(self.scale.findData(TimelineScale.WEEK.value))
        self.scale.currentIndexChanged.connect(self._scale_changed)
        controls.addWidget(self.scale)
        layout.addLayout(controls)

        self.labels, self.schedule = QTableView(), QTableView()
        self.label_model = SprintLabelsModel(self.labels)
        self.schedule_model = SprintScheduleModel(self.schedule)
        self.labels.setModel(self.label_model)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(SprintLayerDelegate(self.schedule))
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
        self.labels.setAccessibleName("Sprint lane labels")
        self.schedule.setAccessibleName("Sprint lane schedule")
        self.labels.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.splitter = QSplitter()
        self.splitter.addWidget(self.labels)
        self.splitter.addWidget(self.schedule)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Selected sprint lane details")
        self.details.setMaximumHeight(74)
        layout.addWidget(self.details)
        self.setMaximumHeight(410)
        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)

    def set_projection(self, projection: SprintCalendarProjection | None) -> None:
        selected = self.selected_sprint_id()
        self.projection = projection
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        visible = len(projection.visible_lanes) if projection else 0
        outside = projection.outside_count if projection else 0
        self.message.setText(
            f"{visible} sprint lane{'s' if visible != 1 else ''}; {outside} outside the horizon. "
            "Large patterned bands are sprints; small solid bars are assigned work; "
            "dashed bars cross sprint dates."
        )
        self._size_periods()
        if selected is not None and self.select_sprint(selected):
            return
        if visible:
            self._select(0)
        else:
            self.details.setPlainText(
                "No sprint lanes intersect this horizon. See the exact table for retained "
                "outside-horizon sprints."
            )

    def selected_sprint_id(self) -> UUID | None:
        value = self.labels.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if isinstance(value, str) and value else None

    def select_sprint(self, sprint_id: UUID) -> bool:
        if self.projection is None:
            return False
        for row, lane in enumerate(self.projection.visible_lanes):
            if lane.id == sprint_id:
                self._select(row, emit=False)
                return True
        outside = next((lane for lane in self.projection.lanes if lane.id == sprint_id), None)
        if outside is not None:
            self.labels.clearSelection()
            self.schedule.clearSelection()
            self.labels.selectionModel().clearCurrentIndex()
            self.schedule.selectionModel().clearCurrentIndex()
            self.details.setPlainText(
                f"{lane_text(outside)} No graphical bar is drawn because this sprint is "
                "outside the planning horizon."
            )
            return True
        return False

    def _scale_changed(self) -> None:
        self.schedule_model.set_scale(TimelineScale(self.scale.currentData()))
        self._resized_columns.clear()
        self._size_periods()

    def _size_periods(self) -> None:
        widths = {TimelineScale.DAY: 48, TimelineScale.WEEK: 150, TimelineScale.MONTH: 260}
        axis, header = self.schedule_model.axis, self.schedule.horizontalHeader()
        width = widths[self.schedule_model.scale]
        header.setDefaultSectionSize(width)
        if axis is None:
            return
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

    def _select(self, row: int, column: int = 0, *, emit: bool = True) -> None:
        if (
            self._syncing_selection
            or self.projection is None
            or not 0 <= row < len(self.projection.visible_lanes)
        ):
            return
        self._syncing_selection = True
        lane = self.projection.visible_lanes[row]
        self.details.setPlainText(lane_text(lane))
        self.labels.setCurrentIndex(self.label_model.index(row, 0))
        if self.schedule_model.columnCount():
            self.schedule.setCurrentIndex(
                self.schedule_model.index(row, min(column, self.schedule_model.columnCount() - 1))
            )
        self._syncing_selection = False
        if emit:
            self.sprintSelected.emit(lane.id)

    def _labels_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self._select(current.row())

    def _schedule_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self._select(current.row(), current.column())
