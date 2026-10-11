"""Timeline unavailability lanes remain read-only, explicit, and theme-aware."""

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from planacity.domain import AvailabilityEvent, Person, PlanningHorizon, ProgramPlan
from planacity.planning.timeline_availability import project_timeline_unavailability
from planacity.ui.main_window import MainWindow
from planacity.ui.session import Session
from planacity.ui.theme import Theme
from planacity.ui.timeline import TimelinePage


def unavailability_plan() -> ProgramPlan:
    alice, bob, cara = (Person(name=name) for name in ("Alice", "Bob", "Cara"))
    return ProgramPlan(
        name="Unavailability",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 11)),
        people=(bob, cara, alice),
        availability_events=(
            AvailabilityEvent(
                person_id=alice.id,
                period=PlanningHorizon(date(2025, 12, 30), date(2026, 1, 6)),
                unavailable_fraction=Decimal("0.5"),
            ),
            AvailabilityEvent(
                person_id=alice.id,
                period=PlanningHorizon(date(2026, 1, 8), date(2026, 1, 9)),
                unavailable_fraction=Decimal(1),
            ),
            AvailabilityEvent(
                person_id=alice.id,
                period=PlanningHorizon(date(2026, 1, 10), date(2026, 1, 10)),
                unavailable_fraction=Decimal(0),
            ),
            AvailabilityEvent(
                person_id=bob.id,
                period=PlanningHorizon(date(2026, 1, 10), date(2026, 1, 14)),
                unavailable_fraction=Decimal("0.25"),
            ),
            AvailabilityEvent(
                person_id=cara.id,
                period=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 2)),
                unavailable_fraction=Decimal(1),
            ),
        ),
    )


def test_unavailability_projection_preserves_canonical_entries_and_clips_display() -> None:
    projection = project_timeline_unavailability(unavailability_plan())

    assert projection.total_days == 7
    assert tuple(lane.person_name for lane in projection.lanes) == ("Alice", "Bob")
    alice, bob = projection.lanes
    assert len(alice.entries) == 2
    assert (alice.entries[0].start, alice.entries[0].end) == (
        date(2025, 12, 30),
        date(2026, 1, 6),
    )
    assert (alice.entries[0].visible_start_day, alice.entries[0].visible_end_day) == (0, 1)
    assert (alice.entries[1].visible_start_day, alice.entries[1].visible_end_day) == (3, 4)
    assert (bob.entries[0].visible_start_day, bob.entries[0].visible_end_day) == (5, 6)


def test_empty_unavailability_projection_keeps_the_horizon_explicit() -> None:
    plan = ProgramPlan(
        name="Empty",
        horizon=PlanningHorizon(date(2026, 1, 5), date(2026, 1, 11)),
    )

    projection = project_timeline_unavailability(plan)

    assert projection.horizon == plan.horizon
    assert projection.total_days == 7
    assert projection.lanes == ()


def test_unavailability_toggle_filters_scales_and_keyboard_do_not_edit_plan(app) -> None:
    session = Session()
    plan = unavailability_plan()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1200, 850)
    page.show()
    try:
        app.processEvents()
        assert not page.availability_toggle.isChecked()
        assert not page.availability_panel.isVisible()

        page.availability_toggle.setChecked(True)
        app.processEvents()
        assert page.availability_panel.isVisible()
        panel = page.availability_panel
        assert panel.label_model.rowCount() == 2
        assert panel.schedule_model.rowCount() == 2
        assert "2 person lanes" in panel.message.text()
        assert "2025-12-30 to 2026-01-06" in panel.details.toPlainText()
        accessible = panel.schedule_model.index(0, 0).data(Qt.ItemDataRole.AccessibleTextRole)
        assert "Alice" in accessible
        assert "Unavailable share 0.5 (partial)" in accessible
        assert "2025-12-30 to 2026-01-06" in accessible

        page.search.setText("no work matches")
        assert panel.label_model.rowCount() == 2
        for scale, columns in (("week", 1), ("month", 1), ("day", 7)):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            assert panel.schedule_model.columnCount() == columns
            assert [panel.schedule.columnWidth(column) for column in range(columns)] == [
                page.schedule.columnWidth(column) for column in range(columns)
            ]

        panel.labels.setFocus()
        QTest.keyClick(panel.labels, Qt.Key.Key_Down)
        app.processEvents()
        assert "Bob" in panel.details.toPlainText()
        assert session.document.plan is plan
        assert not session.document.dirty

        page.availability_toggle.setChecked(False)
        assert not page.availability_panel.isVisible()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize(
    ("theme", "color"),
    ((Theme.LIGHT, "#ad5100"), (Theme.DARK, "#f0a34a")),
)
def test_unavailability_hatching_and_share_height_render_in_both_themes(
    app, settings, theme: Theme, color: str
) -> None:
    window = MainWindow(settings=settings)
    window.session.apply(unavailability_plan())
    window.resize(1400, 900)
    window.set_theme(theme, persist=False)
    window.show()
    window.show_page(2)
    page = window.timeline_page
    page.availability_toggle.setChecked(True)
    try:
        app.processEvents()
        panel = page.availability_panel
        panel.schedule.clearSelection()
        panel.labels.clearSelection()
        app.processEvents()
        image = panel.schedule.viewport().grab().toImage()
        assert not image.isNull()
        expected = QColor(color).name()
        partial = panel.schedule.visualRect(panel.schedule_model.index(0, 0))
        full = panel.schedule.visualRect(panel.schedule_model.index(0, 3))

        def colored_rows(rect) -> list[int]:
            return [
                y
                for y in range(rect.top(), rect.bottom() + 1)
                if any(
                    image.pixelColor(x, y).name() == expected
                    for x in range(rect.left(), rect.right() + 1)
                )
            ]

        partial_rows, full_rows = colored_rows(partial), colored_rows(full)
        assert partial_rows and full_rows
        assert min(partial_rows) > min(full_rows)
    finally:
        window.session.document.saved_plan = window.session.document.plan
        window.close()
        window.deleteLater()
        app.processEvents()
