"""Exercise the read-only Timeline without a visible desktop."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
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
def test_timeline_bar_renders_with_active_appearance(
    app: QApplication, window: MainWindow, theme: Theme
) -> None:
    try:
        window.session.apply(_sample_plan())
        window.show_page(2)
        window.set_theme(theme, persist=False)
        app.processEvents()

        page = window.timeline_page
        bar_index = page.schedule_model.index(0, 1)
        bar_rect = page.schedule.visualRect(bar_index)
        assert bar_rect.isValid()
        image = page.schedule.viewport().grab().toImage()
        assert not image.isNull()
        assert image.pixelColor(bar_rect.center()).name() == QColor(COLORS[theme].accent).name()
    finally:
        window.session.document.saved_plan = window.session.document.plan
