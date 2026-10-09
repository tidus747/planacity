"""Desktop Timeline backed by the canonical projection and validated date edits."""

from __future__ import annotations

from datetime import timedelta
from math import ceil
from uuid import UUID

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QPointF,
    QRectF,
    QSettings,
    Qt,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from planacity.domain import WorkItemType
from planacity.planning.timeline import (
    TimelineDateState,
    TimelineProjection,
    TimelineRow,
    project_timeline,
)
from planacity.planning.timeline_axis import (
    TimelineAxis,
    TimelinePeriod,
    TimelineScale,
    bar_span,
)
from planacity.planning.timeline_dependencies import timeline_dependencies
from planacity.planning.timeline_view import TimelineFilters, TimelineGrouping, arrange_timeline
from planacity.planning.work_context import TopicState
from planacity.ui.pages import WorkspacePage, label
from planacity.ui.session import Session
from planacity.ui.theme import COLORS, Colors, Theme
from planacity.ui.timeline_identity import (
    TimelineBarIdentity,
    TimelineBarShape,
    bar_identity,
    group_identity,
    work_shape,
)
from planacity.ui.timeline_resize import ResizeScheduleView, edit_timeline_dates

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 1
DATE_ROLE = int(Qt.ItemDataRole.UserRole) + 2
PERIOD_ROLE = int(Qt.ItemDataRole.UserRole) + 3
DAY_WIDTH = 34
SCALE_WIDTHS = {TimelineScale.DAY: DAY_WIDTH, TimelineScale.WEEK: 126, TimelineScale.MONTH: 168}
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


def _topic_text(row: TimelineRow, projection: TimelineProjection) -> str:
    return bar_identity(row, projection.groups).label


