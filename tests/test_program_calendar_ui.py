"""Program Calendar editor behavior, validation, persistence, and themes."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox
from test_calendar_settings import calendar_plan
from test_editor_forms import accept, drive_dialog

from planacity.domain import CalendarEvent, CalendarEventKind, PlanningHorizon
from planacity.planning.calendar_events import add_calendar_event
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.theme import Theme


def _editors(form):
    return {editor.accessibleName(): editor for editor in form.findChildren(QLineEdit)}


@pytest.mark.parametrize("theme", list(Theme))
def test_program_calendar_add_edit_delete_and_roundtrip(app, window, theme, monkeypatch, tmp_path):
    plan = calendar_plan()
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(4)
    page = window.calendar_page
    try:
        assert page.model.rowCount() == 0
        assert page.add_button.isEnabled()
        assert "No shared events yet" in page.empty_state.text()

        def add_event(form):
            editors = _editors(form)
            assert isinstance(editors["Event start"], CalendarLineEdit)
            categories = form.findChild(QComboBox)
            assert {categories.itemData(index) for index in range(categories.count())} == {
                kind.value for kind in CalendarEventKind
            }
            accept(form)
            assert form.isVisible()
            assert any(
                "name" in widget.text().lower()
                for widget in form.findChildren(QLabel)
                if widget.accessibleName() == "Validation error"
            )
            editors["Event name"].setText("Customer visit")
            categories.setCurrentIndex(categories.findData(CalendarEventKind.CUSTOMER_VISIT.value))
            editors["Event start"].setText("2026-09-27")
            editors["Event end"].setText("2026-09-28")
            editors["Unavailable share"].setText("0")
            preview = next(
                value
                for value in form.findChildren(QLabel)
                if value.accessibleName() == "Event impact preview"
            )
            assert "Context only" in preview.text()
            assert "Partly outside horizon" in preview.text()
            accept(form)

        drive_dialog(app, page.add_button.click, add_event)
        event = window.session.document.plan.calendar_events[0]
        assert page.model.rowCount() == 1
        assert page.model.item(0, 0).text() == "Customer visit"
        assert page.model.item(0, 4).text() == "No capacity reduction"
        assert page.model.item(0, 5).text() == "Partly outside horizon; Context only"
        assert page.table.isVisible()

        earlier = CalendarEvent(
            name="Public holiday",
            kind=CalendarEventKind.PUBLIC_HOLIDAY,
            period=PlanningHorizon(date(2026, 9, 20), date(2026, 9, 20)),
            unavailable_fraction=Decimal(1),
        )
        window.session.apply(add_calendar_event(window.session.document.plan, earlier))
        assert page.model.item(0, 0).text() == "Public holiday"
        assert page.model.item(0, 4).text() == "100% unavailable"
        assert page.model.item(0, 5).text() == "Outside horizon"

        row = 1
        page.table.setCurrentIndex(page.model.index(row, 0))

        def edit_event(form):
            editors = _editors(form)
            editors["Event name"].setText("Customer readiness visit")
            editors["Unavailable share"].setText("0.25")
            accept(form)

        drive_dialog(app, page.edit_button.click, edit_event)
        changed = next(
            value for value in window.session.document.plan.calendar_events if value.id == event.id
        )
        assert changed.id == event.id
        assert changed.name == "Customer readiness visit"
        assert changed.unavailable_fraction == Decimal("0.25")
        assert page.model.item(1, 4).text() == "25% unavailable"

        window.show_page(3)
        assert Decimal(window.people_page.model.item(0, 5).text()) == Decimal("5.70")
        window.show_page(4)

        current = window.session.document.plan
        path = tmp_path / "program-calendar.planacity"
        window.session.document.save(path)
        window.session.document.open(path)
        window.session.changed.emit()
        assert window.session.document.plan == current
        assert page.model.rowCount() == 2

        page.table.setCurrentIndex(page.model.index(1, 0))
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        page.delete_button.click()
        assert page.model.rowCount() == 2
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        page.delete_button.click()
        assert page.model.rowCount() == 1
        assert window.session.document.plan.imports == plan.imports
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_program_calendar_rejects_invalid_and_stale_drafts(app, window):
    plan = calendar_plan()
    window.session.apply(plan)
    window.show_page(4)
    page = window.calendar_page
    try:

        def invalid(form):
            editors = _editors(form)
            editors["Event name"].setText("Review")
            editors["Event start"].setText("2026-10-02")
            editors["Event end"].setText("2026-10-01")
            editors["Unavailable share"].setText("1.1")
            accept(form)
            assert form.isVisible()
            error = next(
                value
                for value in form.findChildren(QLabel)
                if value.accessibleName() == "Validation error"
            )
            assert error.text()
            form.reject()

        drive_dialog(app, page.add_button.click, invalid)
        assert window.session.document.plan.calendar_events == ()

        def stale(form):
            editors = _editors(form)
            editors["Event name"].setText("Review")
            window.session.apply(replace(plan, name="Concurrent change"))
            accept(form)
            assert form.isVisible()
            assert any(
                "plan changed" in value.text().lower() for value in form.findChildren(QLabel)
            )
            form.reject()

        drive_dialog(app, page.add_button.click, stale)
        assert window.session.document.plan.name == "Concurrent change"
        assert window.session.document.plan.calendar_events == ()
    finally:
        window.session.document.saved_plan = window.session.document.plan
