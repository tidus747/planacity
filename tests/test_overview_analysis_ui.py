"""Overview exposes matching chart and table values in both appearances."""

from dataclasses import replace
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_capacity_breakdown import plan_with_capacity

from planacity.domain import WorkGroup
from planacity.ui.overview import AnalysisMode, TopicMeasure
from planacity.ui.theme import Theme


def load_overview(window):
    plan = plan_with_capacity()
    alpha = WorkGroup(name="Alpha")
    plan = replace(
        plan,
        work_items=(
            replace(plan.work_items[0], primary_group_id=alpha.id),
            *plan.work_items[1:],
        ),
        work_groups=(alpha,),
    )
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(0)
    return window.overview_page, plan


@pytest.mark.parametrize("theme", list(Theme))
def test_capacity_by_person_has_exact_accessible_table_and_chart(app, window, theme):
    page, plan = load_overview(window)
    window.set_theme(theme, persist=False)
    app.processEvents()

    assert page.analysis is not None
    assert page.mode.currentData() == AnalysisMode.PEOPLE.value
    assert page.model.rowCount() == len(plan.people) == 3
    assert page.model.horizontalHeaderItem(0).text() == "Person"
    assert page.model.item(0, 1).text() == "35 h"
    assert page.model.item(0, 2).text() == "28 h"
    assert page.model.item(0, 3).text() == "7 h"
    assert "Overloaded" in page.model.item(0, 5).text()
    assert page.model.item(1, 4).text() == "3 h"
    assert page.model.item(2, 1).text() == "Unknown"
    assert len(page.chart.rows) == 3
    assert "Alex" in page.chart.accessibleDescription()
    assert "complete current plan" in page.scope.text()
    assert "known-person subtotals" in page.coverage.text()
    assert not page.chart.grab().isNull()

    page.analysis_group.setChecked(False)
    app.processEvents()
    assert not page.analysis_content.isVisible()
    page.analysis_group.setChecked(True)
    assert page.analysis_content.isVisible()

    window.session.document.saved_plan = window.session.document.plan


def test_topic_measures_and_capacity_breakdown_share_one_projection(app, window):
    page, plan = load_overview(window)
    page.mode.setCurrentIndex(page.mode.findData(AnalysisMode.TOPICS.value))
    app.processEvents()

    assert page.measure.isVisible()
    assert page.model.horizontalHeaderItem(1).text() == "Scheduled allocated"
    assert tuple(page.model.item(row, 0).text() for row in range(page.model.rowCount())) == (
        f"Alpha [{str(plan.work_groups[0].id)[:8]}]",
        "Ungrouped",
    )
    assert tuple(page.model.item(row, 1).text() for row in range(page.model.rowCount())) == (
        "20 h",
        "8 h",
    )
    assert page.model.item(1, 2).text() == "3 h"

    page.measure.setCurrentIndex(page.measure.findData(TopicMeasure.ESTIMATED))
    app.processEvents()
    assert page.model.horizontalHeaderItem(1).text() == "Estimated leaf effort"
    assert tuple(page.model.item(row, 1).text() for row in range(page.model.rowCount())) == (
        "20 h",
        "11 h",
    )
    assert all("Whole plan" in page.model.item(row, 4).text() for row in range(2))

    page.mode.setCurrentIndex(page.mode.findData(AnalysisMode.BREAKDOWN.value))
    app.processEvents()
    components = tuple(page.model.item(row, 0).text() for row in range(page.model.rowCount()))
    assert components == (
        "Nominal calendar capacity",
        "Recorded unavailability",
        "Available before duties",
        f"Reservation: Meeting [{str(plan.reservation_rules[0].id)[:8]}]",
        "Planning capacity",
        "Scheduled work",
        "Remaining capacity",
        "Unplaced demand",
    )
    assert page.model.item(0, 1).text() == "80 h"
    assert page.model.item(3, 1).text() == "5 h"
    assert page.model.item(4, 1).text() == "75 h"
    assert page.model.item(5, 1).text() == "28 h"
    assert page.model.item(6, 1).text() == "47 h"
    assert page.model.item(7, 1).text() == "3 h"
    assert not page.measure.isVisible()
    window.session.document.saved_plan = window.session.document.plan


def test_overload_extends_past_capacity_reference_and_keyboard_reaches_controls(app, window):
    page, plan = load_overview(window)
    overloaded = replace(
        plan,
        allocations=(replace(plan.allocations[0], hours=Decimal(50)), *plan.allocations[1:]),
    )
    window.session.document.new(overloaded)
    window.session.document.saved_plan = overloaded
    window.session.changed.emit()
    app.processEvents()

    alex = page.chart.rows[0]
    assert alex.value == 58
    assert alex.reference == 35
    assert "remaining -23 h" in alex.detail
    assert "Overloaded" in alex.detail
    page.mode.setFocus()
    QTest.keyClick(page.mode, Qt.Key.Key_Down)
    app.processEvents()
    assert page.mode.currentData() == AnalysisMode.TOPICS.value
    assert page.table.focusPolicy() != Qt.FocusPolicy.NoFocus
    window.session.document.saved_plan = window.session.document.plan


def test_duplicate_person_names_remain_distinct_by_stable_id(window):
    page, plan = load_overview(window)
    duplicate = replace(plan.people[1], name=plan.people[0].name)
    changed = replace(plan, people=(plan.people[0], duplicate, plan.people[2]))
    window.session.document.new(changed)
    window.session.document.saved_plan = changed
    window.session.changed.emit()

    first = page.model.item(0, 0)
    second = page.model.item(1, 0)
    assert first.text().startswith("Alex [")
    assert second.text().startswith("Alex [")
    assert first.text() != second.text()
    assert first.data(Qt.ItemDataRole.UserRole) == str(changed.people[0].id)
    assert second.data(Qt.ItemDataRole.UserRole) == str(changed.people[1].id)
    window.session.document.saved_plan = window.session.document.plan
