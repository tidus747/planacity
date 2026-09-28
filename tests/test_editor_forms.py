"""Exercise the real modal forms, including correction and cancellation."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QPushButton,
)

from planacity.domain import WorkItemType
from planacity.persistence.project import restore_backup


def drive_dialog(app, action, interact):
    failures = []

    def drive():
        dialog = app.activeModalWidget()
        try:
            assert dialog is not None
            interact(dialog)
        except BaseException as error:
            failures.append(error)
        finally:
            if dialog and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, drive)
    action()
    if failures:
        raise failures[0]


def accept(dialog):
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()


def test_create_plan_correct_invalid_range_then_edit_hierarchy(app, window):
    def create(dialog):
        name = dialog.findChild(QLineEdit)
        start, end = dialog.findChildren(QDateEdit)
        assert start.calendarPopup() and end.calendarPopup()
        assert start.displayFormat() == "yyyy-MM-dd"
        assert end.displayFormat() == "yyyy-MM-dd"
        name.setText("Fresh program")
        start.setDate(QDate(2026, 12, 1))
        end.setDate(QDate(2026, 11, 1))
        accept(dialog)
        assert dialog.isVisible()
        assert name.text() == "Fresh program"
        end.setDate(QDate(2027, 2, 1))
        accept(dialog)

    drive_dialog(app, window.file_actions.new, create)
    assert window.session.document.plan.horizon.end == date(2027, 2, 1)
    assert window.session.document.dirty
    for kind, title in (
        (WorkItemType.EPIC, "Epic"),
        (WorkItemType.TASK, "Task"),
        (WorkItemType.SUBTASK, "Subtask"),
    ):

        def add(dialog, title=title):
            editor = dialog.findChild(QLineEdit)
            editor.setText(title)
            accept(dialog)

        drive_dialog(app, lambda kind=kind: window.plan_page.add_item(kind), add)
    plan = window.session.document.plan
    assert len(plan.work_items) == 3
    assert plan.work_items[2].parent_id == plan.work_items[1].id
    window.session.document.saved_plan = plan


def test_people_group_and_relationship_forms(app, window):
    plan = restore_backup(
        Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    )
    window.session.document.new(plan)
    window.session.changed.emit()

    def person(dialog):
        editor = dialog.findChild(QLineEdit)
        editor.setText(" ")
        accept(dialog)
        assert dialog.isVisible()
        editor.setText("Robin")
        accept(dialog)

    drive_dialog(app, lambda: window.people_page.edit("add"), person)
    assert window.session.document.plan.people[-1].name == "Robin"

    def group_manager(manager):
        def group(dialog):
            dialog.findChild(QLineEdit).setText("Another group")
            accept(dialog)

        add_button = next(b for b in manager.findChildren(QPushButton) if b.text() == "&Add")
        drive_dialog(app, add_button.click, group)
        assert manager.findChild(QListWidget).count() == 2

    drive_dialog(app, lambda: window.plan_page.manage(True), group_manager)
    assert len(window.session.document.plan.work_groups) == 2

    def relationship_manager(manager):
        def link(dialog):
            source, kind, target = dialog.findChildren(QComboBox)
            # The initial self-link is invalid; keep the form open for correction.
            accept(dialog)
            assert dialog.isVisible()
            target.setCurrentIndex(target.count() - 1)
            accept(dialog)

        add_button = next(b for b in manager.findChildren(QPushButton) if b.text() == "&Add")
        drive_dialog(app, add_button.click, link)

    drive_dialog(app, lambda: window.plan_page.manage(False), relationship_manager)
    assert len(window.session.document.plan.relationships) == len(plan.relationships) + 1
    window.session.document.saved_plan = window.session.document.plan


def test_cancel_add_and_move_preserves_selection(app, window):
    plan = restore_backup(
        Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    )
    window.session.document.new(plan)
    window.session.changed.emit()
    task_id = plan.work_items[1].id
    index = window.plan_page.model.index_for_id(task_id)
    window.plan_page.table.setCurrentIndex(index)
    drive_dialog(app, lambda: window.plan_page.add_item(WorkItemType.SUBTASK), lambda d: d.reject())
    drive_dialog(app, window.plan_page.move_item, lambda d: d.reject())
    assert window.session.document.plan == plan
    assert window.plan_page.model.item(window.plan_page.table.currentIndex()).id == task_id
    window.session.document.saved_plan = plan


def test_renaming_group_preserves_existing_membership_order(app, window):
    plan = restore_backup(
        Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    )
    group = replace(plan.work_groups[0], epic_ids=tuple(reversed(plan.work_groups[0].epic_ids)))
    plan = replace(plan, work_groups=(group,))
    window.session.document.new(plan)
    window.session.changed.emit()

    def manager(dialog):
        dialog.findChild(QListWidget).setCurrentRow(0)
        edit_button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "&Edit")

        def edit(form):
            form.findChild(QLineEdit).setText("Renamed only")
            accept(form)

        drive_dialog(app, edit_button.click, edit)

    drive_dialog(app, lambda: window.plan_page.manage(True), manager)
    changed = window.session.document.plan.work_groups[0]
    assert changed.epic_ids == group.epic_ids
    assert changed.name == "Renamed only"
    window.session.document.saved_plan = window.session.document.plan
