"""Explicit plan-wide estimate units with a calendar conversion preview."""

from uuid import UUID

from PySide6.QtWidgets import QComboBox, QPushButton, QWidget

from planacity.domain import ProgramPlan
from planacity.domain.estimate_units import EstimateUnit
from planacity.planning.estimate_units import conversion_description, set_estimate_preferences
from planacity.ui.forms import validated_form
from planacity.ui.pages import label
from planacity.ui.session import Session
from planacity.ui.work_calendars import manage_work_calendars


def choose_estimate_units(parent: QWidget, session: Session) -> None:
    plan = session.document.plan
    if plan is None:
        return
    draft = Session()
    draft.document.new(plan)
    units = QComboBox()
    units.setAccessibleName("Estimate unit")
    for unit in EstimateUnit:
        units.addItem(unit.value.title(), unit.value)
    units.setCurrentIndex(units.findData(plan.estimate_preferences.unit.value))
    calendars = QComboBox()
    calendars.setAccessibleName("Estimate reference calendar")
    setup = QPushButton("&Work calendars...")
    setup.setAutoDefault(False)
    setup.setAccessibleName("Manage estimate calendars")
    explanation = label("")
    explanation.setAccessibleName("Reference calendar guidance")
    preview = label("")
    preview.setAccessibleName("Estimate conversion preview")

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen estimate units.")
        return set_estimate_preferences(
            candidate(),
            EstimateUnit(units.currentData()),
            UUID(calendars.currentData()) if calendars.currentData() else None,
        )

    def candidate() -> ProgramPlan:
        current = draft.document.plan
        assert current is not None
        return current

    def populate(selected: str = "") -> None:
        calendars.blockSignals(True)
        calendars.clear()
        calendars.addItem("Choose a work calendar...", "")
        for calendar in candidate().work_calendars:
            suffix = " (no working hours)" if not any(calendar.weekday_hours) else ""
            calendars.addItem(calendar.name + suffix, str(calendar.id))
        calendars.setCurrentIndex(max(0, calendars.findData(selected)))
        calendars.blockSignals(False)

    def refresh() -> None:
        hours = units.currentData() == EstimateUnit.HOURS.value
        calendars.setEnabled(not hours and bool(candidate().work_calendars))
        explanation.setText(
            "Hours needs no reference calendar. Choose Days or Weeks to enable conversion."
            if hours
            else "No work calendars yet. Use Work calendars to create one, then select it here."
            if not candidate().work_calendars
            else "Choose a calendar with positive working hours. This converts effort units; "
            "it does not assign a calendar to any person."
        )
        try:
            preview.setText(conversion_description(build()))
        except ValueError as error:
            preview.setText(str(error))
        if setup.isVisible():
            preview.setMinimumHeight(preview.heightForWidth(preview.width()))
            setup.window().adjustSize()

    def manage() -> None:
        if session.document.plan is not plan:
            preview.setText("The plan changed. Cancel and reopen estimate units.")
            return
        selected = calendars.currentData() or ""
        manage_work_calendars(setup.window(), draft)
        populate(selected)
        refresh()

    setup.clicked.connect(manage)
    units.currentIndexChanged.connect(refresh)
    calendars.currentIndexChanged.connect(refresh)
    populate(str(plan.estimate_preferences.calendar_id or ""))
    refresh()
    updated = validated_form(
        parent,
        "Estimate units",
        [
            ("&Unit", units),
            ("&Reference calendar", calendars),
            ("", explanation),
            ("", setup),
            ("Conversion", preview),
            (
                "",
                label(
                    "OK applies unit settings and calendar changes made here. "
                    "Cancel discards both. Stored effort hours remain unchanged."
                ),
            ),
        ],
        build,
    )
    if updated is not None:
        session.apply(updated)
