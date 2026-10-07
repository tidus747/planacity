"""Plan and Timeline reject dependency-breaking date input without losing drafts."""

from datetime import date

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkItem,
    WorkItemType,
)
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.session import Session
from planacity.ui.timeline import TimelinePage


def guarded_plan() -> ProgramPlan:
    build = WorkItem(
        title="Build", kind=WorkItemType.TASK, start=date(2026, 1, 1), end=date(2026, 1, 4)
    )
    verify = WorkItem(
        title="Verify", kind=WorkItemType.TASK, start=date(2026, 1, 7), end=date(2026, 1, 9)
    )
    link = Relationship(
        source_id=verify.id,
        target_id=build.id,
        kind=RelationshipType.DEPENDS_ON,
    )
    return ProgramPlan(
        name="Guarded dates",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        work_items=(build, verify),
        relationships=(link,),
    )


def _boundary(view, day: date, edge: str) -> QPoint:
    axis = view.axis
    assert axis is not None
    offset = (day - axis.horizon.start).days
    column = axis.column_for_day(offset)
    period = axis.period(column)
    x = view.columnViewportPosition(column) + (
        offset - period.start_day + (edge == "end")
    ) / period.days * view.columnWidth(column)
    y = view.rowViewportPosition(0) + view.rowHeight(0) / 2
    return QPoint(round(x), round(y))


def test_plan_keyboard_conflict_keeps_editor_open_and_escape_cancels(app, window) -> None:
    plan = guarded_plan()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    table = window.plan_page.table
    item_index = window.plan_page.model.index_for_id(plan.work_items[0].id)
    end_index = item_index.siblingAtColumn(window.plan_page.source_model.END_COLUMN)
    table.setCurrentIndex(end_index)
    table.edit(end_index)
    app.processEvents()
    editor = next(
        control for control in table.findChildren(CalendarLineEdit) if control.isVisible()
    )
    editor.setText("2026-01-07")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()

    assert editor.isVisible()
    assert window.session.document.plan is plan
    assert '"Build" ends 2026-01-07' in window.plan_page.error.text()
    assert "end on or before 2026-01-06" in window.plan_page.error.text()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    app.processEvents()
    assert window.session.document.plan is plan
    assert not window.session.document.dirty


def test_timeline_keyboard_editor_checks_a_predecessor_hidden_by_filter(app) -> None:
    session = Session()
    plan = guarded_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1200, 760)
    page.show()
    page.search.setText("Verify")
    app.processEvents()
    page._select_row(0)
    failures = []

    def enter_conflict() -> None:
        try:
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QDialog)
            start, _ = dialog.findChildren(CalendarLineEdit)
            start.selectAll()
            QTest.keyClicks(start, "2026-01-04")
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Ok).click()
            assert dialog.isVisible()
            error = next(
                widget
                for widget in dialog.findChildren(QLabel)
                if widget.accessibleName() == "Validation error"
            )
            assert '"Build" ends 2026-01-04' in error.text()
            assert "start on or after 2026-01-05" in error.text()
            buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        except BaseException as error:
            failures.append(error)
            if QApplication.activeModalWidget() is not None:
                QApplication.activeModalWidget().reject()

    try:
        QTimer.singleShot(0, enter_conflict)
        page.edit_dates.click()
        assert not failures
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    ("title", "edge", "target", "boundary"),
    [
        ("Build", "end", date(2026, 1, 7), "end on or before 2026-01-06"),
        ("Verify", "start", date(2026, 1, 4), "start on or after 2026-01-05"),
    ],
)
def test_timeline_drag_rejects_both_edges_when_other_endpoint_is_hidden(
    app, title, edge, target, boundary
) -> None:
    session = Session()
    plan = guarded_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1400, 780)
    page.show()
    page.search.setText(title)
    app.processEvents()
    view = page.schedule
    item = next(work for work in plan.work_items if work.title == title)
    original_date = item.start if edge == "start" else item.end
    assert original_date is not None
    start = _boundary(view, original_date, edge)
    finish = _boundary(view, target, edge)
    try:
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), finish)
        assert "Invalid drop: Dependency constraint rejected" in page.resize_preview.text()
        assert '"Build"' in page.resize_preview.text()
        assert '"Verify"' in page.resize_preview.text()
        assert boundary in page.resize_preview.text()
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
        assert boundary in page.resize_preview.text()
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
