"""CSV import/export entry points and computed changes from the source baseline."""

from pathlib import Path
from uuid import UUID

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import ProgramPlan, WorkPriority
from planacity.integrations.jira.csv_io import DATE_FORMATS, read_csv
from planacity.integrations.jira.export import (
    DEFAULT_HEADERS,
    DEFAULT_PRIORITY_LABELS,
    EXPORT_FIELDS,
    ExportOptions,
    assignee_export_preview,
    export_csv,
    priority_export_preview,
)
from planacity.integrations.jira.profiles import dump_export_profile, load_export_profile
from planacity.persistence.project import export_text
from planacity.planning.changes import work_changes
from planacity.ui.import_wizard import ImportWizard
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.session import Session


class ExportDialog(QDialog):
    """Review explicit Jira identities and priority labels before CSV export."""

    def __init__(
        self,
        plan: ProgramPlan,
        delimiter: str,
        parent: QWidget | None = None,
        project_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.plan = plan
        self.project_path = project_path
        self.options: ExportOptions | None = None
        self.person_mappings: tuple[tuple[UUID, str], ...] = ()
        self.setWindowTitle("Export Jira CSV")
        self.resize(980, 760)
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                "Choose output columns, Jira identities, and explicit priority labels. "
                "The preview shows when original source text is preserved or a mapping "
                "is required. Display names are never exported as identities automatically."
            )
        )
        layout.addWidget(label("CSV column labels", "heading"))
        header_grid = QGridLayout()
        self.headers = [QLineEdit(header) for header in DEFAULT_HEADERS]
        for index, (field, edit) in enumerate(zip(EXPORT_FIELDS, self.headers, strict=True)):
            edit.setAccessibleName(f"{field.title()} CSV header")
            row, group = divmod(index, 2)
            header_grid.addWidget(label(field.replace("_", " ").title()), row, group * 2)
            header_grid.addWidget(edit, row, group * 2 + 1)
        header_grid.setColumnStretch(1, 1)
        header_grid.setColumnStretch(3, 1)
        layout.addLayout(header_grid)
        form = QFormLayout()
        self.units, self.dates = QComboBox(), QComboBox()
        self.delimiters = QComboBox()
        self.units.addItems(["seconds", "hours"])
        self.dates.addItems(DATE_FORMATS)
        for name, value in (("Comma", ","), ("Semicolon", ";"), ("Tab", "\t")):
            self.delimiters.addItem(name, value)
        self.delimiters.setCurrentIndex(self.delimiters.findData(delimiter))
        form.addRow("Estimate units", self.units)
        form.addRow("Date format", self.dates)
        form.addRow("Delimiter", self.delimiters)
        priority_row = QHBoxLayout()
        self.priority_labels: dict[WorkPriority, QLineEdit] = {}
        for priority, default in DEFAULT_PRIORITY_LABELS:
            edit = QLineEdit(default)
            edit.setAccessibleName(f"{priority.value.title()} target priority label")
            edit.setPlaceholderText(priority.value.title())
            self.priority_labels[priority] = edit
            priority_row.addWidget(label(priority.value.title()))
            priority_row.addWidget(edit)
        form.addRow("Priority target labels", priority_row)
        required_ids = tuple(
            dict.fromkeys(
                row.person_id
                for row in assignee_export_preview(plan)
                if row.result == "External identity required" and row.person_id is not None
            )
        )
        self.person_labels: dict[UUID, QLineEdit] = {}
        for person_id in required_ids:
            person = plan.person(person_id)
            edit = QLineEdit()
            edit.setAccessibleName(f"{person.name} Jira identity")
            edit.setPlaceholderText("Required before export")
            self.person_labels[person.id] = edit
            form.addRow(f"Jira identity - {person.name}", edit)
        profiles = QHBoxLayout()
        for text, callback in (
            ("Load profile...", self.load_profile),
            ("Save profile...", self.save_profile),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            profiles.addWidget(button)
        form.addRow(profiles)
        layout.addLayout(form)
        self.notice = label("")
        self.notice.setAccessibleName("Export assignee and priority preview status")
        layout.addWidget(self.notice)
        self.preview_model = QStandardItemModel(self)
        self.preview_model.setHorizontalHeaderLabels(
            [
                "Reference",
                "Work item",
                "Planacity assignee",
                "CSV assignee",
                "Assignee result",
                "Planacity priority",
                "CSV priority",
                "Priority result",
            ]
        )
        self.preview = QTreeView()
        self.preview.setRootIsDecorated(False)
        self.preview.setMinimumHeight(150)
        self.preview.setModel(self.preview_model)
        layout.addWidget(self.preview, 1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for edit in (*self.headers, *self.priority_labels.values(), *self.person_labels.values()):
            edit.textChanged.connect(self.refresh_preview)
        self.units.currentTextChanged.connect(self.refresh_preview)
        self.dates.currentTextChanged.connect(self.refresh_preview)
        self.delimiters.currentIndexChanged.connect(self.refresh_preview)
        self.refresh_preview()

    def _current_options(self) -> ExportOptions:
        return ExportOptions(
            tuple(edit.text() for edit in self.headers),
            self.units.currentText(),
            self.dates.currentText(),
            self.delimiters.currentData(),
            tuple((priority, edit.text()) for priority, edit in self.priority_labels.items()),
        )

    def refresh_preview(self) -> None:
        self.preview_model.removeRows(0, self.preview_model.rowCount())
        try:
            options = self._current_options()
            mappings = tuple(
                (person_id, edit.text()) for person_id, edit in self.person_labels.items()
            )
            priority_rows = priority_export_preview(self.plan, options)
            assignee_rows = assignee_export_preview(self.plan, mappings)
            unresolved = 0
            missing_identities = 0
            for assignee, priority in zip(assignee_rows, priority_rows, strict=True):
                values = (
                    priority.reference,
                    priority.title,
                    assignee.planacity_assignee,
                    assignee.csv_assignee or "Blank",
                    assignee.result,
                    priority.planacity_priority,
                    priority.csv_priority or "Blank",
                    priority.result,
                )
                row = [QStandardItem(value) for value in values]
                for cell in row:
                    cell.setEditable(False)
                self.preview_model.appendRow(row)
                unresolved += priority.result == "Unresolved source preserved"
                missing_identities += assignee.result == "External identity required"
            self.notice.setText(
                f"{len(priority_rows)} rows reviewed. {missing_identities} assignee identity "
                f"mapping(s) required; {unresolved} unresolved priority source value(s) "
                "will be preserved unchanged."
            )
            self.person_mappings = mappings
            self.options = options if not missing_identities else None
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                not missing_identities
            )
            for column in range(8):
                self.preview.resizeColumnToContents(column)
        except ValueError as error:
            self.options = None
            self.person_mappings = ()
            self.notice.setText(f"Cannot export: {error}")
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def accept(self) -> None:
        self.refresh_preview()
        if self.options is not None:
            super().accept()

    def save_profile(self) -> None:
        try:
            options = self._current_options()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save export mapping profile", "jira-export.json", "JSON (*.json)"
            )
            if not filename:
                return
            target = Path(filename)
            if target.suffix.lower() != ".json":
                raise ValueError("Choose a filename ending in .json.")
            active = self.project_path
            if active is not None and (
                target.resolve() == active.resolve()
                or (target.exists() and target.samefile(active))
            ):
                raise ValueError("A profile cannot replace the active project.")
            export_text(dump_export_profile(options), target)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot save export profile", str(error))

    def load_profile(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load export mapping profile", "", "JSON (*.json)"
        )
        if not filename:
            return
        try:
            options = load_export_profile(Path(filename).read_text(encoding="utf-8"))
            for edit, value in zip(self.headers, options.headers, strict=True):
                edit.setText(value)
            self.units.setCurrentText(options.estimate_unit)
            self.dates.setCurrentText(options.date_format)
            self.delimiters.setCurrentIndex(self.delimiters.findData(options.delimiter))
            for priority, value in options.priority_labels:
                self.priority_labels[priority].setText(value)
            self.refresh_preview()
        except (OSError, ValueError) as error:
            self.notice.setText(str(error))


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
                "work structure, hours, dates, explicitly mapped priority, original "
                "status and external assignees. WorkGroups, relationships, and unmapped columns "
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
        dialog = ExportDialog(
            plan,
            self.delimiter.currentData(),
            self,
            self.session.document.path,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.options is None:
            dialog.deleteLater()
            return
        options = dialog.options
        person_mappings = dialog.person_mappings
        dialog.deleteLater()
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
            export_text(export_csv(plan, options, person_mappings), target)
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
