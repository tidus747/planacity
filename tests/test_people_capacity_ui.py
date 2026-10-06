"""People presents exact dated capacity and links each source back to its editor."""

from datetime import date

import pytest
from test_capacity_breakdown import MONDAY, WEEK, plan_with_capacity

import planacity.ui.editor_pages as editor_pages
from planacity.planning.capacity_breakdown import CapacityBucketScale
from planacity.ui.reservations import ReservationWizard
from planacity.ui.theme import Theme


@pytest.mark.parametrize("theme", list(Theme))
def test_people_capacity_totals_ranges_and_heatmap(window, theme):
    plan = plan_with_capacity()
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(3)
    page = window.people_page
    try:
        assert page.model.rowCount() == 3
        assert [page.model.item(0, column).text() for column in range(7, 13)] == [
            "5",
            "35",
            "28",
            "7",
            "0",
            "Overloaded",
        ]
        assert page.model.item(1, 11).text() == "3"
        assert page.model.item(1, 12).text() == "Incomplete"
        assert page.model.item(2, 8).text() == "Unknown"
        assert page.model.item(2, 12).text() == "Unknown"

        page.table.setCurrentIndex(page.model.index(0, 0))
        assert page.detail_model.rowCount() == 1
        assert page.detail_model.item(0, 0).text() == "2026-10-05 to 2026-10-11"
        assert page.detail_model.item(0, 4).text() == "Overloaded"

        page.scale.setCurrentIndex(page.scale.findData(CapacityBucketScale.DAY.value))
        assert page.detail_model.rowCount() == 7
        assert page.detail_model.item(0, 3).text() == "-5"
        assert page.detail_model.item(0, 4).text() == "Overloaded"
        assert page.reservation_choice.count() == 1
        assert page.work_choice.count() == 2

        page.range_start.setText("2026-10-06")
        page.apply_range("day")
        assert page.period.start == page.period.end == date(2026, 10, 6)
        assert page.model.item(0, 8).text() == "7"
        assert page.model.item(0, 9).text() == "4"
        assert page.model.item(0, 10).text() == "3"
        assert page.model.item(0, 12).text() == "Within capacity"

        previous = page.period
        page.range_start.setText("2026-10-07")
        page.range_end.setText("2026-10-06")
        page.apply_range("custom")
        assert page.period == previous
        assert "start on or before the end" in page.range_error.text()

        page.apply_range("horizon")
        assert page.period == WEEK
        assert page.range_start.text() == str(WEEK.start)
        assert page.range_end.text() == str(WEEK.end)
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_capacity_sources_open_the_matching_editors(window, monkeypatch):
    plan = plan_with_capacity()
    window.session.apply(plan)
    window.show_page(3)
    page = window.people_page
    page.table.setCurrentIndex(page.model.index(0, 0))
    page.scale.setCurrentIndex(page.scale.findData(CapacityBucketScale.DAY.value))
    opened: list[tuple[str, object]] = []

    def reservation(parent, session, rule_id=None):
        opened.append(("reservation", rule_id))

    class AllocationDialogStub:
        def __init__(self, parent, session, work_id):
            opened.append(("work", work_id))

        def exec(self):
            return 0

        def deleteLater(self):
            return None

    monkeypatch.setattr(editor_pages, "reserve_capacity_dialog", reservation)
    monkeypatch.setattr(editor_pages, "AllocationDialog", AllocationDialogStub)
    try:
        page.open_reservation()
        selected_work = page.work_choice.currentData()
        page.open_work()

        assert opened == [
            ("reservation", plan.reservation_rules[0].id),
            (
                "work",
                plan.work_item(next(iter(page.detail_buckets[0].allocations)).work_item_id).id,
            ),
        ]
        assert selected_work == str(opened[1][1])

        dialog = ReservationWizard(window, window.session, plan.reservation_rules[0].id)
        assert dialog.rule_choice.currentData() == str(plan.reservation_rules[0].id)
        dialog.reject()
        dialog.deleteLater()
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_week_shortcut_is_seven_inclusive_days(window):
    window.session.apply(plan_with_capacity())
    page = window.people_page
    try:
        page.range_start.setText(str(MONDAY))
        page.apply_range("week")
        assert page.period == WEEK
    finally:
        window.session.document.saved_plan = window.session.document.plan
