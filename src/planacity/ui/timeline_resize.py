"""Cancelable Timeline edge gestures over the shared canonical document."""

from datetime import date, timedelta
from uuid import UUID

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import (
    QFocusEvent,
    QHideEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from planacity.domain import ProgramPlan
from planacity.planning.timeline import TimelineRow
from planacity.planning.timeline_resize import ResizeEdge, resize_work, snapped_day
from planacity.planning.work_items import set_work_dates
from planacity.ui.forms import CalendarLineEdit, validated_form
from planacity.ui.session import Session
from planacity.ui.timeline_links import DependencyScheduleView

EDGES: tuple[ResizeEdge, ...] = ("start", "end")


def edit_timeline_dates(parent: QWidget, session: Session, item_id: UUID) -> None:
    original = session.document.plan
    if original is None:
        return
    item = original.work_item(item_id)
    start, end = CalendarLineEdit(), CalendarLineEdit()
    start.setText(item.start.isoformat() if item.start else "")
    end.setText(item.end.isoformat() if item.end else "")
    for control in (start, end):
        control.setPlaceholderText("YYYY-MM-DD or empty")

    def build() -> ProgramPlan:
        if session.document.plan is not original:
            raise ValueError("The plan changed. Cancel and reopen Edit dates.")
        try:
            first = date.fromisoformat(start.text().strip()) if start.text().strip() else None
            last = date.fromisoformat(end.text().strip()) if end.text().strip() else None
        except ValueError as error:
            raise ValueError(
                "Enter dates as YYYY-MM-DD, or clear a field to leave it unset."
            ) from error
        return set_work_dates(original, item_id, start=first, end=last)

    plan = validated_form(
        parent, f"Edit dates: {item.title}", [("&Start", start), ("&End", end)], build
    )
    if plan is not None:
        session.apply(plan)


class ResizeScheduleView(DependencyScheduleView):
    preview_changed = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.setMouseTracking(True)
        self.setAutoScroll(False)
        self._drag: tuple[ProgramPlan, TimelineRow, ResizeEdge, float] | None = None
        self._candidate: ProgramPlan | None = None
        self._candidate_error: str | None = None
        self._ghost_x: float | None = None
        self.setToolTip(
            "Drag a bar edge to resize dates. Escape cancels. Use Edit dates for keyboard entry."
        )

    def edge_x(self, row: TimelineRow, edge: ResizeEdge) -> float | None:
        day = row.start_day if edge == "start" else row.end_day
        if self.axis is None or day is None or not 0 <= day < self.axis.total_days:
            return None
        column = self.axis.column_for_day(day)
        period = self.axis.period(column)
        return self.columnViewportPosition(column) + (
            (day - period.start_day + int(edge == "end")) / period.days
        ) * self.columnWidth(column)

    def _hit(self, point: QPointF) -> tuple[TimelineRow, ResizeEdge, float] | None:
        index = self.rowAt(int(point.y()))
        if self.projection is None or index < 0:
            return None
        row = self.projection.rows[index]
        if row.start is None or row.end is None:
            return None
        center = self.rowViewportPosition(index) + self.rowHeight(index) / 2
        if abs(point.y() - center) > 11:
            return None
        hits = []
        for edge in EDGES:
            x = self.edge_x(row, edge)
            if x is not None and 0 <= x <= self.viewport().width() and abs(point.x() - x) <= 6:
                hits.append((abs(point.x() - x), row, edge, x))
        if not hits:
            return None
        _, row, edge, x = min(hits, key=lambda hit: hit[0])
        return row, edge, x

    def mousePressEvent(self, event: QMouseEvent) -> None:
        hit = self._hit(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)
        if hit is not None and self.session.document.plan is not None:
            row, edge, x = hit
            self._drag = (self.session.document.plan, row, edge, event.position().x() - x)
            self._preview(event.position())

    def _preview(self, point: QPointF) -> None:
        self._candidate = None
        self._candidate_error = None
        self._ghost_x = None
        if self._drag is None or self.axis is None:
            return
        plan, row, edge, grab_offset = self._drag
        original = f"Original: {row.start} to {row.end}. "
        try:
            if not self.viewport().rect().contains(point.toPoint()):
                raise ValueError("Drop inside the schedule or press Escape to cancel.")
            x = point.x() - grab_offset
            column = self.columnAt(int(x))
            last = self.axis.columns - 1
            right = self.columnViewportPosition(last) + self.columnWidth(last)
            if column < 0 and abs(x - right) < 0.5:
                column = last
            if column < 0:
                raise ValueError(
                    "No calendar day here. Use Edit dates for dates outside the horizon."
                )
            fraction = (x - self.columnViewportPosition(column)) / self.columnWidth(column)
            offset = snapped_day(self.axis.period(column), fraction, edge)
            day = plan.horizon.start + timedelta(days=offset)
            candidate = resize_work(plan, row.item_id, edge, day)
            item = candidate.work_item(row.item_id)
            assert item.start is not None and item.end is not None
            warning = (
                " Outside planning horizon."
                if (item.start < plan.horizon.start or item.end > plan.horizon.end)
                else ""
            )
            self._candidate = candidate
            self._ghost_x = self.columnViewportPosition(column) + (
                (offset + int(edge == "end") - self.axis.period(column).start_day)
                / self.axis.period(column).days
            ) * self.columnWidth(column)
            self.preview_changed.emit(
                original + f"Proposed: {item.start} to {item.end} "
                f"({(item.end - item.start).days + 1} calendar days). Effort hours unchanged."
                + warning
            )
        except (ValueError, OverflowError) as error:
            self._candidate_error = original + f"Invalid drop: {error}"
            self.preview_changed.emit(self._candidate_error)
        self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None:
            self._preview(event.position())
            return
        self.viewport().setCursor(
            Qt.CursorShape.SizeHorCursor
            if self._hit(event.position())
            else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None:
            if event.button() != Qt.MouseButton.LeftButton:
                self.cancel_resize()
                return
            self._preview(event.position())
            original = self._drag[0]
            candidate = self._candidate
            candidate_error = self._candidate_error
            super().mouseReleaseEvent(event)
            self.cancel_resize()
            if candidate is not None and self.session.document.plan is original:
                horizontal = self.horizontalScrollBar().value()
                vertical = self.verticalScrollBar().value()
                self.session.apply(candidate)
                self.updateGeometries()
                self.horizontalScrollBar().setValue(horizontal)
                self.verticalScrollBar().setValue(vertical)
                self.preview_changed.emit(
                    "Dates unchanged."
                    if candidate == original
                    else "Dates updated. Effort hours and dependent work are unchanged."
                )
            else:
                self.preview_changed.emit(candidate_error or "Resize cancelled. No dates changed.")
            return
        super().mouseReleaseEvent(event)

    def cancel_resize(self) -> None:
        if self._drag is not None:
            self._drag = None
            self._candidate = None
            self._candidate_error = None
            self._ghost_x = None
            self.preview_changed.emit("Resize cancelled. No dates changed.")
            self.viewport().unsetCursor()
            self.viewport().update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._drag is not None and event.key() == Qt.Key.Key_Escape:
            self.cancel_resize()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.cancel_resize()
        super().focusOutEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self.cancel_resize()
        super().hideEvent(event)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, "_drag"):
            self.cancel_resize()
        return super().event(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QPen(self.palette().text().color(), 2))
        if self.projection is not None:
            for index, row in enumerate(self.projection.rows):
                if row.start is None or row.end is None:
                    continue
                y = self.rowViewportPosition(index) + self.rowHeight(index) / 2
                if not 0 <= y <= self.viewport().height():
                    continue
                for edge in EDGES:
                    x = self.edge_x(row, edge)
                    if x is not None:
                        painter.drawLine(QPointF(x, y - 9), QPointF(x, y + 9))
        if self._ghost_x is not None:
            painter.setPen(QPen(self.palette().text().color(), 2, Qt.PenStyle.DashLine))
            painter.drawLine(
                QPointF(self._ghost_x, 0), QPointF(self._ghost_x, self.viewport().height())
            )
        painter.end()
