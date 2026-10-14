"""Accessible read-only Team mode for the Timeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from fractions import Fraction
from math import ceil
from uuid import UUID

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

from planacity.planning.capacity_breakdown import CapacityLoadState
from planacity.planning.estimate_units import format_fraction
from planacity.planning.timeline_axis import TimelineAxis, TimelinePeriod, TimelineScale, bar_span
from planacity.planning.timeline_team import (
    TeamTimelineDuty,
    TeamTimelinePerson,
    TeamTimelineProjection,
    TeamTimelineWeek,
)
from planacity.ui.pages import label
from planacity.ui.theme import Theme

Index = QModelIndex | QPersistentModelIndex
ROOT = QModelIndex()
LANE_ROLE = int(Qt.ItemDataRole.UserRole) + 40
PERIOD_ROLE = int(Qt.ItemDataRole.UserRole) + 41
ROW_HEIGHT = 34


class TeamLaneKind(StrEnum):
    WORK = "Work"
    ABSENCE = "Absence"
    DUTIES = "Duties"
    LOAD = "Weekly load"


@dataclass(frozen=True)
class TeamLane:
    person: TeamTimelinePerson
    kind: TeamLaneKind


def _hours(value: Fraction | None) -> str:
    return "unknown" if value is None else f"{format_fraction(value)} h"


def _period_dates(projection: TeamTimelineProjection, period: TimelinePeriod) -> str:
    start = projection.horizon.start + timedelta(days=period.start_day)
    end = projection.horizon.start + timedelta(days=period.end_day)
    return start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"


def _duties(person: TeamTimelinePerson, period: TimelinePeriod) -> tuple[TeamTimelineDuty, ...]:
    totals: dict[tuple[UUID, str], Fraction] = {}
    for day in person.duty_days:
        if period.start_day <= day.day_offset <= period.end_day:
            for duty in day.duties:
                key = (duty.rule_id, duty.name)
                totals[key] = totals.get(key, Fraction()) + duty.hours
    return tuple(
        TeamTimelineDuty(rule_id=rule_id, name=name, hours=totals[(rule_id, name)])
        for rule_id, name in sorted(totals, key=lambda value: (value[1].casefold(), str(value[0])))
    )


def _week_text(week: TeamTimelineWeek) -> str:
    dates = week.start.isoformat() if week.start == week.end else f"{week.start} to {week.end}"
    text = (
        f"{dates}: {_hours(week.allocated_hours)} allocated / "
        f"{_hours(week.planning_hours)} planning; {_hours(week.remaining_hours)} remaining; "
        f"{week.state.value.replace('_', ' ')}"
    )
    if week.gaps:
        text += "; " + "; ".join(gap.message for gap in week.gaps)
    return text


def lane_text(lane: TeamLane) -> str:
    person = lane.person
    if lane.kind == TeamLaneKind.WORK:
        visible = "; ".join(
            f"{entry.title}, {entry.start} to {entry.end}, {_hours(entry.hours)} total allocation"
            for entry in person.work
        )
        unplaced = "; ".join(
            f"{entry.title}, {_hours(entry.hours)} allocated, dates missing"
            for entry in person.unplaced_work
        )
        return "; ".join(value for value in (visible, unplaced) if value) or "No allocated work"
    if lane.kind == TeamLaneKind.ABSENCE:
        return (
            "; ".join(
                f"{entry.start} to {entry.end}, unavailable share {entry.unavailable_fraction}"
                for entry in person.absences
            )
            or "No recorded unavailability"
        )
    if lane.kind == TeamLaneKind.DUTIES:
        names = sorted(
            {duty.name for day in person.duty_days for duty in day.duties}, key=str.casefold
        )
        return ", ".join(names) if names else "No reserved duties"
    return "; ".join(_week_text(week) for week in person.weeks) or "Weekly load unknown"


def _lanes(projection: TeamTimelineProjection | None) -> tuple[TeamLane, ...]:
    if projection is None:
        return ()
    return tuple(TeamLane(person, kind) for person in projection.people for kind in TeamLaneKind)


class TeamLabelsModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TeamTimelineProjection | None = None
        self.lanes: tuple[TeamLane, ...] = ()

    def set_projection(self, projection: TeamTimelineProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.lanes = _lanes(projection)
        self.endResetModel()

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else len(self.lanes)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else 2

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        lane = self.lanes[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return lane.person.person_name if lane.kind == TeamLaneKind.WORK else ""
            return lane.kind.value
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            return f"{lane.person.person_name}, {lane.kind.value}: {lane_text(lane)}"
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.person.person_id)
        if role == LANE_ROLE:
            return lane
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ("Person", "Lane")[section] if 0 <= section < 2 else None
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )


class TeamScheduleModel(QAbstractTableModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.projection: TeamTimelineProjection | None = None
        self.lanes: tuple[TeamLane, ...] = ()
        self.scale = TimelineScale.WEEK
        self.axis: TimelineAxis | None = None

    def set_projection(self, projection: TeamTimelineProjection | None) -> None:
        self.beginResetModel()
        self.projection = projection
        self.lanes = _lanes(projection)
        self.axis = TimelineAxis(projection.horizon, self.scale) if projection else None
        self.endResetModel()

    def set_scale(self, scale: TimelineScale) -> None:
        self.scale = scale
        self.set_projection(self.projection)

    def rowCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() else len(self.lanes)

    def columnCount(self, parent: Index = ROOT) -> int:
        return 0 if parent.isValid() or self.axis is None else self.axis.columns

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if self.projection is None or self.axis is None or not index.isValid():
            return None
        lane = self.lanes[index.row()]
        period = self.axis.period(index.column())
        if role == Qt.ItemDataRole.DisplayRole and lane.kind == TeamLaneKind.DUTIES:
            return ", ".join(
                f"{duty.name} {format_fraction(duty.hours)} h"
                for duty in _duties(lane.person, period)
            )
        if role == Qt.ItemDataRole.UserRole:
            return str(lane.person.person_id)
        if role == LANE_ROLE:
            return lane
        if role == PERIOD_ROLE:
            return period
        if role in (Qt.ItemDataRole.ToolTipRole, Qt.ItemDataRole.AccessibleTextRole):
            dates = _period_dates(self.projection, period)
            details = self._details(lane, period)
            return f"{lane.person.person_name}, {lane.kind.value}, {dates}: {details}"
        return None

    def _details(self, lane: TeamLane, period: TimelinePeriod) -> str:
        if lane.kind == TeamLaneKind.WORK:
            work_values = [
                f"{entry.title}, {_hours(entry.hours)} total allocation"
                for entry in lane.person.work
                if bar_span(entry.visible_start_day, entry.visible_end_day, period) is not None
            ]
            if lane.person.unplaced_work:
                work_values.append(f"{len(lane.person.unplaced_work)} allocation(s) missing dates")
            return "; ".join(work_values) or "No allocated work"
        if lane.kind == TeamLaneKind.ABSENCE:
            absence_values = [
                f"{entry.start} to {entry.end}, unavailable share {entry.unavailable_fraction}"
                for entry in lane.person.absences
                if bar_span(entry.visible_start_day, entry.visible_end_day, period) is not None
            ]
            return "; ".join(absence_values) or "No recorded unavailability"
        if lane.kind == TeamLaneKind.DUTIES:
            duty_values = _duties(lane.person, period)
            return (
                "; ".join(f"{duty.name}, {_hours(duty.hours)} reserved" for duty in duty_values)
                or "No reserved duties"
            )
        load_values = [
            _week_text(week)
            for week in lane.person.weeks
            if bar_span(week.visible_start_day, week.visible_end_day, period) is not None
        ]
        return "; ".join(load_values) or "Weekly load unknown"

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if (
            self.axis is not None
            and orientation == Qt.Orientation.Horizontal
            and 0 <= section < self.axis.columns
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return self.axis.period(section).label
        return None

    def flags(self, index: Index) -> Qt.ItemFlag:
        return (
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if index.isValid()
            else Qt.ItemFlag.NoItemFlags
        )


class TeamScheduleDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Index) -> None:
        super().paint(painter, option, index)
        lane = index.data(LANE_ROLE)
        period = index.data(PERIOD_ROLE)
        if not isinstance(lane, TeamLane) or not isinstance(period, TimelinePeriod):
            return
        theme = getattr(option.widget.window(), "theme", Theme.LIGHT)
        dark = theme == Theme.DARK
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.save()
        if lane.kind == TeamLaneKind.WORK:
            color = QColor("#3d67d8" if dark else "#2446a8")
            entries = tuple(
                entry
                for entry in lane.person.work
                if bar_span(entry.visible_start_day, entry.visible_end_day, period) is not None
            )
            height = max(5.0, (option.rect.height() - 8) / max(1, len(entries)))
            for position, work_entry in enumerate(entries):
                left, right = bar_span(
                    work_entry.visible_start_day,
                    work_entry.visible_end_day,
                    period,
                ) or (0, 0)
                rect = QRectF(
                    option.rect.left() + left * option.rect.width(),
                    option.rect.top() + 4 + position * height,
                    max(1.0, (right - left) * option.rect.width()),
                    max(3.0, height - 2),
                )
                painter.setPen(QPen(color.darker(120), 1))
                painter.setBrush(color)
                painter.drawRoundedRect(rect, 2, 2)
        elif lane.kind == TeamLaneKind.ABSENCE:
            color = QColor("#f0a34a" if dark else "#ad5100")
            for absence_entry in lane.person.absences:
                span = bar_span(
                    absence_entry.visible_start_day,
                    absence_entry.visible_end_day,
                    period,
                )
                if span is None:
                    continue
                left, right = span
                available = option.rect.height() - 8
                height = max(5.0, available * float(absence_entry.unavailable_fraction))
                rect = QRectF(
                    option.rect.left() + left * option.rect.width(),
                    option.rect.bottom() - 4 - height,
                    max(1.0, (right - left) * option.rect.width()),
                    height,
                )
                painter.setPen(QPen(color, 1))
                painter.setBrush(QBrush(color, Qt.BrushStyle.Dense4Pattern))
                painter.drawRect(rect)
        elif lane.kind == TeamLaneKind.LOAD:
            for week in lane.person.weeks:
                span = bar_span(week.visible_start_day, week.visible_end_day, period)
                if span is None:
                    continue
                color = self._load_color(week.state, dark)
                left, right = span
                rect = QRectF(
                    option.rect.left() + left * option.rect.width(),
                    option.rect.top() + 4,
                    max(1.0, (right - left) * option.rect.width()),
                    option.rect.height() - 8,
                )
                painter.setPen(QPen(color.darker(120), 1))
                painter.setBrush(color)
                painter.drawRect(rect)
                if period.start_day <= week.visible_start_day <= period.end_day:
                    text = f"{_hours(week.allocated_hours)} / {_hours(week.planning_hours)}"
                    painter.setPen(QColor("#ffffff" if dark else "#111827"))
                    painter.drawText(
                        rect.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, text
                    )
        if selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(option.palette.text().color(), 2))
            painter.drawRect(QRectF(option.rect).adjusted(1, 1, -1, -1))
        painter.restore()

    @staticmethod
    def _load_color(state: CapacityLoadState, dark: bool) -> QColor:
        if state == CapacityLoadState.OVERLOADED:
            return QColor("#d85c5c" if dark else "#f0a0a0")
        if state in (CapacityLoadState.UNKNOWN, CapacityLoadState.INCOMPLETE):
            return QColor("#8e7cc3" if dark else "#d6c9f0")
        if state in (CapacityLoadState.NO_CAPACITY, CapacityLoadState.FULL):
            return QColor("#b8873b" if dark else "#efd19a")
        return QColor("#2d8c70" if dark else "#9ed8c5")


class TeamTimelinePanel(QFrame):
    def __init__(self, scale: TimelineScale) -> None:
        super().__init__()
        self.projection: TeamTimelineProjection | None = None
        self._syncing_selection = False
        self._resized_columns: set[int] = set()
        self.setProperty("role", "panel")
        self.setAccessibleName("Team Timeline")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        self.message = label("Open a project to see team capacity in time.", "muted")
        layout.addWidget(self.message)

        self.labels = QTableView()
        self.labels.setAccessibleName("Team Timeline people and lanes")
        self.label_model = TeamLabelsModel(self.labels)
        self.labels.setModel(self.label_model)
        self.labels.setColumnWidth(0, 150)
        self.labels.setColumnWidth(1, 110)
        self.labels.horizontalHeader().setStretchLastSection(True)
        self.schedule = QTableView()
        self.schedule.setAccessibleName("Team Timeline schedule")
        self.schedule_model = TeamScheduleModel(self.schedule)
        self.schedule_model.set_scale(scale)
        self.schedule.setModel(self.schedule_model)
        self.schedule.setItemDelegate(TeamScheduleDelegate(self.schedule))
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
            view.horizontalHeader().setFixedHeight(46)
        self.labels.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.splitter = QSplitter()
        self.splitter.setAccessibleName("Team Timeline labels and dates")
        self.splitter.addWidget(self.labels)
        self.splitter.addWidget(self.schedule)
        self.splitter.setSizes([490, 700])
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Selected Team Timeline details")
        self.details.setMaximumHeight(76)
        layout.addWidget(self.details)

        self.labels.verticalScrollBar().valueChanged.connect(
            self.schedule.verticalScrollBar().setValue
        )
        self.schedule.verticalScrollBar().valueChanged.connect(
            self.labels.verticalScrollBar().setValue
        )
        self.labels.selectionModel().currentRowChanged.connect(self._labels_selected)
        self.schedule.selectionModel().currentRowChanged.connect(self._schedule_selected)

    def set_projection(self, projection: TeamTimelineProjection | None) -> None:
        person_id = self.labels.currentIndex().data(Qt.ItemDataRole.UserRole)
        lane_kind = self.labels.currentIndex().data(LANE_ROLE)
        kind = lane_kind.kind if isinstance(lane_kind, TeamLane) else TeamLaneKind.WORK
        column = max(0, self.schedule.currentIndex().column())
        self.projection = projection
        self.label_model.set_projection(projection)
        self.schedule_model.set_projection(projection)
        count = len(projection.people) if projection is not None else 0
        self.message.setText(
            f"{count} roster person section(s). Values are planning inputs, "
            "not productivity scores."
            if count
            else "No roster people in this plan."
        )
        if self.label_model.lanes:
            row = next(
                (
                    index
                    for index, lane in enumerate(self.label_model.lanes)
                    if str(lane.person.person_id) == person_id and lane.kind == kind
                ),
                0,
            )
            self._select_row(row, column)
        else:
            self._update_details()

    def set_scale(self, scale: TimelineScale) -> None:
        row = max(0, self.labels.currentIndex().row())
        self.schedule_model.set_scale(scale)
        if self.label_model.lanes:
            self._select_row(min(row, len(self.label_model.lanes) - 1), 0)

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
                visible = (
                    width if axis.columns == 1 else ceil(width * period.days / period.full_days)
                )
                header.resizeSection(column, max(1, visible))
        self.schedule.setAccessibleName(f"Team Timeline by {self.schedule_model.scale.value}")

    def select_first(self) -> None:
        if self.label_model.lanes:
            self._select_row(0)

    def _select_row(self, row: int, column: int | None = None) -> None:
        if not 0 <= row < len(self.label_model.lanes):
            return
        self._syncing_selection = True
        flags = (
            self.labels.selectionModel().SelectionFlag.ClearAndSelect
            | self.labels.selectionModel().SelectionFlag.Rows
        )
        if column is None:
            column = max(0, self.schedule.currentIndex().column())
        column = min(column, max(0, self.schedule_model.columnCount() - 1))
        label_index = self.label_model.index(row, 0)
        schedule_index = self.schedule_model.index(row, column)
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
        if not isinstance(lane, TeamLane):
            self.details.setPlainText(self.message.text())
            return
        index = self.schedule.currentIndex()
        period = index.data(PERIOD_ROLE)
        if isinstance(period, TimelinePeriod) and self.projection is not None:
            details = self.schedule_model._details(lane, period)
            self.details.setPlainText(
                f"{lane.person.person_name} - {lane.kind.value} - "
                f"{_period_dates(self.projection, period)}: {details}"
            )
        else:
            self.details.setPlainText(
                f"{lane.person.person_name} - {lane.kind.value}: {lane_text(lane)}"
            )
