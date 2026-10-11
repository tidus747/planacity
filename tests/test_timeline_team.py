"""Team Timeline reconciles canonical work, absences, duties, and capacity."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from planacity.domain import (
    Allocation,
    AvailabilityEvent,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    ReservationRule,
    WorkCalendar,
    WorkItem,
    WorkItemType,
)
from planacity.planning.capacity_breakdown import CapacityLoadState
from planacity.planning.timeline_team import project_team_timeline
from planacity.ui.main_window import MainWindow
from planacity.ui.session import Session
from planacity.ui.theme import Theme
from planacity.ui.timeline import TimelinePage


def team_plan() -> ProgramPlan:
    alice = Person(name="Alice")
    bob = Person(name="Bob")
    calendar = WorkCalendar(
        name="Standard",
        weekday_hours=(Decimal(8),) * 5 + (Decimal(0),) * 2,
    )
    dated = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        assignee_id=alice.id,
        start=date(2026, 1, 5),
        end=date(2026, 1, 9),
    )
    undated = WorkItem(
        title="Follow-up",
        kind=WorkItemType.TASK,
        assignee_id=alice.id,
    )
    horizon = PlanningHorizon(date(2026, 1, 5), date(2026, 1, 11))
    return ProgramPlan(
        name="Team mode",
        horizon=horizon,
        people=(alice, bob),
        work_items=(dated, undated),
        work_calendars=(calendar,),
        person_calendars=(PersonCalendar(person_id=alice.id, calendar_id=calendar.id),),
        availability_events=(
            AvailabilityEvent(
                person_id=alice.id,
                period=PlanningHorizon(date(2026, 1, 7), date(2026, 1, 7)),
                unavailable_fraction=Decimal("0.5"),
            ),
        ),
        reservation_rules=(
            ReservationRule(
                name="Meetings",
                person_ids=(alice.id,),
                hours_per_person=Decimal(5),
                anchor=horizon.start,
                interval_weeks=1,
                effective=horizon,
            ),
        ),
        allocations=(
            Allocation(work_item_id=dated.id, person_id=alice.id, hours=Decimal(20)),
            Allocation(work_item_id=undated.id, person_id=alice.id, hours=Decimal(3)),
        ),
    )


def test_team_projection_reconciles_sources_and_keeps_incomplete_inputs() -> None:
    plan = team_plan()
    original_allocations = plan.allocations

    projection = project_team_timeline(plan)

    assert projection.horizon == plan.horizon
    assert tuple(person.person_name for person in projection.people) == ("Alice", "Bob")
    alice, bob = projection.people
    assert [
        (entry.title, entry.visible_start_day, entry.visible_end_day, entry.hours)
        for entry in alice.work
    ] == [("Integration", 0, 4, Fraction(20))]
    assert [(entry.title, entry.hours) for entry in alice.unplaced_work] == [
        ("Follow-up", Fraction(3))
    ]
    assert (alice.absences[0].visible_start_day, alice.absences[0].unavailable_fraction) == (
        2,
        Decimal("0.5"),
    )
    assert sum((duty.hours for day in alice.duty_days for duty in day.duties), Fraction()) == 5
    assert len(alice.weeks) == 1
    week = alice.weeks[0]
    assert (week.planning_hours, week.allocated_hours, week.remaining_hours) == (31, 20, 11)
    assert week.state == CapacityLoadState.INCOMPLETE
    assert any("Set both dates" in gap.message for gap in week.gaps)
    assert bob.work == bob.absences == bob.duty_days == ()
    assert bob.weeks[0].state == CapacityLoadState.UNKNOWN
    assert any("work calendar" in gap.message for gap in bob.gaps)
    assert plan.allocations is original_allocations


def test_team_projection_preserves_each_legacy_person_allocation() -> None:
    plan = team_plan()
    dated = plan.work_items[0]
    bob = plan.people[1]
    legacy = replace(
        plan,
        allocations=(
            *plan.allocations,
            Allocation(work_item_id=dated.id, person_id=bob.id, hours=Decimal(4)),
        ),
    )

    projection = project_team_timeline(legacy)

    assert [(entry.title, entry.hours) for entry in projection.people[0].work] == [
        ("Integration", Fraction(20))
    ]
    assert [(entry.title, entry.hours) for entry in projection.people[1].work] == [
        ("Integration", Fraction(4))
    ]


def test_team_mode_is_read_only_aligned_and_independent_from_plan_filters(app) -> None:
    session = Session()
    plan = team_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1350, 850)
    page.show()
    try:
        app.processEvents()
        assert page.mode_box.currentData() == "plan"
        assert page.splitter.isVisible()
        assert not page.team_panel.isVisible()

        page.search.setText("no work matches")
        page.mode_box.setCurrentIndex(page.mode_box.findData("team"))
        page.scale_box.setCurrentIndex(page.scale_box.findData("week"))
        app.processEvents()

        panel = page.team_panel
        assert panel.isVisible()
        assert not page.splitter.isVisible()
        assert panel.label_model.rowCount() == 8
        for scale, columns in (("day", 7), ("week", 1), ("month", 1)):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            assert panel.schedule_model.columnCount() == columns
            assert [panel.schedule.columnWidth(column) for column in range(columns)] == [
                page.schedule.columnWidth(column) for column in range(columns)
            ]
        page.scale_box.setCurrentIndex(page.scale_box.findData("week"))
        assert "2 roster people" in page.summary.text()
        duties = panel.schedule_model.index(2, 0).data(Qt.ItemDataRole.AccessibleTextRole)
        load = panel.schedule_model.index(3, 0).data(Qt.ItemDataRole.AccessibleTextRole)
        missing_calendar = panel.schedule_model.index(7, 0).data(Qt.ItemDataRole.AccessibleTextRole)
        assert "Meetings, 5 h reserved" in duties
        assert "20 h allocated / 31 h planning" in load
        assert "Follow-up" not in duties
        assert "Assign a work calendar to 'Bob'" in missing_calendar
        assert session.document.plan is plan
        assert not session.document.dirty

        page.mode_box.setCurrentIndex(page.mode_box.findData("plan"))
        assert page.splitter.isVisible()
        assert not panel.isVisible()
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    ("theme", "load_color"),
    ((Theme.LIGHT, "#d6c9f0"), (Theme.DARK, "#8e7cc3")),
)
def test_team_load_lane_renders_in_both_themes(
    app, settings, theme: Theme, load_color: str
) -> None:
    window = MainWindow(settings=settings)
    window.session.apply(team_plan())
    window.resize(1400, 900)
    window.set_theme(theme, persist=False)
    window.show()
    window.show_page(2)
    page = window.timeline_page
    page.mode_box.setCurrentIndex(page.mode_box.findData("team"))
    page.scale_box.setCurrentIndex(page.scale_box.findData("week"))
    try:
        app.processEvents()
        panel = page.team_panel
        panel.labels.clearSelection()
        panel.schedule.clearSelection()
        app.processEvents()
        image = panel.schedule.viewport().grab().toImage()
        rect = panel.schedule.visualRect(panel.schedule_model.index(3, 0))
        expected = QColor(load_color).name()
        assert not image.isNull()
        assert any(
            image.pixelColor(x, y).name() == expected
            for y in range(rect.top(), rect.bottom() + 1)
            for x in range(rect.left(), rect.right() + 1)
        )
    finally:
        window.session.document.saved_plan = window.session.document.plan
        window.close()
        window.deleteLater()
        app.processEvents()
