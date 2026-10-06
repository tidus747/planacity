"""People filters and details explain derived WorkGroup associations."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_people_groups import plan_with_people_groups

import planacity.ui.editor_pages as editor_pages
from planacity.planning.people_groups import NO_ASSIGNED_WORK_KEY
from planacity.ui.theme import Theme


def _row_for_person(page, person_id) -> int:
    for row in range(page.model.rowCount()):
        if page.model.item(row, 0).data(Qt.ItemDataRole.UserRole) == str(person_id):
            return row
    raise AssertionError(f"Person {person_id} is not visible.")


@pytest.mark.parametrize("theme", list(Theme))
def test_roster_and_details_separate_whole_plan_context_from_range_hours(app, window, theme):
    plan = plan_with_people_groups()
    window.session.apply(plan)
    window.set_theme(theme, persist=False)
    window.show_page(3)
    page = window.people_page
    try:
        first_row = _row_for_person(page, plan.people[0].id)
        assert page.model.item(first_row, 13).text() == (
            "Alpha, Ambiguous group, Beta, Gamma, Ungrouped"
        )
        assert page.model.item(first_row, 9).text() == "14"
        assert page.model.item(first_row, 11).text() == "4"
        page.table.setCurrentIndex(page.model.index(first_row, 0))
        app.processEvents()

        assert page.group_model.rowCount() == 3
        assert tuple(
            page.group_model.item(row, 0).text() for row in range(page.group_model.rowCount())
        ) == (
            "Ambiguous group",
            f"Gamma [{str(plan.work_groups[2].id)[:8]}]",
            "Ungrouped",
        )
        assert page.group_model.item(0, 1).text() == "Alpha, Ambiguous group, Beta"
        assert page.group_model.item(0, 3).text() == "8"
        assert page.group_model.item(0, 4).text() == "8"
        assert page.group_model.item(2, 3).text() == "4"
        assert page.group_model.item(2, 4).text() == "0"
        assert page.group_model.item(2, 5).text() == "4"
        assert "whole-plan associations" in page.group_heading.text()
        assert "2026-10-05 to 2026-10-11" in page.group_heading.text()
        assert not page.group_table.grab().isNull()
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_group_filter_keeps_complete_capacity_and_no_assignment_state(window):
    plan = plan_with_people_groups()
    window.session.apply(plan)
    window.show_page(3)
    page = window.people_page
    try:
        gamma_key = f"group:{plan.work_groups[2].id}"
        page.group_filter.setCurrentIndex(page.group_filter.findData(gamma_key))

        assert page.model.rowCount() == 1
        assert page.model.item(0, 0).data(Qt.ItemDataRole.UserRole) == str(plan.people[0].id)
        assert page.model.item(0, 9).text() == "14"
        assert "all competing work" in page.group_filter_notice.text()
        assert page.group_model.rowCount() == 3

        page.group_filter.setCurrentIndex(page.group_filter.findData(NO_ASSIGNED_WORK_KEY))
        assert page.model.rowCount() == 1
        assert page.model.item(0, 0).data(Qt.ItemDataRole.UserRole) == str(plan.people[2].id)
        assert page.model.item(0, 13).text() == "No assigned work"
        assert page.group_model.rowCount() == 0
        assert "No assigned work" in page.group_heading.text()

        page.group_filter.setFocus()
        QTest.keyClick(page.group_filter, Qt.Key.Key_Home)
        assert page.group_filter.currentData() == ""
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_group_deletion_resets_filter_and_group_work_opens_allocation(app, window, monkeypatch):
    plan = plan_with_people_groups()
    window.session.apply(plan)
    window.show_page(3)
    page = window.people_page
    first_row = _row_for_person(page, plan.people[0].id)
    page.table.setCurrentIndex(page.model.index(first_row, 0))
    page.group_table.setCurrentIndex(page.group_model.index(1, 0))
    opened = []

    class AllocationDialogStub:
        def __init__(self, parent, session, work_id):
            opened.append(work_id)

        def exec(self):
            return 0

        def deleteLater(self):
            return None

    monkeypatch.setattr(editor_pages, "AllocationDialog", AllocationDialogStub)
    try:
        page.open_group_work()
        assert opened == [plan.work_items[2].id]

        gamma = plan.work_groups[2]
        page.group_filter.setCurrentIndex(page.group_filter.findData(f"group:{gamma.id}"))
        changed = replace(
            plan,
            work_groups=tuple(group for group in plan.work_groups if group.id != gamma.id),
            work_items=tuple(
                replace(item, primary_group_id=None) if item.primary_group_id == gamma.id else item
                for item in plan.work_items
            ),
        )
        window.session.apply(changed)
        app.processEvents()

        assert page.group_filter.currentData() == ""
        assert page.group_filter.findData(f"group:{gamma.id}") == -1
        assert page.model.rowCount() == len(plan.people)
    finally:
        window.session.document.saved_plan = window.session.document.plan
