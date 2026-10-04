"""Qt model invariants and real keyboard editing over a shared document."""

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QModelIndex, Qt
from PySide6.QtTest import QAbstractItemModelTester, QTest
from PySide6.QtWidgets import QCalendarWidget, QLineEdit, QMessageBox

from planacity.persistence.project import restore_backup
from planacity.planning.work_items import move_work_item, remove_work_item
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.plan_model import PlanModel
from planacity.ui.session import Session


def example():
    return restore_backup(
        Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    )


def test_tree_indexes_edits_and_structural_changes(app):
    session = Session()
    model = PlanModel(session)
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning)
    assert tester.model() is model
    plan = example()
    session.document.new(plan)
    session.changed.emit()
    assert model.rowCount() == len(plan.children(None)) == 6
    epic = model.index(0, 0)
    assert model.parent(epic) == QModelIndex()
    task = model.index(1, 0, epic)
    assert model.parent(task) == epic
    subtask = model.index(0, 0, task)
    assert model.parent(subtask) == task
    assert model.rowCount(epic.siblingAtColumn(1)) == 0
    assert not model.index(999, 0).isValid()
    assert not model.setData(task, " ")
    assert session.document.plan == plan
    assert model.setData(task, "Assemble fixture")
    assert session.document.plan.work_items[2].id == plan.work_items[2].id
    assert not model.setData(subtask.siblingAtColumn(2), "-1")
    assert model.setData(subtask.siblingAtColumn(2), "0.125")
    assert model.setData(epic.siblingAtColumn(3), "2026-09-30")
    assert "Outside" in model.data(epic.siblingAtColumn(5))
    moved = move_work_item(session.document.plan, plan.work_items[2].id, plan.work_items[4].id)
    session.apply(moved)
    task = model.index_for_id(plan.work_items[2].id)
    assert model.item(model.parent(task)).id == plan.work_items[4].id
    session.apply(
        remove_work_item(
            moved, plan.work_items[2].id, delete_descendants=True, remove_references=True
        )
    )
    assert not model.index_for_id(plan.work_items[2].id).isValid()


def test_container_estimate_is_derived_read_only_and_keeps_entered_reference(app):
    session = Session()
    plan = example()
    session.document.new(plan)
    model = PlanModel(session)
    epic = model.index_for_id(plan.work_items[0].id).siblingAtColumn(2)
    task = model.index_for_id(plan.work_items[2].id).siblingAtColumn(2)
    leaf = model.index_for_id(plan.work_items[3].id).siblingAtColumn(2)

    assert model.data(epic) == "20.75"
    assert model.data(task) == "4.25"
    assert "Derived from 1 leaf item(s): 4.25 h known" in model.data(
        task, Qt.ItemDataRole.ToolTipRole
    )
    assert "Entered reference estimate: 40 h" in model.data(task, Qt.ItemDataRole.ToolTipRole)
    assert not (model.flags(task) & Qt.ItemFlag.ItemIsEditable)
    assert model.flags(leaf) & Qt.ItemFlag.ItemIsEditable
    assert not model.setData(task, "10")
    assert session.document.plan.work_item(plan.work_items[2].id).estimate_hours == 40


def test_inline_invalid_draft_remains_editable_then_save_commits_it(
    app, window, tmp_path, monkeypatch
):
    session = window.session
    session.document.new(example())
    session.changed.emit()
    window.show_page(1)
    table, model = window.plan_page.table, window.plan_page.model
    index = model.index(0, 0)
    table.setCurrentIndex(index)
    table.edit(index)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    assert editor is not None
    editor.setText(" ")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert editor.isVisible()
    assert session.document.plan.work_items[0].title == "Test bench readiness"
    assert window.plan_page.error.text()
    editor.setText("Updated readiness")
    path = tmp_path / "edited.planacity"
    monkeypatch.setattr(window.file_actions, "_target", lambda *args: path)
    assert window.file_actions.save()
    assert not session.document.dirty
    assert session.document.plan.work_items[0].title == "Updated readiness"


def test_invalid_date_draft_stays_open_with_actionable_guidance(app, window):
    plan = example()
    window.session.document.new(plan)
    window.session.changed.emit()
    window.show_page(1)
    table, model = window.plan_page.table, window.plan_page.model
    index = model.index(0, 3)
    table.setCurrentIndex(index)
    table.edit(index)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    assert isinstance(editor, CalendarLineEdit)
    editor.setText("2026-02-30")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert editor.isVisible()
    assert editor.text() == "2026-02-30"
    assert window.session.document.plan.work_items[0].start == plan.work_items[0].start
    assert window.plan_page.error.text() == "Enter dates as YYYY-MM-DD."
    editor.setText("2026-10-02")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert window.session.document.plan.work_items[0].start == date(2026, 10, 2)
    assert window.plan_page.error.text() == ""
    window.session.document.saved_plan = window.session.document.plan


def test_inline_date_calendar_selects_and_commits_iso_date(app, window):
    plan = example()
    window.session.document.new(plan)
    window.session.changed.emit()
    try:
        window.show_page(1)
        table, model = window.plan_page.table, window.plan_page.model
        index = model.index(0, 4)
        table.setCurrentIndex(index)
        table.edit(index)
        app.processEvents()
        editor = table.findChild(CalendarLineEdit)
        assert editor is not None
        editor.calendar_action.trigger()
        app.processEvents()
        calendar = editor.findChild(QCalendarWidget)
        assert calendar is not None and calendar.isVisible()
        assert calendar.objectName() == "dateCalendar"
        assert editor.property("calendarOpen")
        calendar.clicked.emit(QDate(2026, 10, 3))
        app.processEvents()
        assert window.session.document.plan.work_items[0].end == date(2026, 10, 3)
        assert model.data(index, Qt.ItemDataRole.EditRole) == "2026-10-03"
        assert window.plan_page.error.text() == ""

        table.setCurrentIndex(index)
        table.edit(index)
        app.processEvents()
        clear_editor = next(
            candidate for candidate in table.findChildren(CalendarLineEdit) if candidate.isVisible()
        )
        clear_editor.clear()
        QTest.keyClick(clear_editor, Qt.Key.Key_Return)
        app.processEvents()
        assert window.session.document.plan.work_items[0].end is None
        assert model.data(index, Qt.ItemDataRole.EditRole) == ""
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_delete_cancellation_and_confirmation_preserve_other_work(app, window, monkeypatch):
    plan = example()
    window.session.document.new(plan)
    window.session.changed.emit()
    window.plan_page.table.setCurrentIndex(window.plan_page.model.index(0, 0))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    window.plan_page.delete_item()
    assert window.session.document.plan == plan
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.plan_page.delete_item()
    remaining = window.session.document.plan
    assert len(remaining.work_items) == len(plan.work_items) - 4
    assert remaining.people == plan.people
    window.session.document.saved_plan = remaining


def test_escape_cancels_invalid_inline_draft(app, window):
    plan = example()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    table = window.plan_page.table
    index = window.plan_page.model.index(0, 0)
    table.setCurrentIndex(index)
    table.edit(index)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    editor.setText(" ")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    app.processEvents()
    assert window.session.document.plan == plan
    assert not window.session.document.dirty
    assert window.plan_page.error.text() == ""
