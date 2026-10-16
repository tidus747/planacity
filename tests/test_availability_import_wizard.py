"""Availability CSV wizard mapping, review, cancellation, and Calendar entry point."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QFileDialog

from planacity.domain import AvailabilityEvent, Person, PlanningHorizon, ProgramPlan
from planacity.integrations.availability_csv import read_availability_csv
from planacity.ui.availability_import_wizard import AvailabilityImportWizard


def plan_with_people() -> ProgramPlan:
    return ProgramPlan(
        name="Availability import",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 12, 31)),
        people=(Person(name="Alice"), Person(name="Bob")),
    )


def test_wizard_maps_people_previews_warnings_and_applies_selected(app):
    plan = plan_with_people()
    alice = plan.people[0]
    plan = replace(
        plan,
        availability_events=(
            AvailabilityEvent(
                person_id=alice.id,
                period=PlanningHorizon(date(2026, 2, 2), date(2026, 2, 2)),
                unavailable_fraction=Decimal("0.5"),
            ),
        ),
    )
    table = read_availability_csv(
        "Person,Start,End,Unavailable fraction\n"
        "Alice,2026-02-02,2026-02-03,1\n"
        "Bob,2026-03-02,2026-03-02,0.5\n"
        "Unknown,2026-03-04,2026-03-04,1\n"
    )
    wizard = AvailabilityImportWizard(plan, table, ",")
    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.pages.currentIndex() == 1
    assert wizard.person_boxes["Alice"].currentData() == str(alice.id)
    assert not wizard.person_boxes["Unknown"].currentData()

    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.pages.currentIndex() == 2
    assert wizard.preview_model.rowCount() == 3
    assert wizard.preview_model.item(0, 0).checkState() == Qt.CheckState.Unchecked
    assert "overlaps" in wizard.preview_model.item(0, 6).text()
    assert wizard.preview_model.item(1, 0).checkState() == Qt.CheckState.Checked
    assert not wizard.preview_model.item(2, 0).isCheckable()

    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.result() == QDialog.DialogCode.Accepted
    assert wizard.candidate is not None
    assert len(wizard.candidate.availability_events) == 2
    assert len(plan.availability_events) == 1
    wizard.deleteLater()


def test_wizard_cancel_and_profile_roundtrip_do_not_change_plan(app, tmp_path, monkeypatch):
    plan = plan_with_people()
    table = read_availability_csv("Employee;From;To;Share\nAlice;2026-04-01;2026-04-01;1\n", ";")
    profile = tmp_path / "availability-profile.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(profile), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(profile), ""))
    wizard = AvailabilityImportWizard(plan, table, ";")
    wizard.save_profile()
    assert '"kind": "availability-csv"' in profile.read_text(encoding="utf-8")

    other = AvailabilityImportWizard(plan, table, ";")
    for box in other.columns.values():
        box.setCurrentIndex(0)
    other.load_profile()
    assert all(box.currentData() >= 0 for box in other.columns.values())
    other.reject()
    assert other.candidate is None
    assert plan.availability_events == ()
    wizard.deleteLater()
    other.deleteLater()


def test_calendar_import_entry_applies_only_accepted_candidate(window, tmp_path, monkeypatch):
    plan = plan_with_people()
    window.session.apply(plan)
    csv_path = tmp_path / "availability.csv"
    csv_path.write_text(
        "Person,Start,End,Unavailable fraction\nAlice,2026-05-04,2026-05-04,1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(csv_path), ""))

    def accept_import(wizard):
        wizard.advance()
        wizard.advance()
        wizard.advance()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AvailabilityImportWizard, "exec", accept_import)
    window.calendar_page.import_availability()
    assert len(window.session.document.plan.availability_events) == 1
    assert window.session.document.dirty
    window.session.document.saved_plan = window.session.document.plan
