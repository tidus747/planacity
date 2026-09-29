"""Read-only desktop Timeline backed by the canonical timeline projection."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QPointF,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from planacity.planning.timeline import (
    TimelineDateState,
    TimelineProjection,
    TimelineRow,
    project_timeline,
)
from planacity.ui.pages import WorkspacePage, label
from planacity.ui.session import Session
from planacity.ui.theme import COLORS, Colors, Theme

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 1
DATE_ROLE = int(Qt.ItemDataRole.UserRole) + 2
DAY_WIDTH = 34
ROW_HEIGHT = 36


def _schedule_text(row: TimelineRow) -> str:
    if (
        row.date_state == TimelineDateState.SCHEDULED
        and row.start is not None
        and row.end is not None
    ):
        text = f"{row.start.isoformat()} to {row.end.isoformat()}"
    elif row.date_state == TimelineDateState.START_ONLY and row.start is not None:
        text = f"Starts {row.start.isoformat()}; no end"
    elif row.date_state == TimelineDateState.END_ONLY and row.end is not None:
        text = f"Ends {row.end.isoformat()}; no start"
    else:
        text = "Unscheduled"
    if row.outside_horizon:
        text += "; outside horizon"
    return text


class TimelineLabelsModel(QAbstractTableModel):
    """Expose hierarchy labels and schedule state from one immutable projection."""

    headers = ("Work item", "Schedule")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TimelineProjection | None = None

    def set_projection(self, projection: TimelineProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else len(self.projection.rows)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or not index.isValid():
            return None
        row = self.projection.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return f"{'    ' * row.depth}{row.title}"
            return _schedule_text(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{row.kind.value.title()}: {row.title}\n{_schedule_text(row)}"
        if role == Qt.ItemDataRole.AccessibleTextRole:
            if index.column() == 0:
                return f"{row.kind.value.title()}: {row.title}"
            return _schedule_text(row)
        if role == Qt.ItemDataRole.UserRole:
            return str(row.item_id)
        if role == ROW_ROLE:
            return row
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section] if 0 <= section < len(self.headers) else None
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class TimelineScheduleModel(QAbstractTableModel):
    """Expose one display column per horizon day without copying plan state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TimelineProjection | None = None

    def set_projection(self, projection: TimelineProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else len(self.projection.rows)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else self.projection.total_days

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or not index.isValid():
            return None
        row = self.projection.rows[index.row()]
        day = self.projection.horizon.start + timedelta(days=index.column())
        if role == Qt.ItemDataRole.UserRole:
            return str(row.item_id)
        if role == ROW_ROLE:
            return row
        if role == DATE_ROLE:
            return day
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{row.title}\n{day.isoformat()}\n{_schedule_text(row)}"
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{row.title}, {day.isoformat()}, {_schedule_text(row)}"
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if self.projection is None or orientation != Qt.Orientation.Horizontal:
            return None
        day = self.projection.horizon.start + timedelta(days=section)
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{day:%b} {day.day}" if section == 0 or day.day == 1 else str(day.day)
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return day.isoformat()
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


def _theme_colors(widget: QWidget | None) -> Colors:
    if widget is not None:
        theme = getattr(widget.window(), "theme", None)
        if isinstance(theme, Theme):
            return COLORS[theme]
        if widget.palette().window().color().lightness() < 128:
            return COLORS[Theme.DARK]
    return COLORS[Theme.LIGHT]


class TimelineBarDelegate(QStyledItemDelegate):
    """Paint schedule bars and partial-date markers over themed table cells."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Index,
    ) -> None:
        super().paint(painter, option, index)
        row = index.data(ROW_ROLE)
        day = index.data(DATE_ROLE)
        if not isinstance(row, TimelineRow) or day is None:
            return
        widget = option.widget
        rect = option.rect
        state = option.state
        colors = _theme_colors(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if day.weekday() >= 5 and not state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor(colors.sidebar))

        column = index.column()
        accent = QColor(colors.accent)
        center = rect.center()
        if (
            row.date_state == TimelineDateState.SCHEDULED
            and row.start_day is not None
            and row.end_day is not None
            and max(0, row.start_day) <= column <= min(row.end_day, index.model().columnCount() - 1)
        ):
            bar = QRectF(rect).adjusted(-1.0, 11.0, 1.0, -11.0)
            painter.fillRect(bar, accent)
        elif (
            row.date_state == TimelineDateState.START_ONLY
            and row.start_day is not None
            and column == row.start_day
        ):
            size = 7.0
            painter.setBrush(accent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(
                QPolygonF(
                    (
                        QPointF(center.x(), center.y() - size),
                        QPointF(center.x() + size, center.y()),
                        QPointF(center.x(), center.y() + size),
                        QPointF(center.x() - size, center.y()),
                    )
                )
            )
        elif (
            row.date_state == TimelineDateState.END_ONLY
            and row.end_day is not None
            and column == row.end_day
        ):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = painter.pen()
            pen.setColor(accent)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawEllipse(center, 7, 7)
        painter.restore()


class TimelinePage(WorkspacePage):
    """Show the current plan through read-only synchronized label and schedule views."""

    def __init__(self, session: Session) -> None:
        super().__init__(
            "Timeline",
            "See plan dates without changing the canonical Program Plan.",
        )
        self.session = session
        self.projection: TimelineProjection | None = None
        self._syncing_selection = False
        self.summary = label("Open a project to see its schedule.", "badge")
        self.summary.setAccessibleName("Timeline summary")
        self.content.addWidget(self.summary)

        self.labels = QTableView()
        self.labels.setObjectName("timelineLabels")
        self.labels.setAccessibleName("Timeline work items and schedule states")
        self.label_model = TimelineLabelsModel(self.labels)
        self.labels.setModel(self.label_model)
        self.labels.setColumnWidth(0, 280)
        self.labels.setColumnWidth(1, 210)
        self.labels.horizontalHeader().setStretchLastSection(True)

        self.schedule = QTableView()
        self.schedule.setObjectName("timelineSchedule")
        self.schedule.setAccessibleName("Timeline schedule by day")
        self.schedule_model = TimelineScheduleModel(self.schedule)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(TimelineBarDelegate(self.schedule))
        header = self.schedule.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setDefaultSectionSize(DAY_WIDTH)
        header.setMinimumSectionSize(DAY_WIDTH)

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
            view.horizontalHeader().setFixedHeight(46)
        self.labels.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        split = QSplitter()
        split.setAccessibleName("Timeline labels and schedule")
        split.addWidget(self.labels)
        split.addWidget(self.schedule)
        split.setSizes([490, 700])
        split.setStretchFactor(1, 1)
        self.splitter = split
        self.content.addWidget(split, 1)

        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)
        session.changed.connect(self.refresh)
        self.refresh()

    def _selected_id(self) -> UUID | None:
        for index in (self.labels.currentIndex(), self.schedule.currentIndex()):
            value = index.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, str):
                return UUID(value)
        return None

    def _select_row(self, row: int, schedule_column: int | None = None) -> None:
        if self.projection is None or not 0 <= row < len(self.projection.rows):
            return
        self._syncing_selection = True
        flags = (
            self.labels.selectionModel().SelectionFlag.ClearAndSelect
            | self.labels.selectionModel().SelectionFlag.Rows
        )
        label_index = self.label_model.index(row, 0)
        if schedule_column is None:
            current_column = self.schedule.currentIndex().column()
            schedule_column = max(0, current_column)
        schedule_column = min(schedule_column, self.schedule_model.columnCount() - 1)
        schedule_index = self.schedule_model.index(row, schedule_column)
        self.labels.selectionModel().setCurrentIndex(label_index, flags)
        self.schedule.selectionModel().setCurrentIndex(schedule_index, flags)
        self.labels.scrollTo(label_index)
        self.schedule.scrollTo(schedule_index)
        self._syncing_selection = False

    def _labels_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row())

    def _schedule_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row(), current.column())

    def refresh(self) -> None:
        selected_id = self._selected_id()
        selected_column = max(0, self.schedule.currentIndex().column())
        plan = self.session.document.plan
        projection = project_timeline(plan) if plan is not None else None
        self._syncing_selection = True
        self.projection = projection
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        self._syncing_selection = False

        if projection is None:
            self.summary.setText("Open a project to see its schedule.")
        elif not projection.rows:
            self.summary.setText(
                f"{projection.horizon.start.isoformat()} to "
                f"{projection.horizon.end.isoformat()} | No work items"
            )
        else:
            scheduled = sum(
                row.date_state == TimelineDateState.SCHEDULED for row in projection.rows
            )
            partial = sum(
                row.date_state in (TimelineDateState.START_ONLY, TimelineDateState.END_ONLY)
                for row in projection.rows
            )
            unscheduled = len(projection.rows) - scheduled - partial
            self.summary.setText(
                f"{projection.horizon.start.isoformat()} to "
                f"{projection.horizon.end.isoformat()} | {scheduled} scheduled | "
                f"{partial} partial | {unscheduled} unscheduled"
            )
        enabled = bool(projection and projection.rows)
        self.labels.setEnabled(enabled)
        self.schedule.setEnabled(enabled)
        if selected_id is not None and projection is not None:
            selected_row = next(
                (index for index, row in enumerate(projection.rows) if row.item_id == selected_id),
                None,
            )
            if selected_row is not None:
                self._select_row(selected_row, selected_column)