class TimelineLabelsModel(QAbstractTableModel):
    """Expose hierarchy labels and schedule state from one immutable projection."""

    headers = ("Work item", "Schedule", "Section")

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
            if index.column() == 2:
                return row.section
            return _schedule_text(row)
        if role == Qt.ItemDataRole.ToolTipRole:
            if index.column() == 2:
                return row.section
            return (
                f"{row.kind.value.title()}: {row.title}\n"
                f"WorkGroup: {_topic_text(row, self.projection)}\n{_schedule_text(row)}"
            )
        if role == Qt.ItemDataRole.AccessibleTextRole:
            if index.column() == 2:
                return row.section
            if index.column() == 0:
                return (
                    f"{row.kind.value.title()}: {row.title}. "
                    f"WorkGroup: {_topic_text(row, self.projection)}"
                )
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
    """Expose calendar-aligned periods without copying plan state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TimelineProjection | None = None
        self.scale = TimelineScale.DAY
        self.axis: TimelineAxis | None = None

    def set_projection(self, projection: TimelineProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.axis = TimelineAxis(projection.horizon, self.scale) if projection else None
        self.endResetModel()

    def set_scale(self, scale: TimelineScale) -> None:
        self.scale = scale
        self.set_projection(self.projection)

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.projection is None else len(self.projection.rows)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.axis is None else self.axis.columns

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or self.axis is None or not index.isValid():
            return None
        row = self.projection.rows[index.row()]
        period = self.axis.period(index.column())
        day = self.projection.horizon.start + timedelta(days=period.start_day)
        end = self.projection.horizon.start + timedelta(days=period.end_day)
        dates = day.isoformat() if day == end else f"{day.isoformat()} to {end.isoformat()}"
        if role == Qt.ItemDataRole.UserRole:
            return str(row.item_id)
        if role == ROW_ROLE:
            return row
        if role == PERIOD_ROLE:
            return period
        if role == DATE_ROLE:
            return day
        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                f"{row.kind.value.title()}: {row.title}\n"
                f"WorkGroup: {_topic_text(row, self.projection)}\n"
                f"{dates}\n{_schedule_text(row)}"
            )
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return (
                f"{row.kind.value.title()}: {row.title}, "
                f"WorkGroup: {_topic_text(row, self.projection)}, "
                f"{dates}, {_schedule_text(row)}"
            )
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if self.projection is None or self.axis is None or orientation != Qt.Orientation.Horizontal:
            return None
        if not 0 <= section < self.axis.columns:
            return None
        period = self.axis.period(section)
        day = self.projection.horizon.start + timedelta(days=period.start_day)
        end = self.projection.horizon.start + timedelta(days=period.end_day)
        if role == Qt.ItemDataRole.DisplayRole:
            return period.label
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return day.isoformat() if day == end else f"{day.isoformat()} to {end.isoformat()}"
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


def _theme_colors(widget: QWidget | None) -> Colors:
    return COLORS[_active_theme(widget)]


def _active_theme(widget: QWidget | None) -> Theme:
    if widget is not None:
        theme = getattr(widget.window(), "theme", None)
        if isinstance(theme, Theme):
            return theme
        if widget.palette().window().color().lightness() < 128:
            return Theme.DARK
    return Theme.LIGHT


class _LegendSwatch(QWidget):
    def __init__(
        self,
        *,
        identity: TimelineBarIdentity | None = None,
        shape: TimelineBarShape | None = None,
    ) -> None:
        super().__init__()
        self.identity = identity
        self.shape = shape
        self.setFixedSize(26, 22)
        name = (
            identity.label
            if identity is not None
            else shape.value.replace("_", " ").title()
            if shape is not None
            else "Timeline legend swatch"
        )
        self.setAccessibleName(name)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(3, 3, self.width() - 6, self.height() - 6)
        theme = _active_theme(self)
        if self.identity is not None:
            color = QColor(self.identity.color(theme))
            brush = QBrush(
                color,
                Qt.BrushStyle.Dense4Pattern
                if self.identity.patterned
                else Qt.BrushStyle.SolidPattern,
            )
            painter.setPen(QPen(color, 1))
            painter.setBrush(brush)
            painter.drawRoundedRect(rect, 3, 3)
        elif self.shape is not None:
            _paint_bar_shape(
                painter,
                rect,
                self.shape,
                QBrush(QColor(COLORS[theme].accent)),
                True,
                True,
                False,
                QColor(COLORS[theme].text),
            )
        painter.end()


class TimelineLegend(QFrame):
    """Named, scrollable color and shape key with a complete text equivalent."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "panel")
        self.setAccessibleName("Timeline legend")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        heading = QLabel("Legend")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        self.items = QWidget()
        self.items_layout = QHBoxLayout(self.items)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFixedHeight(48)
        scroll.setWidget(self.items)
        layout.addWidget(scroll, 1)
        self.set_projection(None)

    def _clear(self) -> None:
        while self.items_layout.count():
            child = self.items_layout.takeAt(0)
            if child is None:
                break
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _entry(
        self,
        text: str,
        *,
        identity: TimelineBarIdentity | None = None,
        shape: TimelineBarShape | None = None,
    ) -> None:
        item = QWidget()
        layout = QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(_LegendSwatch(identity=identity, shape=shape))
        layout.addWidget(QLabel(text))
        item.setAccessibleName(text)
        self.items_layout.addWidget(item)

    def set_projection(self, projection: TimelineProjection | None) -> None:
        self._clear()
        if projection is None:
            self._entry("Open a plan to see group colors")
            self.setAccessibleDescription("Open a plan to see Timeline visual identities.")
            self.items_layout.addStretch()
            return
        for group in projection.groups:
            self._entry(group.name, identity=group_identity(group))
        states = {row.topic_state for row in projection.rows}
        exception_labels: list[str] = []
        for row in projection.rows:
            identity = bar_identity(row, projection.groups)
            if identity.state != TopicState.RESOLVED and identity.state in states:
                self._entry(identity.label, identity=identity)
                exception_labels.append(identity.label)
                states.remove(identity.state)
        for kind, text in (
            (WorkItemType.EPIC, "Epic bracket"),
            (WorkItemType.TASK, "Task rounded bar"),
            (WorkItemType.SUBTASK, "Subtask slim bar"),
        ):
            self._entry(text, shape=work_shape(kind))
        self.items_layout.addStretch()
        groups = ", ".join(group.name for group in projection.groups) or "none"
        exceptions = ", ".join(exception_labels) or "none"
        self.setAccessibleDescription(
            f"WorkGroup colors: {groups}. Neutral exceptions: {exceptions}. "
            "Work shapes: Epic bracket, "
            "Task rounded bar, Subtask slim bar."
        )


