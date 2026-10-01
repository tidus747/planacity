"""Real allocation dialogs, draft cancellation, filtering, and deletion previews."""

from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QLabel, QLineEdit, QMessageBox
from test_allocation_settings import allocated_plan
from test_editor_forms import accept, drive_dialog

from planacity.domain import WorkCalendar
from planacity.domain.estimate_units import EstimateUnit
from planacity.planning.estimate_units import set_estimate_preferences
from planacity.ui.allocations import AllocationDialog
from planacity.ui.theme import Theme


@pytest.fixture
def loaded(app, window):
    plan = allocated_plan()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    app.processEvents()
    yield window
    window.session.document.saved_plan = window.session.document.plan


def save(dialog):
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)


def hours_form(value, person=None):
    def interact(dialog):
        if person is not None:
            dialog.findChild(QComboBox).setCurrentIndex(person)
        dialog.findChild(QLineEdit).setText(value)
        accept(dialog)

    return interact


@pytest.mark.parametrize("theme", list(Theme))
def test_filtered_plan_edits_exact_hours_validates_and_saves_once(app, loaded, theme):
    window = loaded
    window.set_theme(theme, persist=False)
    original = window.session.document.plan
    page = window.plan_page
    page.search.setText("Integration")
    page.table.setCurrentIndex(page.model.index_for_id(original.work_items[1].id))

    def interact(dialog):
        assert isinstance(dialog, AllocationDialog)
        assert "Allocated: 100 h" in dialog.summary.text()
        dialog.table.setCurrentIndex(dialog.model.index(0, 0))

        def edit(form):
            field = form.findChild(QLineEdit)
            field.setText("-1")
            accept(form)
            assert form.isVisible()
            field.setText("65.125")
            accept(form)

        drive_dialog(app, dialog.edit_button.click, edit)
        assert dialog.candidate.allocations[0].id == original.allocations[0].id
        assert "Remaining: -5.125 h" in dialog.summary.text()
        assert "exceed the estimate" in dialog.summary.text()
        assert window.session.document.plan is original
        drive_dialog(app, dialog.add_button.click, hours_form("2.5", 2))
        assert len(dialog.candidate.allocations) == 3
        dialog.remove_button.click()
        assert len(dialog.candidate.allocations) == 2
        assert window.session.document.plan is original
        save(dialog)

    drive_dialog(app, page.allocation_button.click, interact)
    updated = window.session.document.plan
    assert updated.allocations[0].hours == Decimal("65.125")
    assert updated.allocations[1] == original.allocations[1]
    assert updated.work_items == original.work_items
    assert page.search.text() == "Integration"
    assert page.model.item(page.table.currentIndex()).id == original.work_items[1].id
    assert "Allocated: 105.125 h" in page.detail.text()


def test_cancel_discards_add_edit_and_remove_drafts(app, loaded):
    window = loaded
    original = window.session.document.plan
    dialog = AllocationDialog(window, window.session, original.work_items[1].id)
    dialog.show()
    dialog.table.setCurrentIndex(dialog.model.index(0, 0))
    drive_dialog(app, dialog.edit_button.click, hours_form("75"))
    drive_dialog(app, dialog.add_button.click, hours_form("5", 2))
    dialog.remove_button.click()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert window.session.document.plan is original
    assert not window.session.document.dirty


def test_missing_estimate_zero_and_duplicate_person_are_explicit(app, loaded):
    window = loaded
    plan = window.session.document.plan
    dialog = AllocationDialog(window, window.session, plan.work_items[2].id)
    dialog.show()
    assert "Missing estimate" in dialog.summary.text()
    assert "Remaining: unknown" in dialog.summary.text()
    drive_dialog(app, dialog.add_button.click, hours_form("0", 0))
    assert "No positive allocation" in dialog.summary.text()

    def duplicate(form):
        form.findChild(QLineEdit).setText("2")
        accept(form)
        assert form.isVisible()
        assert any("same work/person pair" in label.text() for label in form.findChildren(QLabel))
        form.findChild(QComboBox).setCurrentIndex(1)
        accept(form)

    drive_dialog(app, dialog.add_button.click, duplicate)
    save(dialog)
    assert len(window.session.document.plan.allocations) == 4
    assert window.session.document.plan.work_items[2].estimate_hours is None


def test_allocations_always_use_hours_even_when_plan_displays_days(app, loaded):
    window = loaded
    calendar = WorkCalendar(name="Reference", weekday_hours=(Decimal(6),) * 5 + (Decimal(0),) * 2)
    plan = replace(window.session.document.plan, work_calendars=(calendar,))
    plan = set_estimate_preferences(plan, EstimateUnit.DAYS, calendar.id)
    window.session.apply(plan)
    dialog = AllocationDialog(window, window.session, plan.work_items[1].id)
    dialog.show()
    dialog.table.setCurrentIndex(dialog.model.index(0, 0))
    drive_dialog(app, dialog.edit_button.click, hours_form("2"))
    save(dialog)
    assert window.session.document.plan.allocations[0].hours == 2
    assert window.plan_page.model.headerData(2, Qt.Orientation.Horizontal) == "Estimate (d)"


def test_empty_roster_and_stale_document_have_actionable_guidance(app, loaded):
    window = loaded
    plan = replace(window.session.document.plan, people=(), allocations=())
    window.session.apply(plan)
    dialog = AllocationDialog(window, window.session, plan.work_items[1].id)
    dialog.show()
    assert not dialog.add_button.isEnabled()
    assert "Add roster members" in dialog.error.text()
    newer = replace(plan, name="Changed elsewhere")
    window.session.apply(newer)
    save(dialog)
    assert dialog.isVisible()
    assert "plan changed" in dialog.error.text()
    assert window.session.document.plan is newer
    dialog.reject()


def test_invalid_inline_draft_blocks_allocation_dialog(app, loaded):
    page = loaded.plan_page
    index = page.model.index_for_id(loaded.session.document.plan.work_items[1].id)
    page.table.setCurrentIndex(index)
    page.table.edit(index)
    app.processEvents()
    editor = page.table.findChild(QLineEdit)
    editor.setText(" ")
    page.allocation_button.click()
    assert app.activeModalWidget() is None
    assert editor.isVisible()
    assert page.error.text()
    QTest.keyClick(editor, Qt.Key.Key_Escape)


def test_hidden_descendant_allocations_are_in_delete_preview(app, loaded, monkeypatch):
    window = loaded
    plan = window.session.document.plan
    page = window.plan_page
    page.search.setText("Program")
    page.table.setCurrentIndex(page.model.index_for_id(plan.work_items[0].id))
    prompts = []

    def cancel(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", cancel)
    page.delete_item()
    assert "1 work item(s) hidden" in prompts[0]
    assert "2 work allocation(s)" in prompts[0]
    assert window.session.document.plan is plan
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_item()
    assert not window.session.document.plan.allocations
    assert window.session.document.plan.work_items == (plan.work_items[2],)


def test_person_removal_previews_allocations_and_preserves_other_people(app, loaded, monkeypatch):
    window = loaded
    original = window.session.document.plan
    window.show_page(3)
    page = window.people_page
    page.table.setCurrentIndex(page.model.index(0, 0))
    prompts = []

    def cancel(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", cancel)
    page.edit("remove")
    assert "1 work allocation(s)" in prompts[0]
    assert window.session.document.plan is original
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.edit("remove")
    assert window.session.document.plan.allocations == (original.allocations[1],)
