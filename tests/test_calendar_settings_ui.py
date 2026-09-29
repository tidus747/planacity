"""Real calendar forms, confirmation, cancellation and People totals."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton
from test_calendar_settings import calendar_plan
from test_editor_forms import accept, drive_dialog

from planacity.ui.theme import Theme
from planacity.ui.work_calendars import edit_work_calendar


@pytest.mark.parametrize("theme", list(Theme))
def test_create_assign_edit_clear_and_delete_calendar(app, window, theme, monkeypatch, tmp_path):
    plan = replace(calendar_plan(), work_calendars=(), person_calendars=())
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(3)
    page = window.people_page
    page.table.setCurrentIndex(page.model.index(0, 0))
    try:
        assert page.model.item(0, 2).text() == "Unknown"

        def manager(dialog):
            add = next(
                button for button in dialog.findChildren(QPushButton) if button.text() == "&Add..."
            )

            def form(form_dialog):
                editors = form_dialog.findChildren(QLineEdit)
                editors[0].setText("Flexible")
                accept(form_dialog)
                assert form_dialog.isVisible()
                assert any(
                    "all seven days" in label.text() for label in form_dialog.findChildren(QLabel)
                )
                for editor, value in zip(
                    editors[1:], ("6.5", "6.5", "0", "6.5", "6.5", "0", "0"), strict=True
                ):
                    editor.setText(value)
                accept(form_dialog)

            drive_dialog(app, add.click, form)
            assert dialog.findChild(QListWidget).count() == 1

        drive_dialog(app, page.calendar_button.click, manager)
        calendar = window.session.document.plan.work_calendars[0]

        def assignment(dialog):
            dialog.findChild(QComboBox).setCurrentIndex(1)
            assert any(
                "26.0 nominal hours" in label.text() for label in dialog.findChildren(QLabel)
            )
            accept(dialog)

        drive_dialog(app, page.assign_button.click, assignment)
        assert page.model.item(0, 2).text() == "26.0"
        assert page.model.item(0, 3).text() == "4"
        before = window.session.document.plan
        drive_dialog(
            app, lambda: edit_work_calendar(page, window.session, calendar.id), lambda d: d.reject()
        )
        assert window.session.document.plan is before

        def zero_calendar(dialog):
            for editor in dialog.findChildren(QLineEdit)[1:]:
                editor.setText("0")
            accept(dialog)

        drive_dialog(
            app, lambda: edit_work_calendar(page, window.session, calendar.id), zero_calendar
        )
        assert page.model.item(0, 2).text() == "0"
        assert window.session.document.plan.work_calendars[0].id == calendar.id
        window.session.document.save(tmp_path / "calendars.planacity")
        window.session.document.open(tmp_path / "calendars.planacity")
        window.session.changed.emit()
        assert page.model.item(0, 2).text() == "0"

        def delete(dialog):
            listing = dialog.findChild(QListWidget)
            listing.setCurrentRow(0)
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "&Delete...")
            monkeypatch.setattr(
                QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No
            )
            button.click()
            assert len(window.session.document.plan.work_calendars) == 1

            def confirm(*args):
                assert "Alex" in args[2]
                return QMessageBox.StandardButton.Yes

            monkeypatch.setattr(QMessageBox, "question", confirm)
            button.click()

        drive_dialog(app, page.calendar_button.click, delete)
        assert window.session.document.plan.person_calendars == ()
        assert page.model.item(0, 2).text() == "Unknown"
        assert window.session.document.plan.imports == plan.imports
    finally:
        window.session.document.saved_plan = window.session.document.plan
