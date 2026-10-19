"""Shared Program Calendar editing backed by the canonical event services."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID, uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QWidget,
)

from planacity.domain import (
    CalendarEvent,
    CalendarEventKind,
    PlanningHorizon,
    ProgramPlan,
    Sprint,
    WorkItem,
    WorkItemType,
)
from planacity.integrations.availability_csv import read_availability_csv
from planacity.planning.calendar_events import (
    add_calendar_event,
    calendar_event,
    remove_calendar_event,
    update_calendar_event,
)
from planacity.planning.sprints import (
    SprintFindingKind,
    add_sprint,
    assign_work_to_sprint,
    remove_sprint,
    sprint,
    sprint_findings,
    unassign_work_from_sprint,
    update_sprint,
)
from planacity.ui.availability_import_wizard import AvailabilityImportWizard
from planacity.ui.forms import CalendarLineEdit, validated_form
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.session import Session


def kind_label(kind: CalendarEventKind) -> str:
    return kind.value.replace("_", " ").title()


def impact_label(value: Decimal) -> str:
    if value == 0:
        return "No capacity reduction"
    percent = format(value * 100, "f")
    if "." in percent:
        percent = percent.rstrip("0").rstrip(".")
    return f"{percent}% unavailable"


def horizon_status(event: CalendarEvent, horizon: PlanningHorizon) -> str:
    notes: list[str] = []
    if event.period.end < horizon.start or event.period.start > horizon.end:
        notes.append("Outside horizon")
    elif event.period.start < horizon.start or event.period.end > horizon.end:
        notes.append("Partly outside horizon")
    if event.unavailable_fraction == 0:
        notes.append("Context only")
    return "; ".join(notes) or "Affects capacity"


def _strict_date(text: str) -> date:
    try:
        value = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError("Enter both dates as YYYY-MM-DD.") from error
    if str(value) != text:
        raise ValueError("Enter both dates as YYYY-MM-DD.")
    return value


def sprint_status(plan: ProgramPlan, value: Sprint) -> str:
    labels = {
        SprintFindingKind.OVERLAP: "Overlaps another sprint",
        SprintFindingKind.OUTSIDE_HORIZON: "Outside planning horizon",
    }
    findings = [
        labels[finding.kind]
        for finding in sprint_findings(plan)
        if finding.kind in labels
        and (finding.sprint_id == value.id or finding.other_sprint_id == value.id)
    ]
    return "; ".join(dict.fromkeys(findings)) or "Scheduled"


def assignment_status(plan: ProgramPlan, item: WorkItem) -> str:
    finding = next(
        (
            value
            for value in sprint_findings(plan)
            if value.work_item_id == item.id
            and value.kind
            in (SprintFindingKind.WORK_DATES_INCOMPLETE, SprintFindingKind.WORK_OUTSIDE_SPRINT)
        ),
        None,
    )
    if finding is None:
        return "Within sprint dates"
    if finding.kind == SprintFindingKind.WORK_DATES_INCOMPLETE:
        return "Work dates incomplete"
    return "Work outside sprint dates"


def edit_sprint(parent: QWidget, session: Session, sprint_id: UUID | None = None) -> None:
    """Create or edit one sprint without mutating a stale plan snapshot."""
    plan = session.document.plan
    if plan is None:
        return
    existing = sprint(plan, sprint_id) if sprint_id is not None else None
    identifier = existing.id if existing is not None else uuid4()
    name = QLineEdit(existing.name if existing is not None else "")
    name.setAccessibleName("Sprint name")
    start = CalendarLineEdit()
    start.setAccessibleName("Sprint start")
    start.setText(str(existing.period.start if existing is not None else plan.horizon.start))
    end = CalendarLineEdit()
    end.setAccessibleName("Sprint end")
    end.setText(str(existing.period.end if existing is not None else plan.horizon.start))
    reference = QLineEdit(existing.external_reference or "" if existing is not None else "")
    reference.setAccessibleName("Sprint external reference")
    reference.setPlaceholderText("Optional external ID or board reference")
    group = QComboBox()
    group.setAccessibleName("Sprint WorkGroup scope")
    group.addItem("Whole roster", "")
    for value in sorted(plan.work_groups, key=lambda item: (item.name.casefold(), str(item.id))):
        group.addItem(value.name, str(value.id))
    if existing is not None and existing.work_group_id is not None:
        group.setCurrentIndex(group.findData(str(existing.work_group_id)))
    guidance = label(
        "Overlaps, irregular lengths, and dates outside the horizon are retained and shown "
        "as planning findings."
    )

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen this form.")
        group_id = group.currentData()
        value = Sprint(
            id=identifier,
            name=name.text(),
            period=PlanningHorizon(
                _strict_date(start.text().strip()), _strict_date(end.text().strip())
            ),
            external_reference=reference.text().strip() or None,
            work_group_id=UUID(group_id) if group_id else None,
        )
        return update_sprint(plan, value) if existing is not None else add_sprint(plan, value)

    updated = validated_form(
        parent,
        "Edit sprint" if existing is not None else "Add sprint",
        [
            ("&Name", name),
            ("&Start", start),
            ("&End", end),
            ("E&xternal reference", reference),
            ("&WorkGroup scope", group),
            ("&Planning behavior", guidance),
        ],
        build,
    )
    if updated is not None:
        session.apply(updated)


def edit_sprint_assignment(parent: QWidget, session: Session, work_item_id: UUID) -> None:
    """Assign, reassign, or unassign one executable leaf in a transactional form."""
    plan = session.document.plan
    if plan is None:
        return
    item = plan.work_item(work_item_id)
    current = next(
        (value for value in plan.sprint_assignments if value.work_item_id == item.id), None
    )
    choice = QComboBox()
    choice.setAccessibleName("Assigned sprint")
    choice.addItem("Unassigned", "")
    for value in sorted(
        plan.sprints,
        key=lambda item: (item.period.start, item.period.end, item.name.casefold(), str(item.id)),
    ):
        choice.addItem(f"{value.name} ({value.period.start} to {value.period.end})", str(value.id))
    if current is not None:
        choice.setCurrentIndex(choice.findData(str(current.sprint_id)))

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen this form.")
        selected = choice.currentData()
        return (
            assign_work_to_sprint(plan, UUID(selected), item.id)
            if selected
            else unassign_work_from_sprint(plan, item.id)
        )

    updated = validated_form(
        parent,
        f"Sprint assignment for {item.title}",
        [("&Sprint", choice)],
        build,
    )
    if updated is not None:
        session.apply(updated)


def edit_calendar_event(parent: QWidget, session: Session, event_id: UUID | None = None) -> None:
    """Create or edit one event atomically after validating the complete draft."""
    plan = session.document.plan
    if plan is None:
        return
    existing = calendar_event(plan, event_id) if event_id is not None else None
    identifier = existing.id if existing is not None else uuid4()

    name = QLineEdit(existing.name if existing is not None else "")
    name.setAccessibleName("Event name")
    kind = QComboBox()
    kind.setAccessibleName("Event category")
    for value in CalendarEventKind:
        kind.addItem(kind_label(value), value.value)
    if existing is not None:
        kind.setCurrentIndex(kind.findData(existing.kind.value))
    start = CalendarLineEdit()
    start.setAccessibleName("Event start")
    start.setText(str(existing.period.start if existing is not None else plan.horizon.start))
    end = CalendarLineEdit()
    end.setAccessibleName("Event end")
    end.setText(str(existing.period.end if existing is not None else plan.horizon.start))
    fraction = QLineEdit(str(existing.unavailable_fraction) if existing is not None else "0")
    fraction.setAccessibleName("Unavailable share")
    fraction.setPlaceholderText("1 = full day; 0.5 = half; 0 = context only")
    guidance = label("")
    guidance.setAccessibleName("Event impact preview")

    def candidate() -> CalendarEvent:
        selected_kind = kind.currentData()
        if not isinstance(selected_kind, str):
            raise ValueError("Choose an event category.")
        start_value = _strict_date(start.text().strip())
        end_value = _strict_date(end.text().strip())
        try:
            share = Decimal(fraction.text().strip())
        except InvalidOperation as error:
            raise ValueError("Enter an unavailable share from 0 to 1, such as 0.5.") from error
        return CalendarEvent(
            id=identifier,
            name=name.text(),
            kind=CalendarEventKind(selected_kind),
            period=PlanningHorizon(start_value, end_value),
            unavailable_fraction=share,
        )

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen this form.")
        value = candidate()
        return (
            update_calendar_event(plan, value)
            if existing is not None
            else add_calendar_event(plan, value)
        )

    def refresh_guidance() -> None:
        try:
            value = candidate()
            guidance.setText(
                f"{impact_label(value.unavailable_fraction)} for every roster person's "
                f"own work calendar. Status: {horizon_status(value, plan.horizon)}. "
                "Overlapping personal and shared events use the strongest share."
            )
        except ValueError as error:
            guidance.setText(str(error))

    for editor in (name, start, end, fraction):
        editor.textChanged.connect(refresh_guidance)
    kind.currentIndexChanged.connect(refresh_guidance)
    refresh_guidance()
    updated = validated_form(
        parent,
        "Edit program event" if existing is not None else "Add program event",
        [
            ("&Name", name),
            ("&Category", kind),
            ("&Start", start),
            ("&End", end),
            ("&Unavailable share (0 to 1)", fraction),
            ("&Impact", guidance),
        ],
        build,
    )
    if updated is not None:
        session.apply(updated)


class CalendarPage(WorkspacePage):
    """List and manage plan-wide dated context without inventing appointments."""

    HEADERS = ("Name", "Category", "Start", "End", "Capacity impact", "Status")
    SPRINT_HEADERS = ("Name", "Start", "End", "WorkGroup scope", "External reference", "Status")
    ASSIGNMENT_HEADERS = ("Work", "Type", "Dates", "Sprint", "Status")

    def __init__(self, session: Session) -> None:
        super().__init__(
            "Calendar",
            "Manage shared events, manual sprints, and explicit sprint assignments.",
        )
        self.session = session
        self.model = QStandardItemModel(0, len(self.HEADERS))
        self.model.setHorizontalHeaderLabels(self.HEADERS)
        self.table = QTreeView()
        self.table.setObjectName("Program calendar events")
        self.table.setAccessibleName("Program calendar events")
        self.table.setModel(self.model)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_selected)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add event...")
        self.edit_button = QPushButton("Edit event...")
        self.delete_button = QPushButton("Delete event...")
        self.add_button.clicked.connect(self.add_event)
        self.edit_button.clicked.connect(self.edit_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        for button in (self.add_button, self.edit_button, self.delete_button):
            actions.addWidget(button)
        self.delimiter = QComboBox()
        for name, value in (("Comma", ","), ("Semicolon", ";"), ("Tab", "\t")):
            self.delimiter.addItem(name, value)
        self.delimiter.setAccessibleName("Availability CSV delimiter")
        self.import_button = QPushButton("Import availability CSV...")
        self.import_button.clicked.connect(self.import_availability)
        actions.addWidget(self.delimiter)
        actions.addWidget(self.import_button)
        actions.addStretch()
        self.header.addLayout(actions)

        panel = Panel("Shared events")
        panel.content.addWidget(
            label(
                "Capacity impact applies to every roster person's own work calendar. "
                "Personal and shared overlaps use the strongest unavailable share; "
                "reservations remain separate."
            )
        )
        self.empty_state = label("Open a plan to manage shared program events.")
        self.empty_state.setAccessibleName("Program calendar status")
        panel.content.addWidget(self.empty_state)
        panel.content.addWidget(self.table)
        self.content.addWidget(panel)

        self.sprint_model = QStandardItemModel(0, len(self.SPRINT_HEADERS))
        self.sprint_model.setHorizontalHeaderLabels(self.SPRINT_HEADERS)
        self.sprint_table = QTreeView()
        self.sprint_table.setObjectName("Program calendar sprints")
        self.sprint_table.setAccessibleName("Program calendar sprints")
        self.sprint_table.setModel(self.sprint_model)
        self.sprint_table.setRootIsDecorated(False)
        self.sprint_table.setAlternatingRowColors(True)
        self.sprint_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sprint_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sprint_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sprint_table.doubleClicked.connect(self.edit_selected_sprint)
        sprint_panel = Panel("Sprint planning")
        sprint_panel.content.addWidget(
            label(
                "Sprints are manual planning periods. WorkGroup scope is context; capacity "
                "and automatic distribution are not calculated in this view."
            )
        )
        self.sprint_empty_state = label("Open a plan to manage sprints.")
        self.sprint_empty_state.setAccessibleName("Sprint planning status")
        sprint_panel.content.addWidget(self.sprint_empty_state)
        sprint_actions = QHBoxLayout()
        self.add_sprint_button = QPushButton("Add sprint...")
        self.edit_sprint_button = QPushButton("Edit sprint...")
        self.delete_sprint_button = QPushButton("Delete sprint...")
        self.add_sprint_button.clicked.connect(self.add_sprint)
        self.edit_sprint_button.clicked.connect(self.edit_selected_sprint)
        self.delete_sprint_button.clicked.connect(self.delete_selected_sprint)
        for button in (
            self.add_sprint_button,
            self.edit_sprint_button,
            self.delete_sprint_button,
        ):
            sprint_actions.addWidget(button)
        sprint_actions.addStretch()
        sprint_panel.content.addLayout(sprint_actions)
        sprint_panel.content.addWidget(self.sprint_table)

        self.assignment_model = QStandardItemModel(0, len(self.ASSIGNMENT_HEADERS))
        self.assignment_model.setHorizontalHeaderLabels(self.ASSIGNMENT_HEADERS)
        self.assignment_table = QTreeView()
        self.assignment_table.setObjectName("Sprint work assignments")
        self.assignment_table.setAccessibleName("Sprint work assignments")
        self.assignment_table.setModel(self.assignment_model)
        self.assignment_table.setRootIsDecorated(False)
        self.assignment_table.setAlternatingRowColors(True)
        self.assignment_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.assignment_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.assignment_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.assignment_table.doubleClicked.connect(self.assign_selected_work)
        assignment_actions = QHBoxLayout()
        self.assign_button = QPushButton("Set sprint...")
        self.unassign_button = QPushButton("Unassign")
        self.assign_button.clicked.connect(self.assign_selected_work)
        self.unassign_button.clicked.connect(self.unassign_selected_work)
        assignment_actions.addWidget(self.assign_button)
        assignment_actions.addWidget(self.unassign_button)
        assignment_actions.addStretch()
        sprint_panel.content.addLayout(assignment_actions)
        self.assignment_empty_state = label("Executable leaf work appears here.")
        self.assignment_empty_state.setAccessibleName("Sprint assignment status")
        sprint_panel.content.addWidget(self.assignment_empty_state)
        sprint_panel.content.addWidget(self.assignment_table)
        self.content.addWidget(sprint_panel)

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.sprint_table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.assignment_table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.session.changed.connect(self.refresh)
        self.refresh()

    def selected_event_id(self) -> UUID | None:
        value = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if isinstance(value, str) and value else None

    def selected_sprint_id(self) -> UUID | None:
        value = self.sprint_table.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if isinstance(value, str) and value else None

    def selected_work_id(self) -> UUID | None:
        value = self.assignment_table.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if isinstance(value, str) and value else None

    def refresh(self) -> None:
        selected_id = self.selected_event_id()
        selected_sprint_id = self.selected_sprint_id()
        selected_work_id = self.selected_work_id()
        self.model.removeRows(0, self.model.rowCount())
        self.sprint_model.removeRows(0, self.sprint_model.rowCount())
        self.assignment_model.removeRows(0, self.assignment_model.rowCount())
        plan = self.session.document.plan
        events = (
            sorted(
                plan.calendar_events,
                key=lambda value: (
                    value.period.start,
                    value.period.end,
                    value.name.casefold(),
                    str(value.id),
                ),
            )
            if plan is not None
            else ()
        )
        for event in events:
            assert plan is not None
            row = [
                QStandardItem(value)
                for value in (
                    event.name,
                    kind_label(event.kind),
                    str(event.period.start),
                    str(event.period.end),
                    impact_label(event.unavailable_fraction),
                    horizon_status(event, plan.horizon),
                )
            ]
            for cell in row:
                cell.setEditable(False)
                cell.setData(str(event.id), Qt.ItemDataRole.UserRole)
            self.model.appendRow(row)
            if event.id == selected_id:
                self.table.setCurrentIndex(row[0].index())

        sprints = (
            sorted(
                plan.sprints,
                key=lambda value: (
                    value.period.start,
                    value.period.end,
                    value.name.casefold(),
                    str(value.id),
                ),
            )
            if plan is not None
            else ()
        )
        groups = {value.id: value.name for value in plan.work_groups} if plan is not None else {}
        for value in sprints:
            assert plan is not None
            row = [
                QStandardItem(text)
                for text in (
                    value.name,
                    str(value.period.start),
                    str(value.period.end),
                    (
                        groups[value.work_group_id]
                        if value.work_group_id is not None
                        else "Whole roster"
                    ),
                    value.external_reference or "",
                    sprint_status(plan, value),
                )
            ]
            for cell in row:
                cell.setEditable(False)
                cell.setData(str(value.id), Qt.ItemDataRole.UserRole)
            self.sprint_model.appendRow(row)
            if value.id == selected_sprint_id:
                self.sprint_table.setCurrentIndex(row[0].index())

        leaves = (
            tuple(
                item
                for item in plan.work_items
                if item.kind != WorkItemType.EPIC and not plan.children(item.id)
            )
            if plan is not None
            else ()
        )
        sprint_names = {value.id: value.name for value in sprints}
        assignments = (
            {value.work_item_id: value.sprint_id for value in plan.sprint_assignments}
            if plan is not None
            else {}
        )
        for item in leaves:
            assert plan is not None
            sprint_id = assignments.get(item.id)
            dates = (
                f"{item.start} to {item.end}"
                if item.start is not None and item.end is not None
                else "Incomplete"
            )
            row = [
                QStandardItem(text)
                for text in (
                    item.title,
                    item.kind.value.title(),
                    dates,
                    sprint_names[sprint_id] if sprint_id is not None else "Unassigned",
                    assignment_status(plan, item) if sprint_id is not None else "Unassigned",
                )
            ]
            for cell in row:
                cell.setEditable(False)
                cell.setData(str(item.id), Qt.ItemDataRole.UserRole)
            self.assignment_model.appendRow(row)
            if item.id == selected_work_id:
                self.assignment_table.setCurrentIndex(row[0].index())

        if plan is None:
            self.empty_state.setText("Open a plan to manage shared program events.")
        elif not events:
            self.empty_state.setText(
                "No shared events yet. Add a holiday, visit, company event, or program event."
            )
        else:
            self.empty_state.setText(
                f"{len(events)} shared event{'s' if len(events) != 1 else ''}. "
                "Double-click a row to edit it."
            )
        self.table.setVisible(bool(events))
        self.add_button.setEnabled(plan is not None)
        self.import_button.setEnabled(plan is not None)
        self.sprint_table.setVisible(bool(sprints))
        self.assignment_table.setVisible(bool(leaves))
        self.add_sprint_button.setEnabled(plan is not None)
        if plan is None:
            self.sprint_empty_state.setText("Open a plan to manage sprints.")
            self.assignment_empty_state.setText("Open a plan to assign executable work.")
        else:
            self.sprint_empty_state.setText(
                f"{len(sprints)} sprint{'s' if len(sprints) != 1 else ''}. "
                "Double-click a row to edit it."
                if sprints
                else "No sprints yet. Add a manual planning period."
            )
            self.assignment_empty_state.setText(
                f"{len(leaves)} executable leaf item{'s' if len(leaves) != 1 else ''}."
                if leaves
                else "No executable leaf work is available for sprint assignment."
            )
        if self.model.rowCount() and not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        if self.sprint_model.rowCount() and not self.sprint_table.currentIndex().isValid():
            self.sprint_table.setCurrentIndex(self.sprint_model.index(0, 0))
        if self.assignment_model.rowCount() and not self.assignment_table.currentIndex().isValid():
            self.assignment_table.setCurrentIndex(self.assignment_model.index(0, 0))
        for table, model in (
            (self.table, self.model),
            (self.sprint_table, self.sprint_model),
            (self.assignment_table, self.assignment_model),
        ):
            for column in range(model.columnCount()):
                table.resizeColumnToContents(column)
        self._selection_changed()

    def _selection_changed(self, *args: object) -> None:
        selected = self.selected_event_id() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)
        sprint_selected = self.selected_sprint_id() is not None
        self.edit_sprint_button.setEnabled(sprint_selected)
        self.delete_sprint_button.setEnabled(sprint_selected)
        work_id = self.selected_work_id()
        plan = self.session.document.plan
        self.assign_button.setEnabled(
            work_id is not None and plan is not None and bool(plan.sprints)
        )
        self.unassign_button.setEnabled(
            work_id is not None
            and any(value.work_item_id == work_id for value in plan.sprint_assignments)
            if plan is not None
            else False
        )

    def add_event(self) -> None:
        edit_calendar_event(self, self.session)

    def add_sprint(self) -> None:
        edit_sprint(self, self.session)

    def edit_selected_sprint(self, *args: object) -> None:
        sprint_id = self.selected_sprint_id()
        if sprint_id is not None:
            edit_sprint(self, self.session, sprint_id)

    def delete_selected_sprint(self) -> None:
        sprint_id = self.selected_sprint_id()
        plan = self.session.document.plan
        if sprint_id is None or plan is None:
            return
        value = sprint(plan, sprint_id)
        count = sum(item.sprint_id == value.id for item in plan.sprint_assignments)
        if (
            QMessageBox.question(
                self,
                "Delete sprint?",
                f"Delete '{value.name}' and remove {count} work assignment(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
            and self.session.document.plan is plan
        ):
            self.session.apply(remove_sprint(plan, value.id))

    def assign_selected_work(self, *args: object) -> None:
        work_id = self.selected_work_id()
        if work_id is not None:
            edit_sprint_assignment(self, self.session, work_id)

    def unassign_selected_work(self) -> None:
        work_id = self.selected_work_id()
        plan = self.session.document.plan
        if work_id is not None and plan is not None:
            self.session.apply(unassign_work_from_sprint(plan, work_id))

    def import_availability(self) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import availability CSV", "", "CSV (*.csv);;All files (*)"
        )
        if not filename:
            return
        try:
            path = Path(filename)
            table = read_availability_csv(
                path.read_text(encoding="utf-8-sig"), self.delimiter.currentData()
            )
            wizard = AvailabilityImportWizard(plan, table, self.delimiter.currentData(), self)
            if wizard.exec() == QDialog.DialogCode.Accepted and wizard.candidate is not None:
                if self.session.document.plan is not plan:
                    raise ValueError("The plan changed. Review the CSV again.")
                self.session.apply(wizard.candidate)
            wizard.deleteLater()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot import availability CSV", str(error))

    def edit_selected(self, *args: object) -> None:
        event_id = self.selected_event_id()
        if event_id is not None:
            edit_calendar_event(self, self.session, event_id)

    def delete_selected(self) -> None:
        event_id = self.selected_event_id()
        plan = self.session.document.plan
        if event_id is None or plan is None:
            return
        event = calendar_event(plan, event_id)
        if (
            QMessageBox.question(
                self,
                "Delete program event?",
                f"Delete '{event.name}' from the Program Calendar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
            and self.session.document.plan is plan
        ):
            self.session.apply(remove_calendar_event(plan, event.id))
