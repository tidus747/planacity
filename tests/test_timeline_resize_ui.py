"""Real mouse/keyboard resizing with cancellation and canonical persistence."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from test_timeline_resize import resize_plan

from planacity.persistence.project import load_project
from planacity.planning.changes import work_changes
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.jira_pages import ChangesPage
from planacity.ui.main_window import MainWindow
from planacity.ui.session import Session
from planacity.ui.timeline import TimelinePage


def boundary(view, day, edge):
    axis = view.axis
    offset = (day - axis.horizon.start).days
    col = axis.column_for_day(offset)
    period = axis.period(col)
    x = view.columnViewportPosition(col) + (
        offset - period.start_day + (edge == "end")
    ) / period.days * view.columnWidth(col)
    return QPoint(round(x), round(view.rowViewportPosition(0) + view.rowHeight(0) / 2))


@pytest.mark.parametrize("scale", ["day", "week", "month"])
@pytest.mark.parametrize("edge,target", [("end", date(2024, 2, 29)), ("start", date(2024, 2, 22))])
def test_drag_commits_once_and_survives_save_reopen(app, tmp_path, scale, edge, target):
    session = Session()
    original = resize_plan()
    session.apply(original)
    session.document.saved_plan = original
    page = TimelinePage(session)
    page.resize(2200, 850)
    page.show()
    changes = []
    session.changed.connect(lambda: changes.append(session.document.plan))
    try:
        page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
        app.processEvents()
        view = page.schedule
        item = original.work_items[0]
        start = boundary(view, getattr(item, edge), edge)
        finish = boundary(view, target, edge)
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), finish)
        assert session.document.plan is original
        assert "Proposed:" in page.resize_preview.text()
        assert "calendar days" in page.resize_preview.text()
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
        assert len(changes) == 1
        updated = session.document.plan
        assert getattr(updated.work_items[0], edge) == target
        assert updated.imports == original.imports
        assert updated.work_items[0].estimate_hours == item.estimate_hours
        assert work_changes(updated)[0].fields == (edge,)
        assert session.document.dirty
        session.document.save(tmp_path / "resized.planacity")
        assert load_project(session.document.path) == updated
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    "cancel", ["escape", "outside", "reversed", "scale", "filter", "hide", "unchanged"]
)
def test_invalid_and_cancelled_gestures_preserve_original(app, cancel):
    session = Session()
    plan = resize_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1400, 850)
    page.show()
    page.scale_box.setCurrentIndex(page.scale_box.findData("week"))
    app.processEvents()
    view = page.schedule
    start = boundary(view, plan.work_items[0].end, "end")
    finish = boundary(view, date(2024, 2, 29), "end")
    try:
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), finish)
        if cancel == "escape":
            QTest.keyClick(view, Qt.Key.Key_Escape)
        elif cancel == "outside":
            finish = QPoint(-20, -20)
        elif cancel == "reversed":
            finish = boundary(view, date(2024, 2, 18), "end")
        elif cancel == "scale":
            page.scale_box.setCurrentIndex(page.scale_box.findData("month"))
        elif cancel == "filter":
            page.search.setText("not found")
        elif cancel == "hide":
            page.hide()
        elif cancel == "unchanged":
            finish = start
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
        assert session.document.plan == plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_keyboard_dates_updates_plan_and_changes_views(app, settings):
    window = MainWindow(settings)
    original = resize_plan()
    window.session.apply(original)
    window.show()
    window.show_page(2)
    page = window.timeline_page
    page._select_row(0)
    errors = []

    def fill_dialog():
        try:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QDialog)
            editors = dialog.findChildren(CalendarLineEdit)
            editors[1].selectAll()
            QTest.keyClicks(editors[1], "2024-02-29")
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        except BaseException as error:
            errors.append(error)
            if QApplication.activeModalWidget():
                QApplication.activeModalWidget().reject()

    try:
        QTimer.singleShot(0, fill_dialog)
        page.edit_dates.click()
        assert not errors
        model = window.plan_page.model
        index = model.index_for_id(original.work_items[0].id)
        assert model.index(index.row(), 4, index.parent()).data() == "2024-02-29"
        assert work_changes(window.session.document.plan)[0].fields == ("end",)
        changes_page = window.findChild(ChangesPage)
        assert changes_page.model.item(0, 3).text() == "end"
        assert window.session.document.plan.imports == original.imports
    finally:
        window.session.document.saved_plan = window.session.document.plan
        window.close()
        window.deleteLater()
        app.processEvents()


def test_resize_after_scrolling_preserves_other_date_and_outside_warning(app):
    plan = resize_plan()
    item = replace(plan.work_items[0], start=date(2024, 1, 30))
    plan = replace(plan, work_items=(item,))
    session = Session()
    session.apply(plan)
    page = TimelinePage(session)
    page.resize(1200, 850)
    page.show()
    app.processEvents()
    view = page.schedule
    view.horizontalScrollBar().setValue(800)
    app.processEvents()
    scroll = view.horizontalScrollBar().value()
    try:
        start = boundary(view, item.end, "end")
        finish = boundary(view, date(2024, 3, 5), "end")
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), finish)
        assert "Outside planning horizon" in page.resize_preview.text()
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
        assert session.document.plan.work_items[0].start == item.start
        assert session.document.plan.work_items[0].end == date(2024, 3, 5)
        assert "outside horizon" in page.label_model.index(0, 1).data()
        assert view.horizontalScrollBar().value() == scroll
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_new_snapshot_cancels_drag_and_partial_items_have_no_handles(app):
    session = Session()
    plan = resize_plan()
    session.apply(plan)
    page = TimelinePage(session)
    page.resize(1400, 850)
    page.scale_box.setCurrentIndex(page.scale_box.findData("month"))
    page.show()
    app.processEvents()
    view = page.schedule
    start = boundary(view, plan.work_items[0].end, "end")
    try:
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        replacement = replace(plan, work_items=(replace(plan.work_items[0], start=None),))
        session.apply(replacement)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        assert session.document.plan is replacement
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        assert view._drag is None
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        assert page.edit_dates.isEnabled()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
