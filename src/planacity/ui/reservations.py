"""Preview-and-confirm recurring capacity workflow shared by menu and People."""

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
from uuid import UUID, uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import PlanningHorizon, ProgramPlan, ReservationRule
from planacity.planning.reservation_preview import preview_plan_reservations
from planacity.planning.reservation_settings import (
    add_reservation,
    remove_reservation,
    reservation_rule,
    update_reservation,
)
from planacity.planning.reservations import ReservationCapacity
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.pages import label
from planacity.ui.session import Session


def hours_text(value: Fraction | None) -> str:
    """Show terminating decimals exactly; retain fractions rather than rounding thirds."""
    if value is None:
        return "Unknown (no eligible days)"
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return str(value)
    with localcontext() as context:
        context.prec = max(28, len(str(abs(value.numerator))) + max(twos, fives) + 2)
        return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def preview_text(plan: ProgramPlan, results: tuple[ReservationCapacity, ...]) -> str:
    lines = [
        "Based on work calendars and entered availability only.",
        "Remaining hours are before program events and work allocations.",
        "Do not record the same duty as both availability and a reservation.",
        "Shares use eligible days in the complete sprint, including outside the horizon.",
        "Recurring decimal shares are shown as exact fractions (for example, 1/3 h).",
        "",
    ]
    names = {rule.id: rule.name for rule in plan.reservation_rules}
    if not results:
        lines.append("No reservation rules remain in this plan.")
    for result in results:
        available = sum((Fraction(day.available_hours) for day in result.days), Fraction())
        lines += [
            plan.person(result.person_id).name,
            f"Horizon {plan.horizon.start} to {plan.horizon.end}: "
            f"available {hours_text(available)} h; reserved {hours_text(result.reserved_hours)} h; "
            f"remaining {hours_text(result.remaining_hours)} h.",
        ]
        if not result.occurrences:
            lines.append("No active occurrences in this horizon; rules remain stored.")
        for occurrence in result.occurrences:
            days = [
                d
                for d in result.days
                if occurrence.included_period.start <= d.day <= occurrence.included_period.end
            ]
            before = sum((Fraction(d.available_hours) for d in days), Fraction())
            after = sum((d.remaining_hours for d in days), Fraction())
            remaining = hours_text(after) if result.remaining_hours is not None else "Unknown"
            lines += [
                f"  {names[occurrence.rule_id]}: sprint "
                f"{occurrence.period.start} to {occurrence.period.end}",
                f"  Applied dates {occurrence.included_period.start} "
                f"to {occurrence.included_period.end}; "
                f"eligible days {occurrence.included_days}/{occurrence.eligible_days}.",
                f"  Full-sprint duty {occurrence.requested_hours} h per person; "
                f"this rule reserves {hours_text(occurrence.reserved_hours)} h.",
                f"  Available in applied dates {hours_text(before)} h; "
                f"remaining after all rules {remaining} h.",
            ]
        for day in result.overlaps:
            lines.append(f"  Overlap {day.day}: " + ", ".join(names[i] for i in day.rule_ids))
        for day in result.overloaded_days:
            lines.append(
                f"  Over capacity {day.day}: remaining {hours_text(day.remaining_hours)} h."
            )
        lines.append("")
    return "\n".join(lines)


