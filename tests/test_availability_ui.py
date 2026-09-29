"""Real availability forms, previews, cancellation, and persisted People totals."""

from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
)
from test_calendar_settings import calendar_plan
from test_editor_forms import accept, drive_dialog

from planacity.ui.availability import edit_availability
from planacity.ui.theme import Theme


@pytest.mark.parametrize("theme", list(Theme))
def test_availability_workflow(app, window, theme, monkeypatch, tmp_path):
    plan = calendar_plan()
    person = plan.people[0]
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(3)
    page = window.people_page
    page.table.setCurrentIndex(page.model.index(0, 0))
    try:
        assert page.model.item(0, 5).text() == "6.0"

        def half(form):
            editors = form.findChildren(QLineEdit)
            accept(form)
            assert form.isVisible()
            assert any(
                "Enter an unavailable" in label.text() for label in form.findChildren(QLabel)
            )
            editors[0].setText("bad")
            editors[2].setText("0.5")
            accept(form)
            assert form.isVisible()
            editors[0].setText("2026-09-28")
            preview = form.findChild(QPlainTextEdit).toPlainText()
            assert "Available: 3.00 h" in preview
            accept(form)

        def manager(dialog):
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "&Add...")
            drive_dialog(app, button.click, half)
            assert dialog.findChild(QListWidget).count() == 1

        drive_dialog(app, page.availability_button.click, manager)
        event = window.session.document.plan.availability_events[0]
        assert page.model.item(0, 4).text() == "3.00"
        assert page.model.item(0, 5).text() == "3.00"
        before = window.session.document.plan

        def cancel(form):
            form.findChildren(QLineEdit)[2].setText("1")
            assert "Available: 0.0 h" in form.findChild(QPlainTextEdit).toPlainText()
            form.reject()

        drive_dialog(
            app, lambda: edit_availability(page, window.session, person.id, event.id), cancel
        )
        assert window.session.document.plan is before

        def quarter(form):
            form.findChildren(QLineEdit)[2].setText("0.25")
            accept(form)

        drive_dialog(
            app, lambda: edit_availability(page, window.session, person.id, event.id), quarter
        )
        assert window.session.document.plan.availability_events[0].id == event.id
        assert len(window.session.document.plan.availability_events) == 1
        assert Decimal(page.model.item(0, 5).text()) == Decimal("4.5")

        def full(form):
            form.findChildren(QLineEdit)[2].setText("1")
            preview = form.findChild(QPlainTextEdit).toPlainText()
            assert "Overlaps use the largest share" in preview
            assert "Entry 1" in preview and "Entry 2" in preview
            accept(form)

        drive_dialog(app, lambda: edit_availability(page, window.session, person.id), full)
        assert page.model.item(0, 6).text() == "1"
        assert Decimal(page.model.item(0, 5).text()) == 0
        current = window.session.document.plan
        window.session.document.save(tmp_path / "availability.planacity")
        window.session.document.open(tmp_path / "availability.planacity")
        window.session.changed.emit()
        assert window.session.document.plan == current
        assert page.model.item(0, 6).text() == "1"
        assert current.imports == plan.imports

        def delete(dialog):
            listing = dialog.findChild(QListWidget)
            listing.setCurrentRow(1)
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "&Delete...")
            monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
            button.click()
            assert listing.count() == 2
            monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
            button.click()
            assert listing.count() == 1

        drive_dialog(app, page.availability_button.click, delete)
        assert Decimal(page.model.item(0, 5).text()) == Decimal("4.5")
        assert page.model.item(0, 6).text() == "0"

        def confirm_person(*args):
            assert "1 availability entries" in args[2]
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", confirm_person)
        page.edit("remove")
        assert window.session.document.plan.availability_events == ()
        assert window.session.document.plan.imports == plan.imports
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_missing_calendar_outside_horizon_and_stale_form(app, window):
    plan = replace(calendar_plan(), person_calendars=())
    person = plan.people[0]
    window.session.apply(plan)
    try:

        def outside(form):
            editors = form.findChildren(QLineEdit)
            editors[0].setText("2026-01-01")
            editors[2].setText("0.25")
            text = form.findChild(QPlainTextEdit).toPlainText()
            assert "unknown" in text
            assert "outside the horizon" in text
            accept(form)

        drive_dialog(app, lambda: edit_availability(window, window.session, person.id), outside)
        before = window.session.document.plan
        assert len(before.availability_events) == 1
        event = before.availability_events[0]

        def stale(form):
            window.session.apply(replace(before, name="Concurrent change"))
            accept(form)
            assert form.isVisible()
            assert any("plan changed" in label.text() for label in form.findChildren(QLabel))
            form.reject()

        drive_dialog(
            app, lambda: edit_availability(window, window.session, person.id, event.id), stale
        )
        assert window.session.document.plan.name == "Concurrent change"
        assert window.session.document.plan.availability_events == before.availability_events
    finally:
        window.session.document.saved_plan = window.session.document.plan
