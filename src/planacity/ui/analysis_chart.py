"""Small accessible horizontal bars for the Overview analysis projection."""

from dataclasses import dataclass
from fractions import Fraction

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class AnalysisBar:
    """One exact chart value with an optional capacity reference."""

    label: str
    value: Fraction | None
    detail: str
    reference: Fraction | None = None
    incomplete: bool = False


class AnalysisBarChart(QWidget):
    """Draw compact bars while leaving exact values in text and the peer table."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[AnalysisBar, ...] = ()
        self.setAccessibleName("Overview analysis chart")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(96)

    def set_rows(self, rows: tuple[AnalysisBar, ...]) -> None:
        self.rows = rows
        self.setAccessibleDescription(
            "\n".join(f"{row.label}: {row.detail}" for row in rows)
            or "No analysis values are available."
        )
        self.setMinimumHeight(max(96, len(rows) * 42 + 20))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(900, max(96, len(self.rows) * 42 + 20))

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text = palette.color(palette.ColorRole.WindowText)
        muted = palette.color(palette.ColorRole.Mid)
        accent = palette.color(palette.ColorRole.Highlight)
        surface = palette.color(palette.ColorRole.Base)
        warning = QColor("#c43d4d")
        painter.setFont(self.font())

        if not self.rows:
            painter.setPen(text)
            painter.drawText(
                self.rect().adjusted(12, 12, -12, -12),
                Qt.AlignmentFlag.AlignCenter,
                "No values are available for this analysis.",
            )
            painter.end()
            return

        known = tuple(row for row in self.rows if row.value is not None)
        positive = max(
            (
                value
                for row in known
                for value in (row.value, row.reference)
                if value is not None and value > 0
            ),
            default=Fraction(1),
        )
        negative = max(
            (-row.value for row in known if row.value is not None and row.value < 0),
            default=Fraction(),
        )
        total = positive + negative
        label_width = min(220, max(150, self.width() // 5))
        detail_width = min(260, max(190, self.width() // 4))
        bar_left = label_width + 20
        bar_width = max(100, self.width() - bar_left - detail_width - 30)
        zero_x = bar_left + bar_width * float(negative / total)

        for index, row in enumerate(self.rows):
            top = 10 + index * 42
            center = top + 17
            label_rect = QRectF(8, top, label_width, 34)
            detail_rect = QRectF(self.width() - detail_width - 8, top, detail_width, 34)
            painter.setPen(text)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                painter.fontMetrics().elidedText(
                    row.label,
                    Qt.TextElideMode.ElideRight,
                    int(label_rect.width()),
                ),
            )
            painter.drawText(
                detail_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                painter.fontMetrics().elidedText(
                    row.detail,
                    Qt.TextElideMode.ElideRight,
                    int(detail_rect.width()),
                ),
            )
            painter.setPen(QPen(muted, 1))
            painter.drawLine(int(zero_x), top + 4, int(zero_x), top + 30)
            if row.value is None:
                unknown_rect = QRectF(bar_left, center - 8, bar_width, 16)
                painter.setPen(QPen(muted, 1, Qt.PenStyle.DotLine))
                painter.setBrush(QBrush(surface, Qt.BrushStyle.Dense4Pattern))
                painter.drawRoundedRect(unknown_rect, 3, 3)
                continue

            if row.reference is not None and row.reference > 0:
                reference_width = bar_width * float(row.reference / total)
                reference_rect = QRectF(zero_x, center - 10, reference_width, 20)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(muted, 2, Qt.PenStyle.DashLine))
                painter.drawRoundedRect(reference_rect, 4, 4)

            value_width = bar_width * float(abs(row.value) / total)
            value_left = zero_x if row.value >= 0 else zero_x - value_width
            value_rect = QRectF(value_left, center - 7, value_width, 14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent if row.value >= 0 else warning)
            painter.drawRoundedRect(value_rect, 3, 3)
            if row.reference is not None and row.reference >= 0 and row.value > row.reference:
                reference_width = bar_width * float(row.reference / total)
                overflow = QRectF(
                    zero_x + reference_width,
                    center - 7,
                    value_width - reference_width,
                    14,
                )
                painter.setBrush(QBrush(warning, Qt.BrushStyle.Dense4Pattern))
                painter.drawRect(overflow)
            if row.incomplete:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(warning, 1, Qt.PenStyle.DotLine))
                painter.drawRoundedRect(value_rect.adjusted(-2, -2, 2, 2), 4, 4)

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(accent, 1, Qt.PenStyle.DashLine))
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.end()