class ReservationWizard(QDialog):
    """Edits remain local until a successfully previewed candidate is confirmed."""

    def __init__(self, parent: QWidget, session: Session) -> None:
        super().__init__(parent)
        self.session = session
        self.original = session.document.plan
        if self.original is None:
            raise ValueError("Open a plan before reserving capacity.")
        self.candidate: ProgramPlan | None = None
        self.identifier = uuid4()
        self.setWindowTitle("Reserve capacity")
        self.resize(790, 680)
        layout = QVBoxLayout(self)
        self.heading = label("1. Configure recurring capacity", "heading")
        layout.addWidget(self.heading)
        self.steps = QStackedWidget()
        layout.addWidget(self.steps)
        fields_page = QWidget()
        form = QFormLayout(fields_page)
        self.rule_choice = QComboBox()
        self.rule_choice.setAccessibleName("Reservation to edit")
        self.rule_choice.addItem("New reservation", "")
        for rule in self.original.reservation_rules:
            self.rule_choice.addItem(rule.name, str(rule.id))
        form.addRow("&Rule", self.rule_choice)
        self.name = QLineEdit()
        self.name.setAccessibleName("Reservation name")
        self.name.setPlaceholderText("Meetings, Front office, or another duty")
        form.addRow("&Name", self.name)
        self.people = QListWidget()
        self.people.setAccessibleName("People receiving the reservation")
        for person in self.original.people:
            item = QListWidgetItem(person.name)
            item.setData(Qt.ItemDataRole.UserRole, str(person.id))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.people.addItem(item)
        form.addRow("&People", self.people)
        self.hours = QLineEdit()
        self.hours.setAccessibleName("Hours per person per sprint")
        form.addRow("&Hours per person per sprint", self.hours)
        self.total = label("")
        form.addRow("", self.total)
        self.anchor = CalendarLineEdit()
        self.anchor.setAccessibleName("Sprint anchor")
        self.interval = QLineEdit()
        self.interval.setAccessibleName("Sprint length in weeks")
        self.start, self.end = CalendarLineEdit(), CalendarLineEdit()
        self.start.setAccessibleName("Effective start")
        self.end.setAccessibleName("Effective end")
        for caption, editor in (
            ("&Anchor", self.anchor),
            ("&Weeks per sprint", self.interval),
            ("&Start", self.start),
            ("&End", self.end),
        ):
            form.addRow(caption, editor)
        form.addRow(
            "",
            label(
                "Each checked person receives these hours every sprint. "
                "Dates are inclusive; type YYYY-MM-DD or use the calendar. "
                "The anchor aligns sprints in both directions."
            ),
        )
        self.steps.addWidget(fields_page)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("Reservation preview")
        self.steps.addWidget(self.preview)
        self.error = label("")
        self.error.setAccessibleName("Reservation validation error")
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.delete_button = QPushButton("Preview &deletion")
        self.delete_button.clicked.connect(lambda: self.show_preview(delete=True))
        self.back = QPushButton("&Back")
        self.back.clicked.connect(self.go_back)
        self.next = QPushButton("&Preview")
        self.next.clicked.connect(lambda: self.show_preview())
        self.confirm = QPushButton("&Confirm")
        self.confirm.clicked.connect(self.apply)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        for button in (self.delete_button, self.back, self.next, self.confirm, cancel):
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.rule_choice.currentIndexChanged.connect(self.load_rule)
        self.hours.textChanged.connect(self.update_total)
        self.people.itemChanged.connect(self.update_total)
        self.load_rule()

    def selected_people(self) -> tuple[UUID, ...]:
        selected = tuple(
            UUID(self.people.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.people.count())
            if self.people.item(i).checkState() == Qt.CheckState.Checked
        )
        identifier = self.rule_choice.currentData()
        if identifier and self.original is not None:
            previous = reservation_rule(self.original, UUID(identifier)).person_ids
            return tuple(p for p in previous if p in selected) + tuple(
                p for p in selected if p not in previous
            )
        return selected

    def update_total(self) -> None:
        try:
            hours = Decimal(self.hours.text().strip())
            if not hours.is_finite() or hours <= 0:
                raise ValueError
            count = len(self.selected_people())
            self.total.setText(
                f"{hours} h x {count} people = "
                f"{hours_text(Fraction(hours) * count)} h per full sprint."
            )
        except (InvalidOperation, ValueError):
            self.total.setText("Enter positive hours per person, not a shared team total.")

    def load_rule(self) -> None:
        assert self.original is not None
        selected = self.rule_choice.currentData()
        rule = reservation_rule(self.original, UUID(selected)) if selected else None
        self.identifier = rule.id if rule else uuid4()
        self.name.setText(rule.name if rule else "")
        self.hours.setText(str(rule.hours_per_person) if rule else "")
        self.anchor.setText(str(rule.anchor if rule else self.original.horizon.start))
        self.interval.setText(str(rule.interval_weeks if rule else 2))
        self.start.setText(str(rule.effective.start if rule else self.original.horizon.start))
        self.end.setText(str(rule.effective.end if rule else self.original.horizon.end))
        for index in range(self.people.count()):
            item = self.people.item(index)
            checked = (
                rule is not None and UUID(item.data(Qt.ItemDataRole.UserRole)) in rule.person_ids
            )
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.go_back()
        self.update_total()

    def go_back(self) -> None:
        self.candidate = None
        self.heading.setText("1. Configure recurring capacity")
        self.steps.setCurrentIndex(0)
        self.error.setText("")
        self.back.setEnabled(False)
        self.confirm.setEnabled(False)
        self.next.setEnabled(True)
        self.delete_button.setEnabled(bool(self.rule_choice.currentData()))

    def show_preview(self, *, delete: bool = False) -> None:
        try:
            if self.session.document.plan is not self.original:
                raise ValueError("The plan changed. Cancel and reopen the wizard.")
            assert self.original is not None
            if delete:
                candidate = remove_reservation(self.original, self.identifier)
                name = reservation_rule(self.original, self.identifier).name
                heading = f"Delete reservation: {name}\n\n"
            else:
                if not self.name.text().strip():
                    raise ValueError("Enter a reservation name, such as Meetings or Front office.")
                if not self.selected_people():
                    raise ValueError(
                        "Select at least one person. Add people in People if the list is empty."
                    )
                dates = []
                for editor in (self.anchor, self.start, self.end):
                    value = editor.text().strip()
                    try:
                        parsed = date.fromisoformat(value)
                        if str(parsed) != value:
                            raise ValueError
                    except ValueError as error:
                        raise ValueError("Enter dates as YYYY-MM-DD.") from error
                    dates.append(parsed)
                try:
                    interval = int(self.interval.text().strip())
                    hours = Decimal(self.hours.text().strip())
                except (ValueError, InvalidOperation) as error:
                    raise ValueError("Enter positive hours and a whole number of weeks.") from error
                if interval <= 0 or not hours.is_finite() or hours <= 0:
                    raise ValueError(
                        "Hours and sprint length must be positive; weeks must be whole numbers."
                    )
                rule = ReservationRule(
                    id=self.identifier,
                    name=self.name.text(),
                    person_ids=self.selected_people(),
                    hours_per_person=hours,
                    anchor=dates[0],
                    interval_weeks=interval,
                    effective=PlanningHorizon(dates[1], dates[2]),
                )
                candidate = (
                    update_reservation(self.original, rule)
                    if self.rule_choice.currentData()
                    else add_reservation(self.original, rule)
                )
                heading = f"Save reservation: {rule.name}\n\n"
            try:
                results = preview_plan_reservations(candidate)
                report = preview_text(candidate, results)
            except ValueError as error:
                if not delete:
                    raise
                report = (
                    "Remaining rules cannot be calculated: "
                    + str(error)
                    + "\nYou can still confirm deletion of this rule. Other rules stay unchanged."
                )
            self.preview.setPlainText(heading + report)
            self.candidate = candidate
            self.heading.setText("2. Review and confirm")
            self.steps.setCurrentIndex(1)
            self.error.setText("")
            self.back.setEnabled(True)
            self.confirm.setEnabled(True)
            self.next.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.preview.setFocus()
        except ValueError as error:
            self.candidate = None
            self.confirm.setEnabled(False)
            self.error.setText(str(error))

    def apply(self) -> None:
        if self.session.document.plan is not self.original:
            self.error.setText("The plan changed. Cancel and reopen the wizard.")
            self.confirm.setEnabled(False)
            return
        if self.candidate is not None:
            self.session.apply(self.candidate)
            self.accept()


def reserve_capacity_dialog(parent: QWidget, session: Session) -> None:
    if session.document.plan is None:
        return
    dialog = ReservationWizard(parent, session)
    dialog.exec()
    dialog.deleteLater()
