"""Document replacement, keyboard shortcuts and dialog decisions cannot discard drafts silently."""

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from planacity.persistence.project import export_backup, load_project, restore_backup, save_project


@pytest.fixture
def populated(window):
    plan = restore_backup(
        Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    )
    window.session.document.new(plan)
    window.session.changed.emit()
    yield window
    window.session.document.saved_plan = window.session.document.plan


def test_cancel_new_open_restore_and_close_preserves_draft(populated, tmp_path, monkeypatch):
    window = populated
    before = window.session.document.plan
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Cancel)
    monkeypatch.setattr(window.file_actions, "_metadata", lambda *args: replace(before, name="New"))
    window.file_actions.new()
    path = tmp_path / "other.planacity"
    save_project(replace(before, name="Other"), path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.file_actions.open()
    backup = tmp_path / "backup.json"
    export_backup(replace(before, name="Backup"), backup)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(backup), ""))
    window.file_actions.restore()
    assert not window.close()
    assert window.session.document.plan == before
    assert window.session.document.dirty and window.session.document.path is None


def test_save_cancel_or_failure_prevents_replacing_document(populated, monkeypatch, tmp_path):
    window = populated
    before = window.session.document.plan
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(window.file_actions, "_target", lambda *args: None)
    assert not window.file_actions.guard()
    errors = []
    monkeypatch.setattr(window.file_actions, "error", errors.append)
    monkeypatch.setattr(
        window.file_actions, "_target", lambda *args: tmp_path / "absent" / "plan.planacity"
    )
    assert not window.file_actions.guard()
    assert errors
    assert window.session.document.plan == before and window.session.document.dirty


def test_keyboard_save_close_reopen_continue(populated, app, monkeypatch, tmp_path):
    window = populated
    path = tmp_path / "program.planacity"
    monkeypatch.setattr(window.file_actions, "_target", lambda *args: path)
    window.activateWindow()
    app.processEvents()
    QTest.keyClick(window, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert path.exists()
    assert not window.session.document.dirty
    assert "*" not in window.windowTitle()
    assert load_project(path) == window.session.document.plan
    assert window.close()
    window.show()
    window.session.document.new(replace(window.session.document.plan, name="Discard this draft"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Discard)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.file_actions.open()
    model = window.plan_page.model
    assert model.setData(model.index(0, 0), "Continue working")
    assert window.session.document.dirty
    assert window.file_actions.save()
    assert load_project(path).work_items[0].title == "Continue working"


def test_invalid_open_and_restore_do_not_prompt_discard(populated, monkeypatch, tmp_path):
    window = populated
    before = window.session.document.plan
    bad = tmp_path / "bad.planacity"
    bad.write_bytes(b"broken")
    errors = []
    monkeypatch.setattr(window.file_actions, "error", errors.append)
    monkeypatch.setattr(window.file_actions, "guard", lambda: pytest.fail("Must validate first"))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(bad), ""))
    window.file_actions.open()
    window.file_actions.restore()
    assert len(errors) == 2
    assert window.session.document.plan == before and window.session.document.dirty
    # Restore normal teardown guard after asserting neither operation called it.
    monkeypatch.setattr(window.file_actions, "guard", lambda: True)


def test_json_export_cannot_overwrite_active_project(populated, monkeypatch, tmp_path):
    path = tmp_path / "program.planacity"
    populated.session.document.save(path)
    before = path.read_bytes()
    monkeypatch.setattr(populated.file_actions, "_target", lambda *args: path)
    errors = []
    monkeypatch.setattr(populated.file_actions, "error", errors.append)
    populated.file_actions.export()
    assert errors and path.read_bytes() == before


def test_save_as_and_backup_restore_states(populated, monkeypatch, tmp_path):
    window = populated
    first, second, backup = (
        tmp_path / name for name in ("first.planacity", "second.planacity", "backup.json")
    )
    window.session.document.save(first)
    before = first.read_bytes()
    updated = replace(window.session.document.plan, name="Second project")
    window.session.apply(updated)
    monkeypatch.setattr(window.file_actions, "_target", lambda *args: second)
    assert window.file_actions.save_as()
    assert window.session.document.path == second and not window.session.document.dirty
    assert first.read_bytes() == before
    monkeypatch.setattr(window.file_actions, "_target", lambda *args: backup)
    window.file_actions.export()
    assert window.session.document.path == second and not window.session.document.dirty
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(backup), ""))
    window.file_actions.restore()
    assert window.session.document.plan == updated
    assert window.session.document.path is None and window.session.document.dirty


def test_overwrite_declined_or_file_dialog_cancelled(populated, monkeypatch, tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("valuable data", encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    populated.file_actions.export()
    assert path.read_text(encoding="utf-8") == "valuable data"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    assert not populated.file_actions.save_as()
    assert populated.session.document.dirty and populated.session.document.path is None
