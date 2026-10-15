"""Shared Program Calendar editing backed by the canonical event services."""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeView,
    QWidget,
)

from planacity.domain import CalendarEvent, CalendarEventKind, PlanningHorizon, ProgramPlan
from planacity.planning.calendar_events import (
    add_calendar_event,
    calendar_event,
    remove_calendar_event,
    update_calendar_event,
)
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

    def __init__(self, session: Session) -> None:
        super().__init__(
            "Calendar",
            "Manage shared holidays and program events that give work and capacity context.",
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

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.session.changed.connect(self.refresh)
        self.refresh()

    def selected_event_id(self) -> UUID | None:
        value = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if isinstance(value, str) and value else None

    def refresh(self) -> None:
        selected_id = self.selected_event_id()
        self.model.removeRows(0, self.model.rowCount())
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
            for item in row:
                item.setEditable(False)
                item.setData(str(event.id), Qt.ItemDataRole.UserRole)
            self.model.appendRow(row)
            if event.id == selected_id:
                self.table.setCurrentIndex(row[0].index())

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
        if self.model.rowCount() and not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.model.index(0, 0))
        for column in range(self.model.columnCount()):
            self.table.resizeColumnToContents(column)
        self._selection_changed()

    def _selection_changed(self, *args: object) -> None:
        selected = self.selected_event_id() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def add_event(self) -> None:
        edit_calendar_event(self, self.session)

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
