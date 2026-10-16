"""Review and confirm generic personal-availability CSV imports."""

from pathlib import Path
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import ProgramPlan
from planacity.integrations.availability_csv import (
    FIELDS,
    AvailabilityCsvMapping,
    AvailabilityCsvTable,
    AvailabilityImportPreview,
    apply_availability_import,
    dump_mapping_profile,
    external_people,
    load_mapping_profile,
    preview_availability_import,
)
from planacity.ui.pages import label

ALIASES = {
    "person": ("person", "name", "employee"),
    "start": ("start", "start date", "from"),
    "end": ("end", "end date", "to"),
    "unavailable_fraction": ("unavailable fraction", "unavailable share", "share"),
}


class AvailabilityImportWizard(QDialog):
    """Map, preview, and atomically prepare one availability import."""

    def __init__(
        self,
        plan: ProgramPlan,
        table: AvailabilityCsvTable,
        delimiter: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import availability CSV")
        self.resize(900, 680)
        self.plan = plan
        self.table = table
        self.delimiter = delimiter
        self.candidate: ProgramPlan | None = None
        self.preview: AvailabilityImportPreview | None = None
        self.columns: dict[str, QComboBox] = {}
        self.person_boxes: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self)
        self.heading = label("1. Map CSV columns", "heading")
        layout.addWidget(self.heading)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.pages.addWidget(self._mapping_page())
        self.people_page = QScrollArea()
        self.people_page.setWidgetResizable(True)
        self.pages.addWidget(self.people_page)
        self.pages.addWidget(self._preview_page())

        self.error = QPlainTextEdit()
        self.error.setReadOnly(True)
        self.error.setMaximumHeight(72)
        self.error.setAccessibleName("Availability import errors")
        self.error.hide()
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.back = QPushButton("Back")
        self.back.clicked.connect(self.go_back)
        self.back.setEnabled(False)
        self.next = QPushButton("Next")
        self.next.clicked.connect(self.advance)
        self.next.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addStretch()
        buttons.addWidget(self.back)
        buttons.addWidget(self.next)
        layout.addLayout(buttons)

    def _mapping_page(self) -> QScrollArea:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(label("Map each required field once. Dates must use YYYY-MM-DD."))
        lowered = [header.casefold() for header in self.table.headers]
        for field in FIELDS:
            box = QComboBox()
            box.setAccessibleName(field.replace("_", " ").title())
            box.addItem("Not mapped", -1)
            for index, header in enumerate(self.table.headers):
                box.addItem(f"{index + 1}: {header}", index)
            matches = [i for i, value in enumerate(lowered) if value in ALIASES[field]]
            if len(matches) == 1:
                box.setCurrentIndex(matches[0] + 1)
            self.columns[field] = box
            form.addRow(field.replace("_", " ").title(), box)
        profiles = QHBoxLayout()
        load = QPushButton("Load profile...")
        save = QPushButton("Save profile...")
        load.clicked.connect(self.load_profile)
        save.clicked.connect(self.save_profile)
        profiles.addWidget(load)
        profiles.addWidget(save)
        form.addRow(profiles)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _preview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary = label("")
        self.summary.setAccessibleName("Availability import summary")
        layout.addWidget(self.summary)
        self.preview_model = QStandardItemModel(self)
        self.preview_model.setHorizontalHeaderLabels(
            ("Import", "Line", "Person", "Start", "End", "Unavailable", "Status")
        )
        self.preview_table = QTreeView()
        self.preview_table.setAccessibleName("Availability import preview")
        self.preview_table.setRootIsDecorated(False)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setModel(self.preview_model)
        header = self.preview_table.header()
        for column in range(6):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.preview_model.itemChanged.connect(self._selection_changed)
        layout.addWidget(self.preview_table, 1)
        return page

    def current_mapping(self) -> AvailabilityCsvMapping:
        return AvailabilityCsvMapping(
            tuple((name, box.currentData()) for name, box in self.columns.items()),
            self.delimiter,
        )

    def _show_error(self, message: str) -> None:
        self.error.setPlainText(message)
        self.error.setVisible(bool(message))

    def advance(self) -> None:
        try:
            step = self.pages.currentIndex()
            if step == 0:
                mapping = self.current_mapping()
                self._build_people(mapping)
                self.pages.setCurrentIndex(1)
                self.heading.setText("2. Match people")
            elif step == 1:
                mapping = self.current_mapping()
                people = {
                    name: UUID(box.currentData())
                    for name, box in self.person_boxes.items()
                    if box.currentData()
                }
                self.preview = preview_availability_import(self.plan, self.table, mapping, people)
                self._build_preview()
                self.pages.setCurrentIndex(2)
                self.heading.setText("3. Review and confirm")
            else:
                assert self.preview is not None
                selected = frozenset(
                    UUID(self.preview_model.item(row, 0).data(Qt.ItemDataRole.UserRole))
                    for row in range(self.preview_model.rowCount())
                    if self.preview_model.item(row, 0).checkState() == Qt.CheckState.Checked
                )
                if not selected:
                    raise ValueError("Select at least one valid availability row to import.")
                self.candidate = apply_availability_import(self.plan, self.preview, selected)
                self.accept()
                return
            self.back.setEnabled(True)
            self.next.setText("Import selected" if self.pages.currentIndex() == 2 else "Next")
            self._show_error("")
        except ValueError as error:
            self._show_error(str(error))

    def _build_people(self, mapping: AvailabilityCsvMapping) -> None:
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(label("Every source person must map to an existing roster person."))
        self.person_boxes = {}
        for source_name in external_people(self.table, mapping):
            box = QComboBox()
            box.addItem("Not mapped", "")
            for person in self.plan.people:
                box.addItem(f"{person.name} ({person.id})", str(person.id))
            exact = [i for i, person in enumerate(self.plan.people) if person.name == source_name]
            if len(exact) == 1:
                box.setCurrentIndex(exact[0] + 1)
            self.person_boxes[source_name] = box
            form.addRow(source_name, box)
        self.people_page.setWidget(page)

    def _build_preview(self) -> None:
        assert self.preview is not None
        self.preview_model.blockSignals(True)
        self.preview_model.removeRows(0, self.preview_model.rowCount())
        people = {person.id: person.name for person in self.plan.people}
        for row in self.preview.rows:
            event = row.event
            warnings = []
            if row.overlapping_event_ids:
                warnings.append("overlaps existing availability")
            if row.outside_horizon:
                warnings.append("outside horizon")
            status = "; ".join((*row.errors, *warnings)) or "Ready"
            check = QStandardItem("")
            check.setData(str(row.candidate_id), Qt.ItemDataRole.UserRole)
            check.setCheckable(row.selectable)
            check.setCheckState(
                Qt.CheckState.Checked
                if row.selectable and not warnings
                else Qt.CheckState.Unchecked
            )
            values = [
                check,
                QStandardItem(str(row.line)),
                QStandardItem(
                    people.get(event.person_id, row.person_value) if event else row.person_value
                ),
                QStandardItem(str(event.period.start) if event else ""),
                QStandardItem(str(event.period.end) if event else ""),
                QStandardItem(str(event.unavailable_fraction) if event else ""),
                QStandardItem(status),
            ]
            for item in values:
                item.setEditable(False)
            self.preview_model.appendRow(values)
        self.preview_model.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *args: object) -> None:
        selected = sum(
            self.preview_model.item(row, 0).checkState() == Qt.CheckState.Checked
            for row in range(self.preview_model.rowCount())
        )
        total = self.preview_model.rowCount()
        self.summary.setText(
            f"{selected} of {total} row{'s' if total != 1 else ''} selected. "
            "Rows with overlaps or outside the horizon require explicit inclusion."
        )

    def go_back(self) -> None:
        step = self.pages.currentIndex()
        if step <= 0:
            return
        self.pages.setCurrentIndex(step - 1)
        self.candidate = None
        self.preview = None
        self.heading.setText("1. Map CSV columns" if step == 1 else "2. Match people")
        self.back.setEnabled(self.pages.currentIndex() > 0)
        self.next.setText("Next")
        self._show_error("")

    def save_profile(self) -> None:
        try:
            mapping = self.current_mapping()
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save availability mapping", "", "JSON (*.json)"
            )
            if filename:
                Path(filename).write_text(
                    dump_mapping_profile(self.table.headers, mapping), encoding="utf-8"
                )
            self._show_error("")
        except (OSError, ValueError) as error:
            self._show_error(str(error))

    def load_profile(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load availability mapping", "", "JSON (*.json)"
        )
        if not filename:
            return
        try:
            mapping = load_mapping_profile(
                Path(filename).read_text(encoding="utf-8"), self.table.headers
            )
            if mapping.delimiter != self.delimiter:
                raise ValueError("The profile uses a different CSV delimiter.")
            for field, index in mapping.columns:
                self.columns[field].setCurrentIndex(index + 1)
            self._show_error("")
        except (OSError, ValueError) as error:
            self._show_error(str(error))
