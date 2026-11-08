"""The offline guide is reachable, copyable, and saveable without plan access."""

from datetime import date
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.ui.planning_guide import AboutDialog, PlanningGuideDialog


def test_guide_dialog_displays_identifiers_and_read_only_contract(app, window):
    dialog = PlanningGuideDialog(window)

    assert dialog.identifier_labels["Application"].text() == (
        f"Application: {dialog.guide.application_version}"
    )
    assert dialog.identifier_labels["JSON schema"].text() == "JSON schema: 14"
    assert dialog.identifier_labels["Guide revision"].text() == "Guide revision: 1"
    assert dialog.instructions.isReadOnly()
    assert dialog.instructions.toPlainText() == dialog.guide.instructions
    assert dialog.instructions.accessibleName() == "Planning guide instructions"
    assert "Structural validation does not prove" in dialog.workflow.text()
    dialog.deleteLater()


def test_copy_instructions_uses_exact_contract_and_never_plan_data(app, window):
    plan = ProgramPlan(
        name="Confidential Zephyr",
        description="Private customer payload",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
    )
    window.session.document.plan = plan
    window.session.document.saved_plan = plan
    before = window.session.document.plan
    dirty = window.session.document.dirty
    dialog = PlanningGuideDialog(window)
    dialog.show()

    QTest.mouseClick(dialog.copy_button, Qt.MouseButton.LeftButton)

    copied = QApplication.clipboard().text()
    assert copied == dialog.guide.instructions
    assert "Confidential Zephyr" not in copied
    assert "Private customer payload" not in copied
    assert window.session.document.plan is before
    assert window.session.document.dirty is dirty
    assert dialog.status.text() == "Instructions copied. No planning data was included."
    dialog.reject()
    dialog.deleteLater()


def test_save_guide_adds_markdown_extension_and_preserves_document(
    app, window, tmp_path, monkeypatch
):
    plan = ProgramPlan(
        name="Private plan",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
    )
    window.session.document.plan = plan
    window.session.document.saved_plan = plan
    target = tmp_path / "guide"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    dialog = PlanningGuideDialog(window)

    dialog.save_guide()

    saved = target.with_suffix(".md")
    assert saved.read_text(encoding="utf-8") == dialog.guide.instructions
    assert window.session.document.plan is plan
    assert dialog.status.text() == f"Guide saved to {saved}"
    dialog.deleteLater()


def test_save_cancellation_and_declined_replacement_change_nothing(
    app, window, tmp_path, monkeypatch
):
    dialog = PlanningGuideDialog(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))

    dialog.save_guide()

    assert tuple(tmp_path.iterdir()) == ()
    existing = tmp_path / "guide.md"
    existing.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(existing), ""))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    dialog.save_guide()

    assert existing.read_text(encoding="utf-8") == "keep"
    dialog.deleteLater()


def test_save_error_is_actionable_and_keeps_dialog_open(app, window, tmp_path, monkeypatch):
    target = tmp_path / "blocked.md"
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))

    def fail_write(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "write_text", fail_write)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, message: warnings.append((title, message)),
    )
    dialog = PlanningGuideDialog(window)
    dialog.show()

    dialog.save_guide()

    assert dialog.isVisible()
    assert warnings[0][0] == "Planning guide could not be saved"
    assert str(target) in warnings[0][1]
    assert "permissions" in warnings[0][1]
    assert not target.exists()
    dialog.reject()
    dialog.deleteLater()


def test_help_and_about_use_the_same_guide_entry_point(app, window, monkeypatch):
    import planacity.ui.main_window as main_window

    opened: list[object] = []
    monkeypatch.setattr(main_window, "show_planning_guide", opened.append)
    monkeypatch.setattr(main_window, "show_about", lambda parent: opened.append("about"))

    window.planning_guide_action.trigger()
    window.about_action.trigger()

    assert opened == [window, "about"]
    assert window.planning_guide_action.shortcut() == QKeySequence(
        QKeySequence.StandardKey.HelpContents
    )

    about_opened: list[object] = []
    about = AboutDialog(window, about_opened.append)
    about.show()
    QTest.mouseClick(about.guide_button, Qt.MouseButton.LeftButton)
    assert about_opened == [about]
    assert about.guide.application_version
    QTest.keyClick(about, Qt.Key.Key_Escape)
    assert not about.isVisible()
    about.deleteLater()
