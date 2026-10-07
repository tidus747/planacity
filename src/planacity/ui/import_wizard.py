"""Review field mapping, people, and the complete candidate before importing."""

from pathlib import Path

from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import Person, ProgramPlan, WorkItemType, WorkPriority
from planacity.integrations.jira.csv_io import (
    DATE_FORMATS,
    FIELDS,
    CsvTable,
    Mapping,
    external_people,
    external_priorities,
    preview_import,
)
from planacity.integrations.jira.profiles import dump_profile, load_profile
from planacity.ui.pages import label

ALIASES = {
    "title": ("Summary", "Title"),
    "type": ("Issue Type", "Work Type", "Work type"),
    "reference": ("Issue key", "Issue Key", "Work item key"),
    "row_id": ("Issue ID", "Issue id", "Work item ID"),
    "parent": ("Parent", "Parent ID"),
    "estimate": ("Original Estimate",),
    "start": ("Start Date",),
    "end": ("Due Date",),
    "person": ("Assignee",),
    "status": ("Status",),
    "priority": ("Priority",),
}


class ImportWizard(QDialog):
    def __init__(
        self,
        plan: ProgramPlan,
        table: CsvTable,
        source: str,
        parent: QWidget | None = None,
        project_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Jira CSV")
        self.resize(860, 740)
        self.plan, self.table, self.source = plan, table, source
        self.project_path = project_path
        self.candidate: ProgramPlan | None = None
        self.mapping: Mapping | None = None
        self.columns: dict[str, QComboBox] = {}
        self.person_boxes: dict[str, QComboBox] = {}
        self.type_boxes: dict[str, QComboBox] = {}
        self.priority_boxes: dict[str, QComboBox] = {}
        self.profile_types: tuple[tuple[str, WorkItemType], ...] = (
            ("Epic", WorkItemType.EPIC),
            ("Task", WorkItemType.TASK),
            ("Sub-task", WorkItemType.SUBTASK),
            ("Subtask", WorkItemType.SUBTASK),
        )
        self.profile_priorities: tuple[tuple[str, WorkPriority | None], ...] = ()
        layout = QVBoxLayout(self)
        self.heading = label("1. Map CSV columns", "heading")
        layout.addWidget(self.heading)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        form_page = QWidget()
        form = QFormLayout(form_page)
        form.addRow(
            label(
                "Review detected mappings. Repeated headers include their column number. "
                "Parent values must match row ID, or external reference if row ID is unmapped."
            )
        )
        for field in FIELDS:
            box = QComboBox()
            box.addItem("Not mapped", -1)
            matches = [i for i, name in enumerate(table.headers) if name in ALIASES[field]]
            for index, header in enumerate(table.headers):
                box.addItem(f"{index + 1}: {header}", index)
            if len(matches) == 1:
                box.setCurrentIndex(matches[0] + 1)
            self.columns[field] = box
            form.addRow(field.replace("_", " ").title(), box)
        self.units = QComboBox()
        self.units.addItems(["seconds", "hours"])
        form.addRow("Estimate units (never story points)", self.units)
        self.date_format = QComboBox()
        self.date_format.addItems(DATE_FORMATS)
        form.addRow("Date format", self.date_format)
        profiles = QHBoxLayout()
        for text, callback in (
            ("Load profile...", self.load_profile),
            ("Save profile...", self.save_profile),
        ):
            button = QPushButton(text)
            button.clicked.connect(callback)
            profiles.addWidget(button)
        form.addRow(profiles)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_page)
        self.pages.addWidget(scroll)
        self.match_page = QScrollArea()
        self.match_page.setWidgetResizable(True)
        self.pages.addWidget(self.match_page)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(130)
        preview_page = QWidget()
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.addWidget(self.preview)
        self.preview_model = QStandardItemModel(self)
        self.preview_table = QTreeView()
        self.preview_table.setRootIsDecorated(False)
        self.preview_table.setModel(self.preview_model)
        preview_layout.addWidget(self.preview_table, 1)
        self.pages.addWidget(preview_page)
        self.error = QPlainTextEdit()
        self.error.setReadOnly(True)
        self.error.setMaximumHeight(90)
        self.error.setAccessibleName("Import validation errors")
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.back = QPushButton("Back")
        self.back.clicked.connect(self.go_back)
        self.back.setEnabled(False)
        self.next = QPushButton("Next")
        self.next.setDefault(True)
        self.next.clicked.connect(self.advance)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self.back)
        buttons.addWidget(self.next)
        layout.addLayout(buttons)

    def current_mapping(self) -> Mapping:
        return Mapping(
            tuple(
                (field, box.currentData())
                for field, box in self.columns.items()
                if box.currentData() >= 0
            ),
            self.units.currentText(),
            self.date_format.currentText(),
            self.profile_types,
            self.profile_priorities,
        )

    def advance(self) -> None:
        try:
            step = self.pages.currentIndex()
            if step == 0:
                self.mapping = self.current_mapping()
                self.build_matches()
            elif step == 1:
                base = self.current_mapping()
                for name, box in self.type_boxes.items():
                    if not box.currentData():
                        raise ValueError(f"Choose a Planacity work type for {name!r}.")
                self.mapping = Mapping(
                    base.columns,
                    base.estimate_unit,
                    base.date_format,
                    tuple(
                        (name, WorkItemType(box.currentData()))
                        for name, box in self.type_boxes.items()
                    ),
                    tuple(
                        (
                            name,
                            None if not box.currentData() else WorkPriority(box.currentData()),
                        )
                        for name, box in self.priority_boxes.items()
                    ),
                )
                self.profile_types = self.mapping.types
                self.profile_priorities = self.mapping.priorities
                people = {}
                for name, box in self.person_boxes.items():
                    selected = box.currentData()
                    if selected == "unmapped":
                        raise ValueError(f"Choose a person for {name!r}.")
                    people[name] = (
                        Person(name=name) if selected == "new" else self.plan.person(selected)
                    )
                self.candidate = preview_import(
                    self.plan, self.table, self.mapping, people, self.source
                )
                source = self.candidate.imports[-1]
                lines = [
                    f"Import {len(source.records)} items from {self.source}.",
                    "Original CSV cells and baseline will be stored in this local project.",
                    "Mapped people join the roster; this does not allocate work or capacity.",
                    "Status and external assignees are preserved for export, not edited here.",
                ]
                unresolved = sum(
                    1
                    for record in source.records
                    if record.external_priority.strip() and record.item.priority is None
                )
                if unresolved:
                    lines.append(
                        f"{unresolved} source priority value(s) remain unresolved: "
                        "Planacity keeps them Unset and preserves their original text."
                    )
                self.preview_model.clear()
                self.preview_model.setHorizontalHeaderLabels(
                    [
                        "Reference",
                        "Type",
                        "Title",
                        "Source priority",
                        "Planacity priority",
                        "Hours",
                        "Person",
                        "Start",
                        "End",
                    ]
                )
                for record in source.records:
                    item = record.item
                    values = (
                        record.external_reference,
                        item.kind.value.title(),
                        item.title,
                        record.external_priority or "Blank",
                        (
                            "Unresolved -> Unset"
                            if record.external_priority.strip() and item.priority is None
                            else "Unset"
                            if item.priority is None
                            else item.priority.value.title()
                        ),
                        "Unknown" if item.estimate_hours is None else str(item.estimate_hours),
                        record.person.name if record.person else "Unassigned",
                        "Not set" if item.start is None else str(item.start),
                        "Not set" if item.end is None else str(item.end),
                    )
                    row = [QStandardItem(value) for value in values]
                    for cell in row:
                        cell.setEditable(False)
                    self.preview_model.appendRow(row)
                for column in range(9):
                    self.preview_table.resizeColumnToContents(column)
                self.preview.setPlainText("\n".join(lines))
            else:
                if self.candidate is not None:
                    self.accept()
                return
            self.pages.setCurrentIndex(step + 1)
            self.update_step()
        except (ValueError, TypeError) as error:
            self.error.setPlainText(str(error))
            self.error.show()

    def build_matches(self) -> None:
        assert self.mapping is not None
        page = QWidget()
        form = QFormLayout(page)
        self.type_boxes = {}
        self.person_boxes = {}
        self.priority_boxes = {}
        column = dict(self.mapping.columns)["type"]
        form.addRow(label("Map every external work type explicitly."))
        for name in dict.fromkeys(row[column] for row in self.table.rows):
            box = QComboBox()
            box.addItem("Choose type", "")
            for kind in WorkItemType:
                box.addItem(kind.value.title(), kind.value)
            mapped = dict(self.profile_types).get(name)
            if mapped is not None:
                box.setCurrentIndex(box.findData(mapped.value))
            self.type_boxes[name] = box
            form.addRow(label(name), box)
        source_priorities = external_priorities(self.table, self.mapping)
        if source_priorities:
            form.addRow(
                label(
                    "Map source priorities explicitly. Unmapped values stay Unset and "
                    "their original text is preserved."
                )
            )
        saved_priorities = dict(self.profile_priorities)
        for name in source_priorities:
            box = QComboBox()
            box.addItem("Unmapped -> Unset", "")
            for priority in WorkPriority:
                box.addItem(priority.value.title(), priority.value)
            if name in saved_priorities:
                mapped_priority = saved_priorities[name]
                box.setCurrentIndex(
                    box.findData("" if mapped_priority is None else mapped_priority.value)
                )
            else:
                exact = next(
                    (
                        priority
                        for priority in WorkPriority
                        if priority.value.casefold() == name.casefold()
                    ),
                    None,
                )
                if exact is not None:
                    box.setCurrentIndex(box.findData(exact.value))
            self.priority_boxes[name] = box
            form.addRow(label(name), box)
        form.addRow(label("Map external people. Names are not matched automatically."))
        for name in external_people(self.table, self.mapping):
            box = QComboBox()
            box.addItem("Choose person", "unmapped")
            box.addItem(f"Create roster entry: {name}", "new")
            for person in self.plan.people:
                box.addItem(person.name, person.id)
            self.person_boxes[name] = box
            form.addRow(label(name), box)
        old = self.match_page.takeWidget()
        if old is not None:
            old.deleteLater()
        self.match_page.setWidget(page)

    def go_back(self) -> None:
        self.candidate = None
        self.pages.setCurrentIndex(max(0, self.pages.currentIndex() - 1))
        self.update_step()

    def update_step(self) -> None:
        step = self.pages.currentIndex()
        self.heading.setText(
            ("1. Map CSV columns", "2. Match values and people", "3. Review import")[step]
        )
        self.back.setEnabled(step > 0)
        self.next.setText("Import" if step == 2 else "Next")
        self.error.clear()
        self.error.hide()

    def save_profile(self) -> None:
        try:
            mapping = self.current_mapping()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save mapping profile", "mapping.json", "JSON (*.json)"
            )
            if filename:
                from planacity.persistence.project import export_text

                if Path(filename).suffix.lower() != ".json":
                    raise ValueError("Choose a filename ending in .json.")
                target = Path(filename)
                active = self.project_path
                if active is not None and (
                    target.resolve() == active.resolve()
                    or (target.exists() and target.samefile(active))
                ):
                    raise ValueError("A profile cannot replace the active project.")
                export_text(dump_profile(self.table.headers, mapping), Path(filename))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot save profile", str(error))

    def load_profile(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load mapping profile", "", "JSON (*.json)")
        if not filename:
            return
        try:
            mapping = load_profile(Path(filename).read_text(encoding="utf-8"), self.table.headers)
            for field, box in self.columns.items():
                box.setCurrentIndex(dict(mapping.columns).get(field, -1) + 1)
            self.units.setCurrentText(mapping.estimate_unit)
            self.date_format.setCurrentText(mapping.date_format)
            self.profile_types = mapping.types
            self.profile_priorities = mapping.priorities
            self.error.clear()
        except (OSError, ValueError) as error:
            self.error.setPlainText(str(error))
            self.error.show()
