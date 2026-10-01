"""Explicit plan-wide estimate units with a calendar conversion preview."""

from uuid import UUID

from PySide6.QtWidgets import QComboBox, QWidget

from planacity.domain import ProgramPlan
from planacity.domain.estimate_units import EstimateUnit
from planacity.planning.estimate_units import conversion_description, set_estimate_preferences
from planacity.ui.forms import validated_form
from planacity.ui.pages import label
from planacity.ui.session import Session


def choose_estimate_units(parent: QWidget, session: Session) -> None:
    plan = session.document.plan
    if plan is None:
        return
    units = QComboBox()
    units.setAccessibleName("Estimate unit")
    for unit in EstimateUnit:
        units.addItem(unit.value.title(), unit.value)
    units.setCurrentIndex(units.findData(plan.estimate_preferences.unit.value))
    calendars = QComboBox()
    calendars.setAccessibleName("Estimate reference calendar")
    calendars.addItem("Choose a work calendar...", "")
    for calendar in plan.work_calendars:
        calendars.addItem(calendar.name, str(calendar.id))
    if plan.estimate_preferences.calendar_id is not None:
        calendars.setCurrentIndex(calendars.findData(str(plan.estimate_preferences.calendar_id)))
    preview = label("")
    preview.setAccessibleName("Estimate conversion preview")

    def build() -> ProgramPlan:
        if session.document.plan is not plan:
            raise ValueError("The plan changed. Cancel and reopen estimate units.")
        return set_estimate_preferences(
            plan,
            EstimateUnit(units.currentData()),
            UUID(calendars.currentData()) if calendars.currentData() else None,
        )

    def refresh() -> None:
        calendars.setEnabled(units.currentData() != EstimateUnit.HOURS.value)
        try:
            preview.setText(conversion_description(build()))
        except ValueError as error:
            preview.setText(str(error) + " Manage calendars in People -> Work calendars.")

    units.currentIndexChanged.connect(refresh)
    calendars.currentIndexChanged.connect(refresh)
    refresh()
    updated = validated_form(
        parent,
        "Estimate units",
        [("&Unit", units), ("&Reference calendar", calendars), ("Conversion", preview)],
        build,
    )
    if updated is not None:
        session.apply(updated)
