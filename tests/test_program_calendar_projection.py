"""Shared event projections keep canonical data and all presentation views aligned."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton

from planacity.domain import CalendarEvent, CalendarEventKind, PlanningHorizon, ProgramPlan
from planacity.planning.program_calendar import (
    CalendarProjectionState,
    project_program_calendar,
)
from planacity.ui.main_window import MainWindow
from planacity.ui.overview import OverviewPage
from planacity.ui.session import Session
from planacity.ui.theme import Theme
from planacity.ui.timeline import TimelinePage


def calendar_projection_plan() -> ProgramPlan:
    def event(
        number: int,
        name: str,
        kind: CalendarEventKind,
        start: date,
        end: date,
        share: str,
    ) -> CalendarEvent:
        return CalendarEvent(
            id=UUID(int=number),
            name=name,
            kind=kind,
            period=PlanningHorizon(start, end),
            unavailable_fraction=Decimal(share),
        )

    return ProgramPlan(
        name="Calendar projection",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 11)),
        calendar_events=(
            event(
                4,
                "After horizon",
                CalendarEventKind.OTHER,
                date(2026, 2, 1),
                date(2026, 2, 2),
                "1",
            ),
            event(
                3,
                "Customer visit",
                CalendarEventKind.CUSTOMER_VISIT,
                date(2026, 1, 8),
                date(2026, 1, 8),
                "0",
            ),
            event(
                2,
                "Company days",
                CalendarEventKind.COMPANY_EVENT,
                date(2026, 1, 10),
                date(2026, 1, 14),
                "0.5",
            ),
            event(
                1,
                "Before horizon",
                CalendarEventKind.PUBLIC_HOLIDAY,
                date(2025, 12, 20),
                date(2025, 12, 20),
                "1",
            ),
        ),
    )


def test_projection_sorts_classifies_and_clips_only_display_coordinates() -> None:
    plan = calendar_projection_plan()
    events_before = plan.calendar_events

    projection = project_program_calendar(plan)

    assert tuple(entry.name for entry in projection.entries) == (
        "Before horizon",
        "Customer visit",
        "Company days",
        "After horizon",
    )
    assert tuple(entry.state for entry in projection.entries) == (
        CalendarProjectionState.OUTSIDE,
        CalendarProjectionState.INSIDE,
        CalendarProjectionState.PARTIAL,
        CalendarProjectionState.OUTSIDE,
    )
    assert projection.outside_count == 2
    assert projection.visible_entries[1].start == date(2026, 1, 10)
    assert projection.visible_entries[1].end == date(2026, 1, 14)
    assert projection.visible_entries[1].visible_start_day == 5
    assert projection.visible_entries[1].visible_end_day == 6
    assert plan.calendar_events == events_before


def test_overview_lists_visible_events_and_opens_calendar(app) -> None:
    session = Session()
    plan = calendar_projection_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    opened: list[str] = []
    page = OverviewPage(session, lambda: None, lambda: None, lambda: opened.append("calendar"))
    page.show()
    try:
        app.processEvents()
        assert page.calendar_model.rowCount() == 2
        assert "2 events in the horizon; 2 outside" in page.calendar_summary.text()
        assert page.calendar_model.index(0, 0).data() == "Customer visit"
        assert page.calendar_model.index(1, 2).data() == "2026-01-10 to 2026-01-14"
        open_button = next(
            button for button in page.findChildren(QPushButton) if button.text() == "Open Calendar"
        )
        open_button.click()
        assert opened == ["calendar"]
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_empty_views_explain_that_no_shared_events_intersect(app) -> None:
    session = Session()
    plan = ProgramPlan(
        name="Empty calendar",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 11)),
    )
    session.apply(plan)
    session.document.saved_plan = plan
    overview = OverviewPage(session, lambda: None, lambda: None, lambda: None)
    timeline = TimelinePage(session)
    try:
        assert overview.calendar_table.isHidden()
        assert "0 events in the horizon; 0 outside" in overview.calendar_summary.text()
        timeline.calendar_toggle.setChecked(True)
        assert timeline.calendar_panel.label_model.rowCount() == 0
        assert timeline.calendar_panel.details.toPlainText() == (
            "No shared events intersect this horizon."
        )
    finally:
        overview.deleteLater()
        timeline.deleteLater()
        app.processEvents()


def test_timeline_program_events_ignore_work_filters_and_survive_mode_and_scale(app) -> None:
    session = Session()
    plan = calendar_projection_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1200, 850)
    page.show()
    try:
        app.processEvents()
        assert not page.calendar_toggle.isChecked()
        page.calendar_toggle.setChecked(True)
        app.processEvents()
        panel = page.calendar_panel
        assert panel.isVisible()
        assert panel.label_model.rowCount() == 2
        assert "2 event lanes; 2 outside" in panel.message.text()
        assert "2026-01-08 to 2026-01-08" in panel.details.toPlainText()
        accessible = panel.schedule_model.index(0, 3).data(Qt.ItemDataRole.AccessibleTextRole)
        assert "Customer Visit" in accessible
        assert "No capacity reduction" in accessible

        page.search.setText("no work matches")
        assert panel.label_model.rowCount() == 2
        for scale, columns in (("week", 1), ("month", 1), ("day", 7)):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            assert panel.schedule_model.columnCount() == columns
            assert [panel.schedule.columnWidth(column) for column in range(columns)] == [
                page.schedule.columnWidth(column) for column in range(columns)
            ]

        page.mode_box.setCurrentIndex(page.mode_box.findData("team"))
        app.processEvents()
        assert page.calendar_toggle.isVisible()
        assert panel.isVisible()
        assert panel.label_model.rowCount() == 2
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    ("theme", "impact_color", "context_color"),
    (
        (Theme.LIGHT, "#8544ad", "#087c9d"),
        (Theme.DARK, "#d58cff", "#55c8e8"),
    ),
)
def test_timeline_distinguishes_impact_and_context_in_both_themes(
    app,
    settings,
    theme: Theme,
    impact_color: str,
    context_color: str,
) -> None:
    window = MainWindow(settings=settings)
    plan = calendar_projection_plan()
    window.session.apply(plan)
    window.session.document.saved_plan = plan
    window.set_theme(theme, persist=False)
    window.resize(1400, 900)
    window.show()
    window.show_page(2)
    window.timeline_page.calendar_toggle.setChecked(True)
    try:
        app.processEvents()
        panel = window.timeline_page.calendar_panel
        panel.labels.clearSelection()
        panel.schedule.clearSelection()
        app.processEvents()
        image = panel.schedule.viewport().grab().toImage()
        colors = {
            image.pixelColor(x, y).name()
            for y in range(image.height())
            for x in range(image.width())
        }
        assert QColor(impact_color).name() in colors
        assert QColor(context_color).name() in colors
        assert "No capacity reduction" in panel.label_model.index(0, 0).data(
            Qt.ItemDataRole.AccessibleTextRole
        )
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
