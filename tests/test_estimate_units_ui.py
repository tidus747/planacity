"""Keyboard entry, explicit settings, and safe rounding in the Plan editor."""

from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
)
from test_editor_forms import accept, drive_dialog
from test_estimate_units import unit_plan

from planacity.domain import WorkItem, WorkItemType
from planacity.domain.estimate_units import EstimateUnit
from planacity.planning.estimate_units import set_estimate_preferences
from planacity.ui.theme import Theme
from planacity.ui.work_calendars import manage_work_calendars


@pytest.fixture
def loaded(app, window):
    plan = unit_plan()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    app.processEvents()
    yield window
    window.session.document.saved_plan = window.session.document.plan


def choices(dialog):
    return {combo.accessibleName(): combo for combo in dialog.findChildren(QComboBox)}


@pytest.mark.parametrize("theme", list(Theme))
def test_settings_preview_validation_and_keyboard_estimate_entry(app, loaded, theme):
    window = loaded
    window.set_theme(theme, persist=False)
    original = window.session.document.plan

    def configure(dialog):
        controls = choices(dialog)
        controls["Estimate unit"].setCurrentIndex(1)
        accept(dialog)
        assert dialog.isVisible()
        assert any(
            "Choose a work calendar" in label.text() for label in dialog.findChildren(QLabel)
        )
        controls["Estimate reference calendar"].setCurrentIndex(1)
        assert any("1 day = 5.4 h" in label.text() for label in dialog.findChildren(QLabel))
        accept(dialog)

    drive_dialog(app, window.estimate_units_action.trigger, configure)
    assert window.session.document.plan.work_items == original.work_items
    model, table = window.plan_page.model, window.plan_page.table
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Estimate (d)"
    index = model.index(0, 2)
    assert model.data(index) == "5"
    assert "Stored estimate: 27 h" in model.data(index, Qt.ItemDataRole.ToolTipRole)
    table.setCurrentIndex(index)
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_F2)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    assert editor.text() == "5"
    editor.setText("NaN")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()
    assert editor.isVisible()
    assert window.session.document.plan.work_items == original.work_items
    editor.setText("1.25")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(100)
    assert window.session.document.plan.work_items[0].estimate_hours == Decimal("6.75")


def test_rounded_editor_noop_and_cancel_do_not_change_hours_or_dirty_state(app, loaded):
    window = loaded
    plan = unit_plan(("7", "7", "8", "0", "0", "0", "0"))
    plan = replace(plan, work_items=(replace(plan.work_items[0], estimate_hours=Decimal("1.000")),))
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, plan.work_calendars[0].id)
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    model, table = window.plan_page.model, window.plan_page.table
    index = model.index(0, 2)
    assert model.data(index).startswith("~")
    table.setCurrentIndex(index)
    table.edit(index)
    app.processEvents()
    editor = table.findChild(QLineEdit)
    assert editor.text() == "1.000 h"
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(100)
    assert window.session.document.plan is plan
    assert not window.session.document.dirty

    def cancel(dialog):
        choices(dialog)["Estimate unit"].setCurrentIndex(2)
        dialog.reject()

    drive_dialog(app, window.estimate_units_action.trigger, cancel)
    assert window.session.document.plan is plan
    assert not window.session.document.dirty


def test_container_rollup_uses_display_units_without_replacing_reference_estimate(app, loaded):
    window = loaded
    plan = window.session.document.plan
    parent = WorkItem(title="Program", kind=WorkItemType.EPIC, estimate_hours=Decimal("99"))
    children = tuple(
        WorkItem(
            title=f"Leaf {number}",
            kind=WorkItemType.TASK,
            parent_id=parent.id,
            estimate_hours=Decimal("27"),
        )
        for number in (1, 2)
    )
    plan = replace(plan, work_items=(parent, *children))
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, plan.work_calendars[0].id)
    window.session.apply(plan)
    index = window.plan_page.model.index_for_id(parent.id).siblingAtColumn(2)
    assert window.plan_page.model.data(index) == "10"
    tooltip = window.plan_page.model.data(index, Qt.ItemDataRole.ToolTipRole)
    assert "54 h known" in tooltip
    assert "Entered reference estimate: 99 h" in tooltip
    assert plan.work_item(parent.id).estimate_hours == 99


def test_invalid_open_editor_blocks_unit_settings(app, loaded):
    window = loaded
    page = window.plan_page
    index = page.model.index(0, 2)
    page.table.setCurrentIndex(index)
    page.table.edit(index)
    app.processEvents()
    editor = page.table.findChild(QLineEdit)
    editor.setText("-1")
    window.estimate_units_action.trigger()
    app.processEvents()
    assert app.activeModalWidget() is None
    assert editor.isVisible()
    assert page.error.text()
    QTest.keyClick(editor, Qt.Key.Key_Escape)


def test_reference_calendar_delete_is_blocked_with_recovery_guidance(app, loaded, monkeypatch):
    window = loaded
    plan = window.session.document.plan
    plan = set_estimate_preferences(plan, EstimateUnit.WEEKS, plan.work_calendars[0].id)
    window.session.apply(plan)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))

    def remove(dialog):
        dialog.findChild(QListWidget).setCurrentRow(0)
        next(b for b in dialog.findChildren(QPushButton) if b.text() == "&Delete...").click()
        assert "Planning -> Estimate units" in messages[0]
        dialog.reject()

    drive_dialog(app, lambda: manage_work_calendars(window, window.session), remove)
    assert window.session.document.plan is plan


def test_dialog_rejects_stale_plan_and_units_action_disabled_without_plan(app, window):
    assert not window.estimate_units_action.isEnabled()
    plan = unit_plan()
    window.session.document.new(plan)
    window.session.changed.emit()
    try:

        def changed(dialog):
            window.session.apply(replace(plan, name="Changed elsewhere"))
            choices(dialog)["Estimate unit"].setCurrentIndex(2)
            choices(dialog)["Estimate reference calendar"].setCurrentIndex(1)
            accept(dialog)
            assert dialog.isVisible()
            assert any("plan changed" in label.text() for label in dialog.findChildren(QLabel))

        drive_dialog(app, window.estimate_units_action.trigger, changed)
        assert window.session.document.plan.name == "Changed elsewhere"
        assert window.session.document.plan.estimate_preferences.unit == EstimateUnit.HOURS
    finally:
        window.session.document.saved_plan = window.session.document.plan