def _rounded_path(rect: QRectF, round_left: bool, round_right: bool) -> QPainterPath:
    radius = min(5.0, rect.height() / 2)
    path = QPainterPath()
    path.moveTo(rect.left() + (radius if round_left else 0), rect.top())
    path.lineTo(rect.right() - (radius if round_right else 0), rect.top())
    if round_right:
        path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + radius)
        path.lineTo(rect.right(), rect.bottom() - radius)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - radius, rect.bottom())
    else:
        path.lineTo(rect.right(), rect.bottom())
    path.lineTo(rect.left() + (radius if round_left else 0), rect.bottom())
    if round_left:
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - radius)
        path.lineTo(rect.left(), rect.top() + radius)
        path.quadTo(rect.left(), rect.top(), rect.left() + radius, rect.top())
    else:
        path.lineTo(rect.left(), rect.top())
    path.closeSubpath()
    return path


def _paint_bar_shape(
    painter: QPainter,
    bounds: QRectF,
    shape: TimelineBarShape,
    brush: QBrush,
    at_start: bool,
    at_end: bool,
    selected: bool,
    outline: QColor,
) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    if shape == TimelineBarShape.EPIC:
        center = bounds.center().y()
        horizontal = QRectF(bounds.left(), center - 3, bounds.width(), 6)
        painter.drawRect(horizontal)
        if at_start:
            painter.drawRect(QRectF(bounds.left(), bounds.top(), 3, bounds.height()))
        if at_end:
            painter.drawRect(QRectF(bounds.right() - 3, bounds.top(), 3, bounds.height()))
        selection_path = QPainterPath()
        selection_path.addRect(bounds)
    elif shape == TimelineBarShape.TASK:
        selection_path = _rounded_path(bounds, at_start, at_end)
        painter.drawPath(selection_path)
    else:
        slim = QRectF(bounds.left(), bounds.center().y() - 4, bounds.width(), 8)
        painter.drawRect(slim)
        selection_path = QPainterPath()
        selection_path.addRect(slim)
    if selected:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(outline, 2))
        painter.drawPath(selection_path)


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
        period = index.data(PERIOD_ROLE)
        if (
            not isinstance(row, TimelineRow)
            or not isinstance(period, TimelinePeriod)
            or day is None
        ):
            return
        widget = option.widget
        rect = option.rect
        state = option.state
        colors = _theme_colors(widget)
        parent = self.parent()
        model = parent.model() if isinstance(parent, QTableView) else None
        projection = getattr(model, "projection", None)
        if not isinstance(projection, TimelineProjection):
            return
        identity = bar_identity(row, projection.groups)
        theme = _active_theme(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if (
            period.full_days == 1
            and day.weekday() >= 5
            and not state & QStyle.StateFlag.State_Selected
        ):
            painter.fillRect(rect, QColor(colors.sidebar))

        accent = QColor(identity.color(theme))
        brush = QBrush(
            accent,
            Qt.BrushStyle.Dense4Pattern if identity.patterned else Qt.BrushStyle.SolidPattern,
        )
        center = QPointF(rect.center())
        if (
            row.date_state == TimelineDateState.SCHEDULED
            and row.start_day is not None
            and row.end_day is not None
        ):
            span = bar_span(row.start_day, row.end_day, period)
            if span is not None:
                left, right = span
                bar = QRectF(
                    rect.left() + left * rect.width(),
                    rect.top() + 9,
                    (right - left) * rect.width(),
                    rect.height() - 18,
                )
                _paint_bar_shape(
                    painter,
                    bar,
                    work_shape(row.kind),
                    brush,
                    period.start_day <= row.start_day <= period.end_day,
                    period.start_day <= row.end_day <= period.end_day,
                    bool(state & QStyle.StateFlag.State_Selected),
                    QColor(colors.text),
                )
        elif (
            row.date_state == TimelineDateState.START_ONLY
            and row.start_day is not None
            and period.start_day <= row.start_day <= period.end_day
        ):
            center.setX(
                rect.left()
                + ((row.start_day - period.start_day + 0.5) / period.days) * rect.width()
            )
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
            and period.start_day <= row.end_day <= period.end_day
        ):
            center.setX(
                rect.left() + ((row.end_day - period.start_day + 0.5) / period.days) * rect.width()
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = painter.pen()
            pen.setColor(accent)
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawEllipse(center, 7, 7)
        painter.restore()


class TimelinePage(WorkspacePage):
    """Synchronize schedule views and apply explicit date edits to the shared plan."""

    def __init__(self, session: Session, settings: QSettings | None = None) -> None:
        super().__init__(
            "Timeline",
            "Explore the schedule. Drag a bar edge or edit dates to adjust planned work.",
        )
        self.session = session
        self.settings = settings
        self.projection: TimelineProjection | None = None
        self._syncing_selection = False
        self._resized_columns: set[int] = set()
        self.summary = label("Open a project to see its schedule.", "badge")
        self.summary.setAccessibleName("Timeline summary")
        self.content.addWidget(self.summary)
        self.legend = TimelineLegend()
        self.content.addWidget(self.legend)
        self.grouping_box = QComboBox()
        for grouping_choice in TimelineGrouping:
            self.grouping_box.addItem(grouping_choice.value.title(), grouping_choice.value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search work titles...")
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All types", "")
        for kind in WorkItemType:
            self.kind_filter.addItem(kind.value.title(), kind.value)
        self.group_filter = QComboBox()
        self.group_filter.addItem("All WorkGroups", "")
        self.state_filter = QComboBox()
        self.state_filter.addItem("All schedules", "")
        for state in TimelineDateState:
            self.state_filter.addItem(state.value.replace("_", " ").title(), state.value)
        filters = QHBoxLayout()
        for name, control in (
            ("Group by", self.grouping_box),
            ("Search titles", self.search),
            ("Work type", self.kind_filter),
            ("WorkGroup", self.group_filter),
            ("Schedule state", self.state_filter),
        ):
            control.setAccessibleName(name)
            control.setToolTip(name)
            filters.addWidget(control)
        self.clear_filters = QPushButton("Clear filters")
        filters.addWidget(self.clear_filters)
        self.content.addLayout(filters)

        self.labels = QTableView()
        self.labels.setObjectName("timelineLabels")
        self.labels.setAccessibleName("Timeline work items and schedule states")
        self.label_model = TimelineLabelsModel(self.labels)
        self.labels.setModel(self.label_model)
        self.labels.setColumnWidth(0, 280)
        self.labels.setColumnWidth(1, 210)
        self.labels.setColumnWidth(2, 150)
        self.labels.setColumnHidden(2, True)
        self.labels.horizontalHeader().setStretchLastSection(True)

        self.schedule = ResizeScheduleView(session)
        self.schedule.setObjectName("timelineSchedule")
        self.schedule.setAccessibleName("Timeline schedule by day")
        self.schedule_model = TimelineScheduleModel(self.schedule)
        stored = settings.value("timeline/scale", "day") if settings is not None else "day"
        scale = (
            TimelineScale(stored)
            if isinstance(stored, str) and stored in tuple(TimelineScale)
            else TimelineScale.DAY
        )
        self.schedule_model.set_scale(scale)
        self.scale_box = QComboBox()
        self.scale_box.setAccessibleName("Timeline scale")
        for choice in TimelineScale:
            self.scale_box.addItem(choice.value.title(), choice.value)
        self.scale_box.setCurrentIndex(self.scale_box.findData(scale.value))
        scale_label = QLabel("&Scale")
        scale_label.setBuddy(self.scale_box)
        self.header.addWidget(scale_label)
        self.header.addWidget(self.scale_box)
        self.edit_dates = QPushButton("Edit &dates...")
        self.edit_dates.setEnabled(False)
        self.edit_dates.clicked.connect(self._edit_dates)
        self.header.addWidget(self.edit_dates)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(TimelineBarDelegate(self.schedule))
        header = self.schedule.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setDefaultSectionSize(DAY_WIDTH)
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
        self.resize_preview = label(
            "Drag a bar edge to resize dates. Escape cancels. Effort is unchanged."
        )
        self.resize_preview.setAccessibleName("Date resize preview")
        self.content.addWidget(self.resize_preview)
        self.schedule.preview_changed.connect(self.resize_preview.setText)
        self.dependency_toggle = QCheckBox("Show dependency arrows")
        self.dependency_toggle.setChecked(True)
        self.dependency_toggle.toggled.connect(self._toggle_dependencies)
        self.content.addWidget(self.dependency_toggle)
        self.dependency_details = QPlainTextEdit()
        self.dependency_details.setReadOnly(True)
        self.dependency_details.setAccessibleName("Dependency details")
        self.dependency_details.setMaximumHeight(90)
        self.content.addWidget(self.dependency_details)

        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)
        self.scale_box.currentIndexChanged.connect(self._change_scale)
        for box in (self.grouping_box, self.kind_filter, self.group_filter, self.state_filter):
            box.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.clear_filters.clicked.connect(self._clear_filters)
        session.changed.connect(self.refresh)
        self.refresh()

    def _clear_filters(self) -> None:
        for control in (self.search, self.kind_filter, self.group_filter, self.state_filter):
            control.blockSignals(True)
        self.search.clear()
        for box in (self.kind_filter, self.group_filter, self.state_filter):
            box.setCurrentIndex(0)
        for control in (self.search, self.kind_filter, self.group_filter, self.state_filter):
            control.blockSignals(False)
        self.refresh()

    def _size_periods(self) -> None:
        self.schedule.axis = self.schedule_model.axis
        header = self.schedule.horizontalHeader()
        width = SCALE_WIDTHS[self.schedule_model.scale]
        header.setDefaultSectionSize(width)
        # Qt retains explicit widths after resets. Reset only columns we have
        # customized, rather than iterating over every day in long horizons.
        axis = self.schedule_model.axis
        if axis is not None:
            for column in self._resized_columns:
                if column < axis.columns:
                    header.resizeSection(column, width)
            self._resized_columns.update((0, axis.columns - 1))
            for column in {0, axis.columns - 1}:
                period = axis.period(column)
                # A horizon within one period still needs a readable scale header.
                visible_width = (
                    width if axis.columns == 1 else ceil(width * period.days / period.full_days)
                )
                header.resizeSection(column, max(1, visible_width))
        self.schedule.setAccessibleName(f"Timeline schedule by {self.schedule_model.scale.value}")

    def _change_scale(self) -> None:
        self.schedule.cancel_resize()
        scale = TimelineScale(self.scale_box.currentData())
        if scale == self.schedule_model.scale:
            return
        axis = self.schedule_model.axis
        selected_row = self.labels.currentIndex().row()
        selected_column = max(0, self.schedule.currentIndex().column())
        selected_day = axis.period(selected_column).start_day if axis is not None else 0
        first_column = max(0, self.schedule.columnAt(0))
        anchor = 0.0
        if axis is not None:
            period = axis.period(first_column)
            fraction = -self.schedule.columnViewportPosition(
                first_column
            ) / self.schedule.columnWidth(first_column)
            anchor = period.start_day + fraction * period.days
        vertical = self.schedule.verticalScrollBar().value()
        self._syncing_selection = True
        self.schedule_model.set_scale(scale)
        self._size_periods()
        # Recompute scrollbar ranges before restoring the date anchor; Qt otherwise
        # clamps it against the previous scale until the next layout event.
        self.schedule.updateGeometries()
        self._syncing_selection = False
        axis = self.schedule_model.axis
        if axis is not None:
            if selected_row >= 0:
                self._select_row(selected_row, axis.column_for_day(selected_day))
            column = axis.column_for_day(int(anchor))
            period = axis.period(column)
            fraction = (anchor - period.start_day) / period.days
            position = self.schedule.horizontalHeader().sectionPosition(column)
            self.schedule.horizontalScrollBar().setValue(
                round(position + fraction * self.schedule.columnWidth(column))
            )
            self.schedule.verticalScrollBar().setValue(vertical)
        if self.settings is not None:
            self.settings.setValue("timeline/scale", scale.value)
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                self.summary.setText(
                    self.summary.text() + " | Scale preference could not be saved."
                )

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
        self._update_dependency_details()

    def _labels_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row())

    def _schedule_selected(self, current: QModelIndex, previous: QModelIndex) -> None:
        if not self._syncing_selection and current.isValid():
            self._select_row(current.row(), current.column())

    def refresh(self) -> None:
        self.schedule.cancel_resize()
        selected_id = self._selected_id()
        selected = self.labels.currentIndex().data(ROW_ROLE)
        section_id = selected.section_id if isinstance(selected, TimelineRow) else None
        selected_column = max(0, self.schedule.currentIndex().column())
        plan = self.session.document.plan
        projection = project_timeline(plan) if plan is not None else None
        self.legend.set_projection(projection)
        current_group = self.group_filter.currentData()
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All WorkGroups", "")
        if projection is not None:
            for group in projection.groups:
                self.group_filter.addItem(group.name, str(group.id))
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(current_group)))
        self.group_filter.blockSignals(False)
        grouping = TimelineGrouping(self.grouping_box.currentData())
        if projection is not None:
            kind, group_id, state = (
                self.kind_filter.currentData(),
                self.group_filter.currentData(),
                self.state_filter.currentData(),
            )
            projection = arrange_timeline(
                projection,
                grouping,
                TimelineFilters(
                    text=self.search.text(),
                    kind=WorkItemType(kind) if kind else None,
                    group_id=UUID(group_id) if group_id else None,
                    state=TimelineDateState(state) if state else None,
                ),
            )
        grouped = grouping != TimelineGrouping.HIERARCHY
        if self.labels.isColumnHidden(2) == grouped:
            self.labels.setColumnHidden(2, not grouped)
            self.labels.setColumnWidth(0, 190 if grouped else 280)
            self.labels.setColumnWidth(1, 170 if grouped else 210)
        self._syncing_selection = True
        self.projection = projection
        self.schedule.projection = projection
        self.schedule.dependencies = (
            timeline_dependencies(plan, projection)
            if plan is not None and projection is not None
            else ()
        )
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        self._size_periods()
        self._syncing_selection = False

        if projection is None:
            self.summary.setText("Open a project to see its schedule.")
        elif not projection.rows:
            self.summary.setText(
                f"{projection.horizon.start.isoformat()} to "
                f"{projection.horizon.end.isoformat()} | No matching work items"
            )
        else:
            unique_rows = {row.item_id: row for row in projection.rows}.values()
            scheduled = sum(row.date_state == TimelineDateState.SCHEDULED for row in unique_rows)
            partial = sum(
                row.date_state in (TimelineDateState.START_ONLY, TimelineDateState.END_ONLY)
                for row in unique_rows
            )
            unscheduled = len(unique_rows) - scheduled - partial
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
                (
                    index
                    for index, row in enumerate(projection.rows)
                    if row.item_id == selected_id and row.section_id == section_id
                ),
                None,
            )
            if selected_row is None:
                selected_row = next(
                    (
                        index
                        for index, row in enumerate(projection.rows)
                        if row.item_id == selected_id
                    ),
                    None,
                )
            if selected_row is not None:
                self._select_row(selected_row, selected_column)
        self._update_dependency_details()
        self.schedule.viewport().update()

    def _toggle_dependencies(self, checked: bool) -> None:
        self.schedule.show_dependencies = checked
        self.schedule.viewport().update()

    def _update_dependency_details(self) -> None:
        selected = self._selected_id()
        self.edit_dates.setEnabled(selected is not None)
        links = [
            link
            for link in self.schedule.dependencies
            if selected is None or selected in (link.predecessor, link.successor)
        ]
        lines = [link.description + (" | " + link.reason if link.reason else "") for link in links]
        self.dependency_details.setPlainText(
            "\n".join(lines)
            if lines
            else "No dependencies for the selected work."
            if selected is not None
            else "No dependencies in this plan."
        )
        self.dependency_details.setToolTip(
            "Predecessor end -> successor start. Select work to inspect its links. "
            "Arrows require both endpoints on screen. Dates are never changed."
        )

    def _edit_dates(self) -> None:
        selected = self._selected_id()
        if selected is not None:
            edit_timeline_dates(self, self.session, selected)
