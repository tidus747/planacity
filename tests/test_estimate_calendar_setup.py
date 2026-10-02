"""Calendar setup inside unit settings is explicit, atomic, and keyboard usable."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QPushButton
from test_editor_forms import accept, drive_dialog
from test_estimate_units import unit_plan
from test_estimate_units_ui import choices

from planacity.domain import WorkCalendar
from planacity.domain.estimate_units import EstimateUnit
from planacity.persistence.project import load_project, restore_backup, save_project
from planacity.ui.theme import Theme


@pytest.fixture
def loaded(app, window):
    window.session.document.new(unit_plan())
    window.session.document.saved_plan = window.session.document.plan
    window.session.changed.emit()
    yield window
    window.session.document.saved_plan = window.session.document.plan


def button(dialog, text):
    return next(b for b in dialog.findChildren(QPushButton) if b.text() == text)


def guidance(dialog):
    return next(
        label.text()
        for label in dialog.findChildren(QLabel)
        if label.accessibleName() == "Reference calendar guidance"
    )


def add_calendar(app, manager):
    def fill(form):
        form.findChildren(QLineEdit)[0].setText("Short week")
        for editor in form.findChildren(QLineEdit)[1:]:
            editor.setText("4" if editor.accessibleName().split()[0] == "Monday" else "0")
        accept(form)

    drive_dialog(app, button(manager, "&Add...").click, fill)
    manager.reject()


@pytest.mark.parametrize("theme", list(Theme))
@pytest.mark.parametrize("confirm", [False, True])
def test_calendar_and_units_save_together_or_cancel(app, loaded, theme, confirm, tmp_path):
    window = loaded
    window.set_theme(theme, persist=False)
    original = window.session.document.plan
    changes = []
    window.session.changed.connect(lambda: changes.append(window.session.document.plan))

    def configure(dialog):
        controls = choices(dialog)
        units, calendars = controls["Estimate unit"], controls["Estimate reference calendar"]
        assert not calendars.isEnabled()
        assert "Hours needs no reference" in guidance(dialog)
        units.setFocus()
        QTest.keyClick(units, Qt.Key.Key_Down)
        assert calendars.isEnabled()
        calendars.setCurrentIndex(1)
        selected = calendars.currentData()
        drive_dialog(
            app, button(dialog, "&Work calendars...").click, lambda m: add_calendar(app, m)
        )
        assert units.currentData() == "days"
        assert calendars.currentData() == selected
        assert calendars.count() == 3
        assert window.session.document.plan is original
        assert not changes
        calendars.setCurrentIndex(2)
        app.processEvents()
        preview = next(
            label
            for label in dialog.findChildren(QLabel)
            if label.accessibleName() == "Estimate conversion preview"
        )
        assert preview.height() >= preview.heightForWidth(preview.width())
        if confirm:
            accept(dialog)
        else:
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    if not confirm:
        assert window.session.document.plan is original
        assert not changes
        assert not window.session.document.dirty
        return
    plan = window.session.document.plan
    assert len(changes) == 1
    assert plan.estimate_preferences.unit == EstimateUnit.DAYS
    assert plan.estimate_preferences.calendar_id == plan.work_calendars[1].id
    assert plan.work_items == original.work_items
    assert plan.person_calendars == original.person_calendars
    assert plan.imports == original.imports
    path = tmp_path / "units.planacity"
    save_project(plan, path)
    restored = load_project(path)
    assert restored == plan
    window.session.document.new(restored)
    window.session.changed.emit()

    def reopened(dialog):
        assert choices(dialog)["Estimate reference calendar"].currentData() == str(
            restored.work_calendars[1].id
        )
        assert choices(dialog)["Estimate unit"].currentData() == "days"

    drive_dialog(app, window.estimate_units_action.trigger, reopened)


@pytest.mark.parametrize("example", [False, True])
@pytest.mark.parametrize("unit_index", [1, 2])
def test_missing_calendar_guides_setup_for_days_and_weeks(app, loaded, example, unit_index):
    window = loaded
    plan = (
        restore_backup(Path("examples/aurora.planacity.json"))
        if example
        else replace(unit_plan(), work_calendars=(), work_items=())
    )
    window.session.document.new(plan)
    window.session.changed.emit()

    def configure(dialog):
        controls = choices(dialog)
        units, calendars = controls["Estimate unit"], controls["Estimate reference calendar"]
        units.setCurrentIndex(unit_index)
        assert not calendars.isEnabled()
        assert "No work calendars yet" in guidance(dialog)
        accept(dialog)
        assert dialog.isVisible()
        drive_dialog(
            app, button(dialog, "&Work calendars...").click, lambda m: add_calendar(app, m)
        )
        assert calendars.isEnabled()
        assert units.currentIndex() == unit_index
        calendars.setCurrentIndex(1)
        accept(dialog)

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert window.session.document.plan.estimate_preferences.unit.value == (
        "days" if unit_index == 1 else "weeks"
    )
    assert window.session.document.plan.work_items == plan.work_items


def test_zero_hour_calendar_is_identified_and_rejected(app, loaded):
    window = loaded
    original = window.session.document.plan
    zero = WorkCalendar(name="No working days", weekday_hours=(Decimal(0),) * 7)
    window.session.apply(replace(original, work_calendars=(*original.work_calendars, zero)))

    def configure(dialog):
        controls = choices(dialog)
        controls["Estimate unit"].setCurrentIndex(2)
        calendars = controls["Estimate reference calendar"]
        assert "no working hours" in calendars.itemText(2)
        calendars.setCurrentIndex(2)
        accept(dialog)
        assert dialog.isVisible()
        assert any("working hours" in label.text() for label in dialog.findChildren(QLabel))
        calendars.setCurrentIndex(1)
        accept(dialog)

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert (
        window.session.document.plan.estimate_preferences.calendar_id
        == original.work_calendars[0].id
    )


def test_calendar_drafts_cannot_overwrite_a_changed_plan(app, loaded):
    window = loaded
    original = window.session.document.plan

    def configure(dialog):
        drive_dialog(
            app, button(dialog, "&Work calendars...").click, lambda m: add_calendar(app, m)
        )
        window.session.apply(replace(original, name="Updated elsewhere"))
        button(dialog, "&Work calendars...").click()
        assert app.activeModalWidget() is dialog
        accept(dialog)
        assert dialog.isVisible()
        assert any("plan changed" in label.text() for label in dialog.findChildren(QLabel))

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert window.session.document.plan == replace(original, name="Updated elsewhere")


def test_calendar_edit_refreshes_conversion_and_cancel_discards_edit(app, loaded):
    window = loaded
    original = window.session.document.plan

    def configure(dialog):
        controls = choices(dialog)
        controls["Estimate unit"].setCurrentIndex(2)
        controls["Estimate reference calendar"].setCurrentIndex(1)

        def manage(manager):
            manager.findChild(QListWidget).setCurrentRow(0)

            def edit(form):
                form.findChildren(QLineEdit)[1].setText("8")
                accept(form)

            drive_dialog(app, button(manager, "&Edit...").click, edit)
            manager.reject()

        drive_dialog(app, button(dialog, "&Work calendars...").click, manage)
        assert controls["Estimate reference calendar"].currentData() == str(
            original.work_calendars[0].id
        )
        assert any("1 week = 29 h" in label.text() for label in dialog.findChildren(QLabel))
        dialog.reject()

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert window.session.document.plan is original


def test_cancel_calendar_form_then_confirm_units_does_not_add_calendar(app, loaded):
    window = loaded
    original = window.session.document.plan

    def configure(dialog):
        def manage(manager):
            def cancel(form):
                form.findChildren(QLineEdit)[0].setText("Unfinished calendar")
                form.reject()

            drive_dialog(app, button(manager, "&Add...").click, cancel)
            manager.reject()

        drive_dialog(app, button(dialog, "&Work calendars...").click, manage)
        assert choices(dialog)["Estimate reference calendar"].count() == 2
        accept(dialog)

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert window.session.document.plan is original
    assert not window.session.document.dirty
