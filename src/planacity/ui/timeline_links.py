"""Paint dependency connectors over the Timeline's existing schedule cells."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QTableView

from planacity.planning.timeline import TimelineProjection
from planacity.planning.timeline_axis import TimelineAxis
from planacity.planning.timeline_dependencies import TimelineDependency, connector_points


class DependencyScheduleView(QTableView):
    projection: TimelineProjection | None = None
    axis: TimelineAxis | None = None
    dependencies: tuple[TimelineDependency, ...] = ()
    show_dependencies = True

    def dependency_paths(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Only draw connectors whose actual endpoints are visible in this viewport."""
        if not self.show_dependencies or self.axis is None or self.projection is None:
            return ()
        axis = self.axis
        rows = self.projection.rows

        def endpoint(row_index: int, day: int, end: bool) -> tuple[float, float]:
            column = axis.column_for_day(day)
            period = axis.period(column)
            fraction = (day - period.start_day + int(end)) / period.days
            x = self.columnViewportPosition(column) + fraction * self.columnWidth(column)
            y = self.rowViewportPosition(row_index) + (self.rowHeight(row_index) - 1) / 2
            return x, y

        paths = []
        for link in self.dependencies:
            if link.reason:
                continue
            predecessors = [i for i, row in enumerate(rows) if row.item_id == link.predecessor]
            successors = [i for i, row in enumerate(rows) if row.item_id == link.successor]
            pairs = [
                (a, b)
                for a in predecessors
                for b in successors
                if rows[a].section_id == rows[b].section_id
            ]
            if not pairs and predecessors and successors:
                pairs = [(predecessors[0], successors[0])]
            for a, b in pairs:
                end_day, start_day = rows[a].end_day, rows[b].start_day
                if end_day is None or start_day is None:
                    continue
                start, end = endpoint(a, end_day, True), endpoint(b, start_day, False)
                bounds = self.viewport().rect()
                if all(
                    0 <= x <= bounds.width() and 0 <= y < bounds.height() for x, y in (start, end)
                ):
                    paths.append(connector_points(start, end))
        return tuple(paths)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().text().color()
        painter.setPen(QPen(color, 1.5))
        for path in self.dependency_paths():
            painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in path]))
            x, y = path[-1]
            painter.setBrush(color)
            painter.drawPolygon(
                QPolygonF([QPointF(x, y), QPointF(x - 6, y - 4), QPointF(x - 6, y + 4)])
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.end()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()
