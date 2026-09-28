"""CSV import/export entry points and computed changes from the source baseline."""

from pathlib import Path

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QWidget,
)

from planacity.integrations.jira.csv_io import DATE_FORMATS, read_csv
from planacity.integrations.jira.export import (
    DEFAULT_HEADERS,
    EXPORT_FIELDS,
    ExportOptions,
    export_csv,
)
from planacity.persistence.project import export_text
from planacity.planning.changes import work_changes
from planacity.ui.forms import validated_form
from planacity.ui.import_wizard import ImportWizard
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.session import Session


class ImportPage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__("Import and export", "Bring Jira work into your local Program Plan.")
        self.session = session
        panel = Panel("Jira CSV")
        panel.content.addWidget(
            label(
                "Create or open a plan first. Choose a UTF-8 CSV, map its "
                "fields and people, then review before importing."
            )
        )
        self.delimiter = QComboBox()
        for name, value in (("Comma", ","), ("Semicolon", ";"), ("Tab", "\t")):
            self.delimiter.addItem(name, value)
        self.delimiter.setAccessibleName("CSV delimiter")
        panel.content.addWidget(self.delimiter)
        self.import_button = QPushButton("Import Jira CSV...")
        self.import_button.clicked.connect(self.import_file)
        panel.content.addWidget(self.import_button)
        self.export_button = QPushButton("Export Jira CSV...")
        self.export_button.clicked.connect(self.export_file)
        panel.content.addWidget(self.export_button)
        panel.content.addWidget(
            label(
                "Imported source cells stay in the project. Export includes "
                "work structure, hours, dates, original status and external "
                "assignees. WorkGroups, relationships, and unmapped columns "
                "are not exported. Keep a JSON backup for the complete plan."
            )
        )
        panel.content.addWidget(
            label(
                "Re-import reconciliation and Jira API access are not supported. "
                "Removing local work does not delete Jira issues."
            )
        )
        self.content.addWidget(panel)
        self.content.addStretch()
        session.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.import_button.setEnabled(self.session.document.plan is not None)
        self.export_button.setEnabled(self.session.document.plan is not None)

    def import_file(self) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Jira CSV", "", "CSV (*.csv);;All files (*)"
        )
        if not filename:
            return
        try:
            path = Path(filename)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                table = read_csv(stream.read(), self.delimiter.currentData())
            wizard = ImportWizard(plan, table, path.name, self, self.session.document.path)
            if wizard.exec() == QDialog.DialogCode.Accepted and wizard.candidate is not None:
                self.session.apply(wizard.candidate)
            wizard.deleteLater()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot import CSV", str(error))

    def export_file(self) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        headers = [QLineEdit(header) for header in DEFAULT_HEADERS]
        units, dates = QComboBox(), QComboBox()
        units.addItems(["seconds", "hours"])
        dates.addItems(DATE_FORMATS)
        fields: list[tuple[str, QWidget]] = [
            (field.title(), edit) for field, edit in zip(EXPORT_FIELDS, headers, strict=True)
        ]
        fields.extend([("Estimate units", units), ("Date format", dates)])
        options = validated_form(
            self,
            "Export Jira CSV",
            fields,
            lambda: ExportOptions(
                tuple(edit.text() for edit in headers),
                units.currentText(),
                dates.currentText(),
                self.delimiter.currentData(),
            ),
        )
        if options is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Jira CSV", "plan.csv", "CSV (*.csv)"
        )
        if not filename:
            return
        try:
            target = Path(filename)
            active = self.session.document.path
            if active is not None and (
                target.resolve() == active.resolve()
                or (target.exists() and target.samefile(active))
            ):
                raise ValueError("Choose a different path; CSV cannot replace the active project.")
            if target.suffix.lower() != ".csv":
                raise ValueError("Choose a filename ending in .csv.")
            export_text(export_csv(plan, options), target)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot export CSV", str(error))


class ChangesPage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__("Changes", "Compare planned work with the preserved imported baseline.")
        self.session = session
        self.notice = label("")
        self.content.addWidget(self.notice)
        self.view = QTreeView()
        self.view.setRootIsDecorated(False)
        self.model = QStandardItemModel(self)
        self.view.setModel(self.model)
        self.content.addWidget(self.view, 1)
        session.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.model.clear()
        self.model.setHorizontalHeaderLabels(
            ["Change", "External reference", "Work item", "Fields"]
        )
        plan = self.session.document.plan
        if plan is None or not plan.imports:
            self.notice.setText(
                "Import a CSV to establish a baseline. Manual plans have no imported baseline."
            )
            return
        changes = work_changes(plan)
        self.notice.setText(
            f"{len(changes)} changed items. Removed rows do not delete Jira issues. "
            "Roster, groups, and relationships are outside this work comparison."
        )
        for change in changes:
            row = [
                QStandardItem(value)
                for value in (change.kind, change.reference, change.title, ", ".join(change.fields))
            ]
            for item in row:
                item.setEditable(False)
            self.model.appendRow(row)
        for column in range(3):
            self.view.resizeColumnToContents(column)
