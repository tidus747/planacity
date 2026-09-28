"""Validate, correct, preview, cancel, and apply imports through real Qt widgets."""

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.integrations.jira.csv_io import read_csv
from planacity.persistence.project import load_project
from planacity.ui.import_wizard import ImportWizard
from planacity.ui.jira_pages import ChangesPage


def empty_plan():
    return ProgramPlan(
        name="Import test", horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 12, 31))
    )


def test_wizard_requires_people_then_previews_without_mutating(app):
    plan = empty_plan()
    table = read_csv("Issue key,Summary,Issue Type,Assignee\nTEST-1,Test,Task,Alice\n")
    wizard = ImportWizard(plan, table, "sample.csv")
    wizard.show()
    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.pages.currentIndex() == 1
    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.pages.currentIndex() == 1
    assert "Choose a person" in wizard.error.toPlainText()
    wizard.person_boxes["Alice"].setCurrentIndex(1)
    QTest.mouseClick(wizard.next, Qt.MouseButton.LeftButton)
    assert wizard.pages.currentIndex() == 2
    assert wizard.preview_model.item(0, 0).text() == "TEST-1"
    assert wizard.candidate.work_items[0].title == "Test"
    assert plan.work_items == ()
    wizard.reject()
    assert plan.imports == ()
    wizard.deleteLater()


def test_bad_mapping_stays_open_and_import_edit_save_reopen(window, app, tmp_path):
    window.session.document.new(empty_plan())
    window.session.changed.emit()
    table = read_csv("Issue key,Summary,Issue Type,Original Estimate\nTEST-1,Test,Task,2.5\n")
    wizard = ImportWizard(window.session.document.plan, table, "sample.csv", window)
    wizard.units.setCurrentText("hours")
    wizard.columns["title"].setCurrentIndex(0)
    wizard.advance()
    assert wizard.pages.currentIndex() == 0
    assert "Map title" in wizard.error.toPlainText()
    wizard.columns["title"].setCurrentIndex(2)
    wizard.advance()
    wizard.advance()
    assert wizard.pages.currentIndex() == 2
    wizard.go_back()
    assert wizard.candidate is None
    wizard.advance()
    wizard.advance()
    window.session.apply(wizard.candidate)
    assert window.session.document.dirty
    model = window.plan_page.model
    assert model.data(model.index(0, 6)) == "TEST-1"
    assert model.setData(model.index(0, 0), "Agreed")
    changes = window.findChild(ChangesPage)
    assert changes.model.rowCount() == 1
    assert changes.model.item(0, 0).text() == "Modified"
    path = tmp_path / "imported.planacity"
    window.session.document.save(path)
    reopened = load_project(path)
    assert reopened.work_items[0].title == "Agreed"
    assert reopened.imports[0].records[0].item.title == "Test"
    wizard.deleteLater()


def test_explicit_type_mapping_and_profile_reuse(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    path = tmp_path / "mapping.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(path), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    plan = empty_plan()
    table = read_csv("Issue key,Summary,Issue Type\nTEST-1,Investigation,Story\n")
    wizard = ImportWizard(plan, table, "story.csv")
    wizard.advance()
    wizard.advance()
    assert wizard.pages.currentIndex() == 1
    wizard.type_boxes["Story"].setCurrentIndex(2)
    wizard.advance()
    assert wizard.candidate.work_items[0].kind.value == "task"
    wizard.go_back()
    wizard.go_back()
    wizard.save_profile()
    other = ImportWizard(plan, table, "another.csv")
    other.load_profile()
    other.advance()
    assert other.type_boxes["Story"].currentData() == "task"
    other.advance()
    assert other.candidate is not None
    assert "Investigation" not in path.read_text(encoding="utf-8")
    wizard.deleteLater()
    other.deleteLater()


def test_ambiguous_profile_keeps_existing_wizard_mapping(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from planacity.integrations.jira.profiles import dump_profile

    table = read_csv("Issue key,Summary,Issue Type\nTEST-1,Test,Task\n")
    plan = empty_plan()
    wizard = ImportWizard(plan, table, "sample.csv")
    original = wizard.current_mapping()
    path = tmp_path / "ambiguous.json"
    profile = dump_profile(table.headers, original)
    path.write_text(profile[:-1] + ', "estimate_unit": "hours"}', encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(path), ""))
    wizard.load_profile()
    assert "Duplicate mapping profile field: estimate_unit" in wizard.error.toPlainText()
    assert wizard.current_mapping() == original
    assert wizard.candidate is None
    assert wizard.plan == plan
    # Correcting the file allows recovery in the same wizard.
    path.write_text(profile, encoding="utf-8")
    wizard.load_profile()
    assert not wizard.error.toPlainText()
    wizard.advance()
    wizard.advance()
    assert wizard.candidate is not None
    wizard.deleteLater()


def test_import_page_and_real_export_form(window, app, tmp_path, monkeypatch):
    from pathlib import Path

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QMessageBox

    from planacity.ui.jira_pages import ImportPage

    window.session.document.new(empty_plan())
    window.session.changed.emit()
    page = window.findChild(ImportPage)
    source = Path(__file__).resolve().parents[1] / "examples" / "jira-aurora.csv"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a: (str(source), ""))
    failures = []

    def import_dialog():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, ImportWizard)
            dialog.advance()
            for box in dialog.person_boxes.values():
                box.setCurrentIndex(1)
            dialog.advance()
            assert dialog.candidate is not None, dialog.error.toPlainText()
            dialog.advance()
        except BaseException as error:
            failures.append(error)
            dialog.reject()

    QTimer.singleShot(0, import_dialog)
    page.import_file()
    if failures:
        window.session.document.saved_plan = window.session.document.plan
        raise failures[0]
    plan = window.session.document.plan
    assert len(plan.work_items) == 4
    assert len(plan.people) == 2
    target = tmp_path / "roundtrip.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(target), ""))

    def export_dialog():
        dialog = app.activeModalWidget()
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()

    QTimer.singleShot(0, export_dialog)
    page.export_file()
    output = read_csv(target.read_text(encoding="utf-8"))
    assert len(output.rows) == 4
    assert output.rows[2][4] == output.rows[1][1]
    assert window.session.document.plan == plan
    # Even a project with an unconventional .csv extension is protected.
    active = tmp_path / "active.csv"
    window.session.document.save(active)
    before = active.read_bytes()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(active), ""))
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(a[-1]))
    QTimer.singleShot(0, export_dialog)
    page.export_file()
    assert warnings and "active project" in warnings[-1]
    assert active.read_bytes() == before
