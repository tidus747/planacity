"""Theme-aware calendar controls shared by required and optional date editors."""

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPalette, QShowEvent, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget, QToolButton, QWidget

from planacity.ui.icons import svg_icon
from planacity.ui.theme import COLORS, Theme


class PlanacityCalendar(QCalendarWidget):
    """Refresh native calendar details from the inherited Planacity palette."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dateCalendar")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Replace native header colors and arrows after Qt applies the stylesheet."""
        self.ensurePolished()
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.Text)
        surface = palette.color(QPalette.ColorRole.Base)
        theme = Theme.DARK if surface.lightness() < 128 else Theme.LIGHT
        colors = COLORS[theme]
        accent = QColor(colors.accent)

        header = QTextCharFormat()
        header.setBackground(QColor(colors.sidebar))
        header.setForeground(QColor(colors.muted))
        header.setFontWeight(QFont.Weight.DemiBold)
        self.setHeaderTextFormat(header)

        weekend = QTextCharFormat()
        weekend.setForeground(accent)
        self.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, weekend)
        self.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, weekend)

        today = QTextCharFormat()
        today.setForeground(accent)
        today.setFontWeight(QFont.Weight.Bold)
        today.setFontUnderline(True)
        self.setDateTextFormat(QDate.currentDate(), today)

        for object_name, filename in (
            ("qt_calendar_prevmonth", "chevron-left.svg"),
            ("qt_calendar_nextmonth", "chevron-right.svg"),
        ):
            button = self.findChild(QToolButton, object_name)
            if button is not None:
                button.setIcon(svg_icon(filename, text.name()))
                button.setIconSize(QSize(18, 18))
