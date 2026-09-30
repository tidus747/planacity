"""Integration of Timeline filters, grouped identities and dependency rendering."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_timeline_dependencies import dependency_plan
from test_timeline_view import grouped_plan

from planacity.domain import Relationship, RelationshipType
from planacity.ui.session import Session
from planacity.ui.timeline import ROW_ROLE, TimelinePage


def test_filters_group_selection_and_clear_do_not_edit_plan(app):
    session = Session()
    plan = grouped_plan()
    session.apply(plan)
    page = TimelinePage(session)
    page.resize(1440, 800)
    page.show()
    try:
        page.grouping_box.setCurrentIndex(page.grouping_box.findData("workgroup"))
        assert page.label_model.rowCount() == 7
        assert "1 scheduled | 0 partial | 3 unscheduled" in page.summary.text()
        page._select_row(4)
        selected = page.labels.currentIndex().data(ROW_ROLE)
        assert selected.section == "Delivery"
        QTest.keyClicks(page.search, "sensor")
        assert page.label_model.rowCount() == 4
        assert page.labels.currentIndex().data(ROW_ROLE).section_id == selected.section_id
        page.kind_filter.setCurrentIndex(page.kind_filter.findData("task"))
        page.state_filter.setCurrentIndex(page.state_filter.findData("scheduled"))
        page.group_filter.setCurrentIndex(1)
        assert page.label_model.rowCount() == 1
        page.search.setText("nothing matches")
        assert page.label_model.rowCount() == 0
        assert "No matching" in page.summary.text()
        QTest.mouseClick(page.clear_filters, Qt.MouseButton.LeftButton)
        assert page.label_model.rowCount() == 7
        page.grouping_box.setCurrentIndex(0)
        assert page.label_model.rowCount() == 4
        assert page.labels.isColumnHidden(2)
        assert session.document.plan is plan
        # Removing a WorkGroup safely resets its obsolete filter choice.
        page.group_filter.setCurrentIndex(1)
        session.apply(replace(plan, work_groups=()))
        assert page.group_filter.currentData() == ""
        assert page.label_model.rowCount() == 4
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("scale", ["day", "week", "month"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_dependency_endpoints_follow_scale_scroll_theme_and_filters(app, settings, scale, theme):
    from planacity.ui.main_window import MainWindow
    from planacity.ui.theme import Theme

    window = MainWindow(settings=settings)
    plan = dependency_plan()
    window.session.apply(plan)
    window.resize(1440, 900)
    window.set_theme(Theme(theme))
    window.show()
    window.show_page(2)
    page = window.timeline_page
    try:
        page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
        app.processEvents()
        paths = page.schedule.dependency_paths()
        assert len(paths) == 1
        path = paths[0]
        axis = page.schedule_model.axis
        assert axis is not None
        end_col = axis.column_for_day(3)
        period = axis.period(end_col)
        expected_x = page.schedule.columnViewportPosition(end_col) + (
            4 - period.start_day
        ) / period.days * page.schedule.columnWidth(end_col)
        assert path[0][0] == pytest.approx(expected_x)
        assert path[-1][1] > path[0][1]
        assert not page.schedule.viewport().grab().isNull()
        assert "Build -> Verify" in page.dependency_details.toPlainText()
        page._select_row(1)
        assert "depends_on" in page.dependency_details.toPlainText()
        page.search.setText("Verify")
        assert not page.schedule.dependency_paths()
        assert "hidden by filters" in page.dependency_details.toPlainText()
        page.clear_filters.click()
        with_arrows = page.schedule.viewport().grab().toImage()
        page.dependency_toggle.setChecked(False)
        assert not page.schedule.dependency_paths()
        assert page.schedule.viewport().grab().toImage() != with_arrows
        page.dependency_toggle.setChecked(True)
        assert len(page.schedule.dependency_paths()) == 1
        if scale == "day":
            page.schedule.horizontalScrollBar().setValue(34 * 10)
            assert not page.schedule.dependency_paths()
        assert window.session.document.plan is plan
    finally:
        window.session.document.saved_plan = window.session.document.plan
        window.close()
        window.deleteLater()
        app.processEvents()


def test_dependency_occurrences_follow_workgroup_sections(app):
    plan = grouped_plan()
    standalone, task, epic, sub = plan.work_items
    sub = replace(sub, start=date(2026, 1, 6), end=date(2026, 1, 7))
    plan = replace(
        plan,
        work_items=(standalone, task, epic, sub),
        relationships=(
            Relationship(source_id=task.id, target_id=sub.id, kind=RelationshipType.BLOCKS),
        ),
    )
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1440, 900)
    page.show()
    try:
        page.grouping_box.setCurrentIndex(page.grouping_box.findData("workgroup"))
        app.processEvents()
        assert len(page.schedule.dependency_paths()) == 2
        page.group_filter.setCurrentIndex(1)
        app.processEvents()
        assert len(page.schedule.dependency_paths()) == 1
        assert {row.section for row in page.projection.rows} == {"Hardware"}
        page.clear_filters.click()
        page.grouping_box.setCurrentIndex(page.grouping_box.findData("epic"))
        app.processEvents()
        assert len(page.schedule.dependency_paths()) == 1
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
