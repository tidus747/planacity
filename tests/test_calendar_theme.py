"""Calendar popup cells must fit their text under the application's table styling."""

from datetime import date

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCalendarWidget, QStyle, QStyleOptionViewItem, QTableView

from planacity.ui.forms import CalendarLineEdit
from planacity.ui.project_actions import _date_editor
from planacity.ui.theme import Theme


@pytest.mark.parametrize("picker", ["plan", "horizon"])
def test_calendar_dates_fit_after_theme_switching(app, window, picker):
    if picker == "plan":
        editor = CalendarLineEdit(window)
        editor.setText("2026-09-15")
        editor.show_calendar()
        calendar = editor.findChild(QCalendarWidget)
    else:
        editor = _date_editor(date(2026, 9, 15), "Start date")
        editor.setParent(window)
        calendar = editor.calendarWidget()
        calendar.show()
    try:
        for theme in (Theme.LIGHT, Theme.DARK, Theme.LIGHT):
            window.set_theme(theme, persist=False)
            app.processEvents()
            view = calendar.findChild(QTableView)
            # Inspect actual style-computed text bounds, not stylesheet strings.
            # Spreadsheet padding previously made several cell rectangles empty.
            for row in range(view.model().rowCount()):
                for column in range(view.model().columnCount()):
                    index = view.model().index(row, column)
                    text = str(index.data() or "")
                    if not text:
                        continue
                    option = QStyleOptionViewItem()
                    option.initFrom(view)
                    option.index = index
                    option.rect = view.visualRect(index)
                    option.text = text
                    option.features = QStyleOptionViewItem.ViewItemFeature.HasDisplay
                    bounds = view.style().subElementRect(
                        QStyle.SubElement.SE_ItemViewItemText, option, view
                    )
                    assert bounds.height() >= option.fontMetrics.height(), (theme, text, bounds)
                    assert bounds.width() >= option.fontMetrics.horizontalAdvance(text)
            calendar.setSelectedDate(QDate(2026, 9, 15))
            view.setFocus()
            QTest.keyClick(view, Qt.Key.Key_Right)
            assert calendar.selectedDate() == QDate(2026, 9, 16)
    finally:
        calendar.hide()
        if picker == "plan" and editor._calendar_menu is not None:
            editor._calendar_menu.close()
        editor.deleteLater()
        app.processEvents()
