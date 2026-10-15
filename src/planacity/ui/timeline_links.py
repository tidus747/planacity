"""Paint dependency connectors over the Timeline's existing schedule cells."""

from uuid import UUID

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QTableView

from planacity.planning.timeline import TimelineProjection
from planacity.planning.timeline_axis import TimelineAxis
from planacity.planning.timeline_dependencies import TimelineDependency, connector_points

CRITICAL_COLORS = {"light": "#b42318", "dark": "#ff7b72"}


class DependencyScheduleView(QTableView):
    projection: TimelineProjection | None = None
    axis: TimelineAxis | None = None
    dependencies: tuple[TimelineDependency, ...] = ()
    show_dependencies = True
    show_critical_path = False
    critical_node_ids: frozenset[UUID] = frozenset()
    critical_relationship_ids: frozenset[UUID] = frozenset()

    def _path_entries(
        self,
    ) -> tuple[tuple[TimelineDependency, tuple[tuple[float, float], ...]], ...]:
        """Return connector geometry whose actual endpoints are visible."""
        if self.axis is None or self.projection is None:
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
                    paths.append((link, connector_points(start, end)))
        return tuple(paths)

    def critical_dependency_paths(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        if not self.show_critical_path:
            return ()
        return tuple(
            path
            for link, path in self._path_entries()
            if link.relationship_id in self.critical_relationship_ids
        )

    def ordinary_dependency_paths(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        if not self.show_dependencies:
            return ()
        return tuple(
            path
            for link, path in self._path_entries()
            if not self.show_critical_path
            or link.relationship_id not in self.critical_relationship_ids
        )

    def dependency_paths(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """Return every connector currently presented by either optional layer."""
        return self.ordinary_dependency_paths() + self.critical_dependency_paths()

    def _draw_paths(
        self,
        painter: QPainter,
        paths: tuple[tuple[tuple[float, float], ...], ...],
        pen: QPen,
    ) -> None:
        painter.setPen(pen)
        painter.setBrush(pen.color())
        for path in paths:
            painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in path]))
            x, y = path[-1]
            painter.drawPolygon(
                QPolygonF([QPointF(x, y), QPointF(x - 6, y - 4), QPointF(x - 6, y + 4)])
            )
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().text().color()
        self._draw_paths(painter, self.ordinary_dependency_paths(), QPen(color, 1.5))
        theme = "dark" if self.palette().window().color().lightness() < 128 else "light"
        critical_pen = QPen(QColor(CRITICAL_COLORS[theme]), 2.5, Qt.PenStyle.DashLine)
        self._draw_paths(painter, self.critical_dependency_paths(), critical_pen)
        painter.end()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self.viewport().update()
