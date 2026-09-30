"""Accessible calendar management and explicit per-person assignments."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import ProgramPlan, WorkCalendar
from planacity.planning.calendar_settings import (
    add_calendar,
    assign_calendar,
    remove_calendar,
    update_calendar,
)
from planacity.planning.work_calendar import nominal_capacity
from planacity.ui.forms import validated_form
from planacity.ui.pages import label
from planacity.ui.session import Session

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _current(session: Session, plan: ProgramPlan) -> None:
    if session.document.plan is not plan:
        raise ValueError("The plan changed. Cancel and reopen this form.")


def edit_work_calendar(parent: QWidget, session: Session, calendar_id: UUID | None = None) -> None:
    plan = session.document.plan
    if plan is None:
        return
    calendar = plan.work_calendar(calendar_id) if calendar_id is not None else None
    name = QLineEdit(calendar.name if calendar else "")
    fields: list[tuple[str, QWidget]] = [("&Name", name)]
    editors = []
    for index, weekday in enumerate(WEEKDAYS):
        editor = QLineEdit(str(calendar.weekday_hours[index]) if calendar else "")
        editor.setAccessibleName(f"{weekday} hours")
        editor.setPlaceholderText("Hours (0 for non-working day)")
        fields.append((f"{weekday} (h)", editor))
        editors.append(editor)
    used = sum(value.calendar_id == calendar_id for value in plan.person_calendars)
    fields.append(
        ("", label(f"Nominal hours before leave, events, or reservations. Used by {used} people."))
    )

    def build() -> ProgramPlan:
        _current(session, plan)
        try:
            hours = tuple(Decimal(editor.text().strip()) for editor in editors)
        except InvalidOperation as error:
            raise ValueError(
                "Enter hours for all seven days. Use 0 for a non-working day."
            ) from error
        values = WorkCalendar(
            name=name.text(),
            weekday_hours=hours,
            **({"id": calendar.id} if calendar is not None else {}),
        )
        return update_calendar(plan, values) if calendar else add_calendar(plan, values)

    updated = validated_form(
        parent, "Edit work calendar" if calendar else "Add work calendar", fields, build
    )
    if updated is not None:
        session.apply(updated)


def manage_work_calendars(parent: QWidget, session: Session) -> None:
    if session.document.plan is None:
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle("Work calendars")
    dialog.resize(480, 380)
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        label(
            "Define explicit weekly hours, then assign a calendar to each person. "
            "No default is assumed."
        )
    )
    listing = QListWidget()
    listing.setAccessibleName("Work calendars")
    layout.addWidget(listing)

    def refresh() -> None:
        listing.clear()
        plan = session.document.plan
        if plan is not None:
            for calendar in plan.work_calendars:
                listing.addItem(calendar.name)
                listing.item(listing.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, str(calendar.id)
                )

    def selected() -> UUID | None:
        item = listing.currentItem()
        return UUID(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def edit() -> None:
        identifier = selected()
        if identifier is not None:
            edit_work_calendar(dialog, session, identifier)
            refresh()

    def add() -> None:
        edit_work_calendar(dialog, session)
        refresh()

    def delete() -> None:
        identifier, plan = selected(), session.document.plan
        if identifier is None or plan is None:
            return
        calendar = plan.work_calendar(identifier)
        people = [
            plan.person(value.person_id).name
            for value in plan.person_calendars
            if value.calendar_id == identifier
        ]
        message = f"Delete '{calendar.name}'?"
        if people:
            message += "\nThis also clears calendar assignments for: " + ", ".join(people)
        if (
            QMessageBox.question(
                dialog,
                "Delete calendar?",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            if session.document.plan is plan:
                session.apply(remove_calendar(plan, identifier, unassign=bool(people)))
                refresh()

    actions = QHBoxLayout()
    for text, callback in (("&Add...", add), ("&Edit...", edit), ("&Delete...", delete)):
        button = QPushButton(text)
        button.clicked.connect(callback)
        actions.addWidget(button)
    layout.addLayout(actions)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    refresh()
    dialog.exec()
    dialog.deleteLater()


def choose_person_calendar(parent: QWidget, session: Session, person_id: UUID) -> None:
    plan = session.document.plan
    if plan is None:
        return
    person = plan.person(person_id)
    selected = next(
        (value.calendar_id for value in plan.person_calendars if value.person_id == person_id), None
    )
    choices = QComboBox()
    choices.setAccessibleName("Assigned work calendar")
    choices.addItem("Not configured", "")
    for calendar in plan.work_calendars:
        choices.addItem(calendar.name, str(calendar.id))
    choices.setCurrentIndex(max(0, choices.findData(str(selected) if selected else "")))
    preview = label("")

    def refresh() -> None:
        identifier = choices.currentData()
        if not identifier:
            preview.setText("No calendar assigned. Nominal hours are unknown, not zero.")
            return
        capacity = nominal_capacity(plan.work_calendar(UUID(identifier)), plan.horizon)
        preview.setText(
            f"{plan.horizon.start} to {plan.horizon.end}: {capacity.total_hours} nominal hours, "
            f"{capacity.working_days} working days. Before leave, events, and reservations."
        )

    def build() -> ProgramPlan:
        _current(session, plan)
        return assign_calendar(
            plan, person_id, UUID(choices.currentData()) if choices.currentData() else None
        )

    choices.currentIndexChanged.connect(refresh)
    refresh()
    updated = validated_form(
        parent, f"Calendar for {person.name}", [("&Calendar", choices), ("", preview)], build
    )
    if updated is not None:
        session.apply(updated)
