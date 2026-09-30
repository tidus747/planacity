"""Availability editing with keyboard dates and explicit overlap previews."""

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import AvailabilityEvent, PlanningHorizon, ProgramPlan
from planacity.planning.availability_settings import (
    add_availability,
    availability_event,
    person_availability,
    remove_availability,
    update_availability,
)
from planacity.ui.forms import CalendarLineEdit, validated_form
from planacity.ui.pages import label
from planacity.ui.session import Session


def _summary(plan: ProgramPlan, person_id: UUID) -> str:
    result = person_availability(plan, person_id)
    heading = f"Horizon: {plan.horizon.start} to {plan.horizon.end}.\n"
    if result is None:
        return (
            heading + "No calendar assigned. Hours and overlaps are unknown. Entries are retained."
        )
    text = (
        heading + f"Nominal: {result.nominal_hours} h. Unavailable: {result.unavailable_hours} h. "
        f"Available: {result.available_hours} h.\n"
        "Before program events, reservations, and allocations.\n"
    )
    if not result.overlaps:
        return text + "No overlapping positive-share entries in this horizon."
    entries = {
        event.id: index
        for index, event in enumerate(
            (event for event in plan.availability_events if event.person_id == person_id), start=1
        )
    }
    return (
        text
        + "Overlaps use the largest share, not the sum:\n"
        + "\n".join(
            f"{overlap.period.start} to {overlap.period.end}: "
            + ", ".join(
                f"Entry {number}" for number in sorted(entries[i] for i in overlap.event_ids)
            )
            for overlap in result.overlaps
        )
    )


def edit_availability(
    parent: QWidget, session: Session, person_id: UUID, event_id: UUID | None = None
) -> None:
    plan = session.document.plan
    if plan is None:
        return
    person = plan.person(person_id)
    event = availability_event(plan, event_id) if event_id is not None else None
    identifier = event.id if event else uuid4()
    start, end = CalendarLineEdit(), CalendarLineEdit()
    start.setAccessibleName("Availability start")
    end.setAccessibleName("Availability end")
    start.setText(str(event.period.start if event else plan.horizon.start))
    end.setText(str(event.period.end if event else plan.horizon.end))
    fraction = QLineEdit(str(event.unavailable_fraction) if event else "")
    fraction.setAccessibleName("Unavailable share")
    fraction.setPlaceholderText("1 = full day; 0.5 = half; 0 = none")
    preview = QPlainTextEdit()
    preview.setReadOnly(True)
    preview.setAccessibleName("Availability preview")
    preview.setMinimumHeight(150)

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen this form.")
        dates = []
        for editor in (start, end):
            text = editor.text().strip()
            try:
                parsed = date.fromisoformat(text)
                if str(parsed) != text:
                    raise ValueError
            except ValueError as error:
                raise ValueError("Enter both dates as YYYY-MM-DD.") from error
            dates.append(parsed)
        try:
            share = Decimal(fraction.text().strip())
        except InvalidOperation as error:
            raise ValueError("Enter an unavailable share from 0 to 1, such as 0.5.") from error
        value = AvailabilityEvent(
            person_id=person_id,
            period=PlanningHorizon(*dates),
            unavailable_fraction=share,
            id=identifier,
        )
        return update_availability(plan, value) if event else add_availability(plan, value)

    def refresh() -> None:
        try:
            candidate = build()
            text = _summary(candidate, person_id)
            if dates_outside(start.text(), end.text(), plan.horizon):
                text += (
                    "\nEntry extends outside the horizon. "
                    "It is retained; only intersecting dates count."
                )
            preview.setPlainText(text)
        except ValueError as error:
            preview.setPlainText(str(error))

    for editor in (start, end, fraction):
        editor.textChanged.connect(refresh)
    refresh()
    updated = validated_form(
        parent,
        f"Availability for {person.name}",
        [
            ("&Start", start),
            ("&End", end),
            ("&Unavailable share (0 to 1)", fraction),
            (
                "",
                label(
                    "Shares apply to each date's calendar hours. Overlaps use the largest share. "
                    "For distinct partial absences, enter their combined share in one entry."
                ),
            ),
            ("&Preview", preview),
        ],
        build,
    )
    if updated is not None:
        session.apply(updated)


def dates_outside(start: str, end: str, horizon: PlanningHorizon) -> bool:
    return (
        date.fromisoformat(start.strip()) < horizon.start
        or date.fromisoformat(end.strip()) > horizon.end
    )


def manage_availability(parent: QWidget, session: Session, person_id: UUID) -> None:
    plan = session.document.plan
    if plan is None:
        return
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Availability for {plan.person(person_id).name}")
    dialog.resize(650, 500)
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        label(
            "Unavailable shares: 1 = full day, 0.5 = half, 0 = none. "
            "Confirmed edits are kept when this window closes."
        )
    )
    listing = QListWidget()
    listing.setAccessibleName("Availability entries")
    layout.addWidget(listing)
    summary = QPlainTextEdit()
    summary.setReadOnly(True)
    summary.setAccessibleName("Availability summary")
    layout.addWidget(summary)

    def refresh() -> None:
        listing.clear()
        current = session.document.plan
        if current is None:
            return
        for event in current.availability_events:
            if event.person_id == person_id:
                listing.addItem(
                    f"Entry {listing.count() + 1}: {event.period.start} to {event.period.end} | "
                    f"Unavailable share: {event.unavailable_fraction}"
                )
                listing.item(listing.count() - 1).setData(Qt.ItemDataRole.UserRole, str(event.id))
        summary.setPlainText(_summary(current, person_id))

    def selected() -> UUID | None:
        item = listing.currentItem()
        return UUID(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def add() -> None:
        edit_availability(dialog, session, person_id)
        refresh()

    def edit() -> None:
        identifier = selected()
        if identifier is not None:
            edit_availability(dialog, session, person_id, identifier)
            refresh()

    def delete() -> None:
        identifier, current = selected(), session.document.plan
        if identifier is None or current is None:
            return
        event = availability_event(current, identifier)
        if (
            QMessageBox.question(
                dialog,
                "Delete availability?",
                f"Delete the entry from {event.period.start} to {event.period.end}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            if session.document.plan is current:
                session.apply(remove_availability(current, identifier))
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
