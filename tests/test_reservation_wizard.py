"""Both entry points share validated previews and one atomic confirmation."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_editor_forms import drive_dialog
from test_reservation_preview import preview_plan

from planacity.ui.reservations import ReservationWizard, hours_text
from planacity.ui.theme import Theme


def fill(dialog):
    assert isinstance(dialog, ReservationWizard)
    dialog.name.setText("Meetings")
    dialog.hours.setText("1")
    dialog.interval.setText("1")
    dialog.people.setCurrentRow(0)
    dialog.people.setFocus()
    QTest.keyClick(dialog.people, Qt.Key.Key_Space)


@pytest.mark.parametrize("theme", list(Theme))
def test_create_edit_cancel_delete_and_save(app, window, theme, tmp_path):
    plan = replace(preview_plan(), reservation_rules=())
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(3)
    try:

        def create(dialog):
            assert not dialog.confirm.isEnabled()
            dialog.next.click()
            assert dialog.error.text()
            fill(dialog)
            assert "1 h x 1 people = 1 h" in dialog.total.text()
            dialog.start.setText("bad")
            dialog.next.click()
            assert "YYYY-MM-DD" in dialog.error.text()
            dialog.start.setText(str(plan.horizon.start))
            dialog.next.click()
            assert window.session.document.plan is plan
            text = dialog.preview.toPlainText()
            assert "before program events and work allocations" in text
            assert "eligible days 5/5" in text
            assert "remaining 5 h" in text
            dialog.back.click()
            assert not dialog.confirm.isEnabled()
            dialog.next.click()
            dialog.confirm.click()

        drive_dialog(app, window.reserve_action.trigger, create)
        saved = window.session.document.plan
        rule = saved.reservation_rules[0]
        assert rule.hours_per_person == 1
        assert saved.imports == plan.imports
        assert window.session.document.dirty

        def cancel(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            dialog.hours.setText("2")
            dialog.next.click()
            assert "remaining 4 h" in dialog.preview.toPlainText()
            dialog.reject()

        drive_dialog(app, window.people_page.reserve_button.click, cancel)
        assert window.session.document.plan is saved

        def edit(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            assert dialog.identifier == rule.id
            dialog.hours.setText("2")
            dialog.next.click()
            dialog.confirm.click()

        drive_dialog(app, window.reserve_action.trigger, edit)
        updated = window.session.document.plan
        assert len(updated.reservation_rules) == 1
        assert updated.reservation_rules[0].id == rule.id
        assert updated.reservation_rules[0].hours_per_person == 2
        path = tmp_path / "reserved.planacity"
        window.session.document.save(path)
        window.session.document.open(path)
        window.session.changed.emit()
        assert window.session.document.plan == updated

        def cancel_delete(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            dialog.delete_button.click()
            dialog.reject()

        drive_dialog(app, window.reserve_action.trigger, cancel_delete)
        assert window.session.document.plan == updated

        def delete(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            dialog.delete_button.click()
            assert "Delete reservation: Meetings" in dialog.preview.toPlainText()
            assert window.session.document.plan.reservation_rules
            dialog.confirm.click()

        drive_dialog(app, window.people_page.reserve_button.click, delete)
        assert window.session.document.plan.reservation_rules == ()
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_stale_preview_cannot_overwrite_changed_plan(app, window):
    plan = preview_plan()
    window.session.apply(plan)
    try:

        def stale(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            dialog.next.click()
            assert dialog.confirm.isEnabled()
            window.session.apply(replace(plan, name="Changed elsewhere"))
            dialog.confirm.click()
            assert "plan changed" in dialog.error.text()
            assert not dialog.confirm.isEnabled()
            dialog.reject()

        drive_dialog(app, window.reserve_action.trigger, stale)
        assert window.session.document.plan.name == "Changed elsewhere"
        assert window.session.document.plan.reservation_rules == plan.reservation_rules
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_multi_person_hours_overlaps_and_overloads_are_visible(app, window):
    from planacity.domain import Person
    from planacity.planning.calendar_settings import assign_calendar

    plan = preview_plan()
    other = Person(name="Morgan")
    plan = assign_calendar(
        replace(plan, people=(*plan.people, other)), other.id, plan.work_calendars[0].id
    )
    window.session.apply(plan)
    try:

        def preview(dialog):
            fill(dialog)
            dialog.people.item(1).setCheckState(Qt.CheckState.Checked)
            dialog.name.setText("Front office")
            dialog.hours.setText("10")
            assert "10 h x 2 people = 20 h" in dialog.total.text()
            dialog.next.click()
            text = dialog.preview.toPlainText()
            assert "Alex" in text and "Morgan" in text
            assert "Overlap" in text and "Over capacity" in text
            assert "remaining -5 h" in text and "remaining -4 h" in text
            dialog.reject()

        drive_dialog(app, window.people_page.reserve_button.click, preview)
        assert window.session.document.plan is plan
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_missing_calendar_blocks_save_but_not_deleting_rule(app, window):
    from uuid import uuid4

    plan = replace(preview_plan(), person_calendars=())
    remaining_rule = replace(plan.reservation_rules[0], id=uuid4(), name="Support")
    plan = replace(plan, reservation_rules=(*plan.reservation_rules, remaining_rule))
    window.session.apply(plan)
    try:

        def missing(dialog):
            dialog.rule_choice.setCurrentIndex(1)
            dialog.next.click()
            assert "Assign a work calendar" in dialog.error.text()
            assert not dialog.confirm.isEnabled()
            dialog.delete_button.click()
            assert dialog.confirm.isEnabled()
            assert "Remaining rules cannot be calculated" in dialog.preview.toPlainText()
            dialog.confirm.click()

        drive_dialog(app, window.reserve_action.trigger, missing)
        assert window.session.document.plan.reservation_rules == (remaining_rule,)
    finally:
        window.session.document.saved_plan = window.session.document.plan


@pytest.mark.parametrize(
    "value, text",
    [
        (Fraction(1, 3), "1/3"),
        (Fraction(6, 5), "1.2"),
        (Fraction(-1, 8), "-0.125"),
        (Fraction(0), "0"),
        (Fraction(Decimal("1.12345678901234567890123456789")), "1.12345678901234567890123456789"),
    ],
)
def test_display_does_not_round_exact_shares(value, text):
    assert hours_text(value) == text
