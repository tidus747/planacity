"""Program Calendar editor behavior, validation, persistence, and themes."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox
from test_calendar_settings import calendar_plan
from test_editor_forms import accept, drive_dialog
from test_sprints import sprint_plan

from planacity.domain import CalendarEvent, CalendarEventKind, PlanningHorizon, Sprint
from planacity.planning.calendar_events import add_calendar_event
from planacity.planning.sprints import add_sprint, assign_work_to_sprint
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


@pytest.mark.parametrize("theme", list(Theme))
def test_calendar_manages_sprints_assignments_and_roundtrip(
    app, window, theme, monkeypatch, tmp_path
):
    plan, first, second, task, undated = sprint_plan()
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(4)
    page = window.calendar_page
    try:
        assert page.sprint_model.rowCount() == 0
        assert page.assignment_model.rowCount() == 2
        assert page.assignment_model.item(0, 3).text() == "Unassigned"
        assert page.assignment_model.item(1, 4).text() == "Unassigned"
        assert not page.sprint_table.grab().isNull()

        def create(form):
            editors = _editors(form)
            assert isinstance(editors["Sprint start"], CalendarLineEdit)
            editors["Sprint name"].setText(first.name)
            editors["Sprint start"].setText(str(first.period.start))
            editors["Sprint end"].setText(str(first.period.end))
            editors["Sprint external reference"].setText(first.external_reference)
            group = next(
                combo
                for combo in form.findChildren(QComboBox)
                if combo.accessibleName() == "Sprint WorkGroup scope"
            )
            group.setCurrentIndex(group.findData(str(first.work_group_id)))
            accept(form)

        drive_dialog(app, page.add_sprint_button.click, create)
        created = window.session.document.plan.sprints[0]
        assert created.name == first.name
        assert created.work_group_id == first.work_group_id
        assert page.sprint_model.item(0, 3).text() == "Flight"

        page.assignment_table.setCurrentIndex(page.assignment_model.index(0, 0))

        def assign(form):
            choice = next(
                combo
                for combo in form.findChildren(QComboBox)
                if combo.accessibleName() == "Assigned sprint"
            )
            choice.setCurrentIndex(choice.findData(str(created.id)))
            accept(form)

        drive_dialog(app, page.assign_button.click, assign)
        assignment = window.session.document.plan.sprint_assignments[0]
        assert assignment.work_item_id == task.id
        assert page.assignment_model.item(0, 3).text() == first.name
        assert page.assignment_model.item(0, 4).text() == "Within sprint dates"

        overlapping = Sprint(name=second.name, period=second.period)
        window.session.apply(add_sprint(window.session.document.plan, overlapping))
        assert page.sprint_model.rowCount() == 2
        assert "Overlaps" in page.sprint_model.item(0, 5).text()

        def reassign(form):
            choice = next(
                combo
                for combo in form.findChildren(QComboBox)
                if combo.accessibleName() == "Assigned sprint"
            )
            choice.setCurrentIndex(choice.findData(str(overlapping.id)))
            accept(form)

        page.assignment_table.setCurrentIndex(page.assignment_model.index(0, 0))
        drive_dialog(app, page.assign_button.click, reassign)
        assert window.session.document.plan.sprint_assignments[0].id == assignment.id
        assert page.assignment_model.item(0, 3).text() == second.name
        assert page.assignment_model.item(0, 4).text() == "Work outside sprint dates"

        page.unassign_button.click()
        assert window.session.document.plan.sprint_assignments == ()
        assert page.assignment_model.item(0, 3).text() == "Unassigned"

        page.sprint_table.setCurrentIndex(page.sprint_model.index(0, 0))
        selected = page.selected_sprint_id()

        def edit(form):
            _editors(form)["Sprint name"].setText("Iteration Alpha")
            accept(form)

        drive_dialog(app, page.edit_sprint_button.click, edit)
        assert next(
            value for value in window.session.document.plan.sprints if value.id == selected
        ).name == ("Iteration Alpha")

        current = window.session.document.plan
        path = tmp_path / "sprint-calendar.planacity"
        window.session.document.save(path)
        window.session.document.open(path)
        window.session.changed.emit()
        assert window.session.document.plan == current

        page.sprint_table.setCurrentIndex(page.sprint_model.index(0, 0))
        deleting_id = page.selected_sprint_id()
        window.session.apply(
            assign_work_to_sprint(window.session.document.plan, deleting_id, task.id)
        )
        page.sprint_table.setCurrentIndex(page.sprint_model.index(0, 0))
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
        page.delete_sprint_button.click()
        assert len(window.session.document.plan.sprints) == 2
        assert len(window.session.document.plan.sprint_assignments) == 1
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        page.delete_sprint_button.click()
        assert len(window.session.document.plan.sprints) == 1
        assert window.session.document.plan.sprint_assignments == ()
        assert window.session.document.plan.work_items == plan.work_items
        assert undated.id in {item.id for item in window.session.document.plan.work_items}
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_sprint_forms_reject_invalid_and_stale_drafts(app, window):
    plan, _, _, task, _ = sprint_plan()
    window.session.apply(plan)
    window.show_page(4)
    page = window.calendar_page
    try:

        def invalid(form):
            editors = _editors(form)
            editors["Sprint name"].setText("Iteration")
            editors["Sprint start"].setText("2027-01-10")
            editors["Sprint end"].setText("2027-01-01")
            accept(form)
            assert form.isVisible()
            assert any(
                value.accessibleName() == "Validation error" and value.text()
                for value in form.findChildren(QLabel)
            )
            form.reject()

        drive_dialog(app, page.add_sprint_button.click, invalid)
        assert window.session.document.plan.sprints == ()

        def stale(form):
            _editors(form)["Sprint name"].setText("Iteration")
            window.session.apply(replace(plan, name="Concurrent change"))
            accept(form)
            assert form.isVisible()
            assert any(
                "plan changed" in value.text().lower() for value in form.findChildren(QLabel)
            )
            form.reject()

        drive_dialog(app, page.add_sprint_button.click, stale)
        assert window.session.document.plan.name == "Concurrent change"

        first = Sprint(name="Sprint 1", period=plan.horizon)
        window.session.apply(add_sprint(window.session.document.plan, first))
        page.assignment_table.setCurrentIndex(page.assignment_model.index(0, 0))

        def stale_assignment(form):
            choice = next(
                combo
                for combo in form.findChildren(QComboBox)
                if combo.accessibleName() == "Assigned sprint"
            )
            choice.setCurrentIndex(choice.findData(str(first.id)))
            window.session.apply(replace(window.session.document.plan, description="Changed"))
            accept(form)
            assert form.isVisible()
            form.reject()

        drive_dialog(app, page.assign_button.click, stale_assignment)
        assert not any(
            value.work_item_id == task.id
            for value in window.session.document.plan.sprint_assignments
        )
    finally:
        window.session.document.saved_plan = window.session.document.plan
