"""Exercise the read-only Timeline without a visible desktop."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.timeline_axis import TimelineScale
from planacity.ui.main_window import MainWindow
from planacity.ui.session import Session
from planacity.ui.theme import COLORS, Theme
from planacity.ui.timeline import TimelinePage


def _sample_plan() -> ProgramPlan:
    epic = WorkItem(
        title="Integration",
        kind=WorkItemType.EPIC,
        start=date(2026, 1, 2),
        end=date(2026, 1, 6),
    )
    start_only = WorkItem(
        title="Commission rig",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        start=date(2026, 1, 5),
    )
    end_only = WorkItem(
        title="Receive fixture",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        end=date(2026, 1, 8),
    )
    unscheduled = WorkItem(title="Release notes", kind=WorkItemType.TASK)
    return ProgramPlan(
        name="Aurora",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 14)),
        work_items=(epic, start_only, end_only, unscheduled),
    )


def test_timeline_models_expose_projection_states_and_accessibility(app: QApplication) -> None:
    session = Session()
    page = TimelinePage(session)
    page.resize(1000, 600)
    page.show()
    try:
        session.apply(_sample_plan())
        app.processEvents()

        assert page.label_model.rowCount() == 4
        assert page.schedule_model.rowCount() == 4
        assert page.schedule_model.columnCount() == 14
        assert page.label_model.index(1, 0).data() == "    Commission rig"
        assert page.label_model.index(1, 1).data() == "Starts 2026-01-05; no end"
        assert page.label_model.index(2, 1).data() == "Ends 2026-01-08; no start"
        assert page.label_model.index(3, 1).data() == "Unscheduled"
        assert page.schedule_model.headerData(0, Qt.Orientation.Horizontal) == "Jan 1"
        assert page.schedule_model.headerData(1, Qt.Orientation.Horizontal) == "2"
        assert "1 scheduled | 2 partial | 1 unscheduled" in page.summary.text()
        assert page.labels.accessibleName() == "Timeline work items and schedule states"
        assert page.schedule.accessibleName() == "Timeline schedule by day"
        assert not page.label_model.flags(page.label_model.index(0, 0)) & Qt.ItemFlag.ItemIsEditable
        assert (
            not page.schedule_model.flags(page.schedule_model.index(0, 0))
            & Qt.ItemFlag.ItemIsEditable
        )
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_timeline_keeps_selection_by_identity_and_synchronizes_views(
    app: QApplication,
) -> None:
    session = Session()
    page = TimelinePage(session)
    page.resize(900, 480)
    page.show()
    try:
        plan = _sample_plan()
        session.apply(plan)
        page.labels.setCurrentIndex(page.label_model.index(1, 0))
        app.processEvents()
        selected_id = page.labels.currentIndex().data(Qt.ItemDataRole.UserRole)
        assert page.schedule.currentIndex().row() == 1

        page.labels.setFocus()
        QTest.keyClick(page.labels, Qt.Key.Key_Down)
        app.processEvents()
        assert page.labels.currentIndex().row() == 2
        assert page.schedule.currentIndex().row() == 2
        page.labels.setCurrentIndex(page.label_model.index(1, 0))
        app.processEvents()

        epic, start_only, end_only, unscheduled = plan.work_items
        session.apply(replace(plan, work_items=(epic, end_only, start_only, unscheduled)))
        app.processEvents()

        assert page.labels.currentIndex().row() == 2
        assert page.schedule.currentIndex().row() == 2
        assert page.labels.currentIndex().data(Qt.ItemDataRole.UserRole) == selected_id

        page.schedule.setCurrentIndex(page.schedule_model.index(3, 5))
        app.processEvents()
        assert page.labels.currentIndex().row() == 3
        assert page.schedule.currentIndex().column() == 5
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_timeline_scrolls_labels_and_schedule_together(app: QApplication) -> None:
    session = Session()
    page = TimelinePage(session)
    page.resize(720, 360)
    page.show()
    try:
        work = tuple(
            WorkItem(
                title=f"Scheduled task {number}",
                kind=WorkItemType.TASK,
                start=date(2026, 1, 2),
                end=date(2026, 2, 20),
            )
            for number in range(30)
        )
        session.apply(
            ProgramPlan(
                name="Long plan",
                horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 3, 31)),
                work_items=work,
            )
        )
        app.processEvents()

        vertical = page.schedule.verticalScrollBar()
        horizontal = page.schedule.horizontalScrollBar()
        assert vertical.maximum() > 0
        assert horizontal.maximum() > 0
        vertical.setValue(vertical.maximum() // 2)
        horizontal.setValue(horizontal.maximum() // 2)
        app.processEvents()
        assert page.labels.verticalScrollBar().value() == vertical.value()
        assert horizontal.value() > 0
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("theme", list(Theme))
@pytest.mark.parametrize("scale", list(TimelineScale))
def test_timeline_bar_renders_with_active_appearance(
    app: QApplication, window: MainWindow, theme: Theme, scale: TimelineScale
) -> None:
    try:
        window.session.apply(_sample_plan())
        window.show_page(2)
        window.set_theme(theme, persist=False)
        app.processEvents()

        page = window.timeline_page
        page.scale_box.setCurrentIndex(page.scale_box.findData(scale.value))
        app.processEvents()
        axis = page.schedule_model.axis
        column = axis.column_for_day(3)
        period = axis.period(column)
        bar_index = page.schedule_model.index(0, column)
        bar_rect = page.schedule.visualRect(bar_index)
        assert bar_rect.isValid()
        image = page.schedule.viewport().grab().toImage()
        assert not image.isNull()
        x = bar_rect.left() + int((3.5 - period.start_day) / period.days * bar_rect.width())
        assert (
            image.pixelColor(x, bar_rect.center().y()).name() == QColor(COLORS[theme].accent).name()
        )
    finally:
        window.session.document.saved_plan = window.session.document.plan


def _left_visible_day(page):
    column = max(0, page.schedule.columnAt(0))
    period = page.schedule_model.axis.period(column)
    fraction = -page.schedule.columnViewportPosition(column) / page.schedule.columnWidth(column)
    return period.start_day + fraction * period.days


def test_scale_switch_keeps_work_and_visible_dates_without_editing_plan(app, settings):
    session = Session()
    plan = replace(_sample_plan(), horizon=PlanningHorizon(date(2026, 1, 1), date(2027, 12, 31)))
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session, settings)
    page.resize(1000, 500)
    page.show()
    try:
        app.processEvents()
        page._select_row(1, 180)
        page.schedule.horizontalScrollBar().setValue(150 * 34 + 10)
        app.processEvents()
        selected = page._selected_id()
        anchor = _left_visible_day(page)
        for scale in ("week", "month", "day", "month", "week", "day"):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            app.processEvents()
            assert page._selected_id() == selected
            assert abs(_left_visible_day(page) - anchor) < 1
            assert session.document.plan is plan
            assert not session.document.dirty
        page.scale_box.setFocus()
        QTest.keyClick(page.scale_box, Qt.Key.Key_End)
        app.processEvents()
        assert page.schedule_model.scale == TimelineScale.MONTH
        assert settings.value("timeline/scale") == "month"
        restored = TimelinePage(session, settings)
        assert restored.schedule_model.scale == TimelineScale.MONTH
        assert restored.schedule_model.columnCount() == 24
        restored.deleteLater()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_scale_edge_widths_do_not_leak_into_other_columns(app):
    session = Session()
    session.apply(
        replace(_sample_plan(), horizon=PlanningHorizon(date(2026, 1, 2), date(2026, 3, 3)))
    )
    page = TimelinePage(session)
    page.resize(1000, 500)
    page.show()
    try:
        for scale in ("month", "week", "day", "month", "day"):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            app.processEvents()
        assert {page.schedule.columnWidth(i) for i in range(page.schedule_model.columnCount())} == {
            34
        }
        page.scale_box.setCurrentIndex(page.scale_box.findData("month"))
        assert page.schedule_model.headerData(1, Qt.Orientation.Horizontal) == "Feb 2026"
        assert (
            page.schedule_model.headerData(
                2, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole
            )
            == "2026-03-01 to 2026-03-03"
        )
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("invalid", ["fortnight", 12])
def test_invalid_saved_scale_falls_back_to_day(app, settings, invalid):
    settings.setValue("timeline/scale", invalid)
    page = TimelinePage(Session(), settings)
    assert page.scale_box.currentData() == "day"
    assert page.schedule_model.scale == TimelineScale.DAY
    page.deleteLater()
    app.processEvents()
