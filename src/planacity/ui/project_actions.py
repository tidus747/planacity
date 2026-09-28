"""File dialogs, explicit unsaved-change decisions, and project metadata forms."""

import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
)

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.persistence.project import export_backup, load_project, restore_backup
from planacity.ui.calendars import PlanacityCalendar
from planacity.ui.forms import validated_form
from planacity.ui.session import Session


def _date_editor(value: date, accessible_name: str) -> QDateEdit:
    editor = QDateEdit(QDate(value.year, value.month, value.day))
    editor.setAccessibleName(accessible_name)
    editor.setDisplayFormat("yyyy-MM-dd")
    editor.setDateRange(QDate(1, 1, 1), QDate(9999, 12, 31))
    editor.setCalendarPopup(True)
    editor.setKeyboardTracking(False)
    calendar = PlanacityCalendar()
    calendar.setAccessibleName(f"{accessible_name} calendar")
    editor.setCalendarWidget(calendar)
    return editor


def _date_value(editor: QDateEdit) -> date:
    value = editor.date()
    return date(value.year(), value.month(), value.day())


class ProjectActions:
    def __init__(self, window: QMainWindow, session: Session) -> None:
        self.window, self.session = window, session
        self.flush_edit: Callable[[], bool] = lambda: True
        menu = window.menuBar().addMenu("&File")
        self.actions: dict[str, QAction] = {}
        for name, title, shortcut, callback in (
            ("new", "&New plan...", "Ctrl+N", self.new),
            ("open", "&Open...", "Ctrl+O", self.open),
            ("save", "&Save", "Ctrl+S", self.save),
            ("save_as", "Save &as...", "Ctrl+Shift+S", self.save_as),
            ("properties", "Plan &properties...", "", self.properties),
            ("export", "Export JSON &backup...", "", self.export),
            ("restore", "&Restore JSON backup...", "", self.restore),
        ):
            action = menu.addAction(title)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.actions[name] = action
        menu.addSeparator()
        quit_action = menu.addAction("E&xit")
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(window.close)
        session.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        for name in ("save", "save_as", "properties", "export"):
            self.actions[name].setEnabled(self.session.document.plan is not None)

    def error(self, problem: Exception) -> None:
        QMessageBox.warning(
            self.window,
            "Project operation failed",
            f"{problem}\n\nThe current plan is still available. "
            "Check the file and folder permissions, "
            "or choose another path.",
        )

    def guard(self) -> bool:
        if not self.flush_edit():
            return False
        if not self.session.document.dirty:
            return True
        choice = QMessageBox.warning(
            self.window,
            "Unsaved changes",
            "Save changes to the current plan?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return choice == QMessageBox.StandardButton.Discard

    def _metadata(self, plan: ProgramPlan | None) -> ProgramPlan | None:
        name = QLineEdit(plan.name if plan else "")
        description = QPlainTextEdit(plan.description if plan else "")
        start = _date_editor(
            plan.horizon.start if plan else date.today(), "Planning horizon start date"
        )
        end = _date_editor(plan.horizon.end if plan else date.today(), "Planning horizon end date")

        def build() -> ProgramPlan:
            horizon = PlanningHorizon(_date_value(start), _date_value(end))
            if plan:
                return replace(
                    plan, name=name.text(), description=description.toPlainText(), horizon=horizon
                )
            return ProgramPlan(
                name=name.text(), description=description.toPlainText(), horizon=horizon
            )

        return validated_form(
            self.window,
            "Plan properties" if plan else "New Program Plan",
            [
                ("&Name", name),
                ("&Description", description),
                ("&Start (YYYY-MM-DD)", start),
                ("&End (YYYY-MM-DD)", end),
            ],
            build,
        )

    def new(self) -> None:
        if not self.flush_edit():
            return
        plan = self._metadata(None)
        if plan is not None and self.guard():
            self.session.document.new(plan)
            self.session.changed.emit()

    def properties(self) -> None:
        if not self.flush_edit():
            return
        if self.session.document.plan:
            plan = self._metadata(self.session.document.plan)
            if plan is not None:
                self.session.apply(plan)

    def open(self) -> None:
        if not self.flush_edit():
            return
        name, _ = QFileDialog.getOpenFileName(
            self.window, "Open Program Plan", "", "Planacity (*.planacity)"
        )
        if not name:
            return
        try:
            load_project(Path(name))
            if self.guard():
                self.session.document.open(Path(name))
                self.session.changed.emit()
        except (OSError, ValueError, sqlite3.Error) as error:
            self.error(error)

    def _target(self, title: str, extension: str) -> Path | None:
        name, _ = QFileDialog.getSaveFileName(
            self.window,
            title,
            "",
            f"Planacity (*{extension})",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not name:
            return None
        path = Path(name)
        if not path.suffix:
            path = path.with_suffix(extension)
        if (
            path.exists()
            and QMessageBox.question(
                self.window,
                "Replace file?",
                f"Replace '{path}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return None
        return path

    def save(self) -> bool:
        if not self.flush_edit():
            return False
        if self.session.document.path is None:
            return self.save_as()
        return self._save(self.session.document.path)

    def save_as(self) -> bool:
        if not self.flush_edit():
            return False
        path = self._target("Save Program Plan", ".planacity")
        return self._save(path) if path is not None else False

    def _save(self, path: Path) -> bool:
        try:
            self.session.document.save(path)
            self.session.changed.emit()
            return True
        except (OSError, ValueError, sqlite3.Error) as error:
            self.error(error)
            return False

    def export(self) -> None:
        if not self.flush_edit():
            return
        plan = self.session.document.plan
        if plan is None:
            return
        path = self._target("Export JSON backup", ".json")
        if path is None:
            return
        try:
            active = self.session.document.path
            if active is not None and (
                path.resolve() == active.resolve()
                or (path.exists() and active.exists() and path.samefile(active))
            ):
                raise ValueError(
                    "Choose a different path for the JSON backup; this is the active project."
                )
            export_backup(plan, path)
            self.window.statusBar().showMessage(f"Backup exported to {path}", 5000)
        except (OSError, ValueError) as error:
            self.error(error)

    def restore(self) -> None:
        if not self.flush_edit():
            return
        name, _ = QFileDialog.getOpenFileName(
            self.window, "Restore JSON backup", "", "JSON backup (*.json)"
        )
        if not name:
            return
        try:
            plan = restore_backup(Path(name))
            if self.guard():
                self.session.document.new(plan)
                self.session.changed.emit()
        except (OSError, ValueError) as error:
            self.error(error)
