"""Critical-path Timeline presentation stays optional, global, and read-only."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QWidget

from planacity.domain import (
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.critical_path import CriticalPathStatus
from planacity.ui.session import Session
from planacity.ui.theme import Theme
from planacity.ui.timeline import TimelinePage
from planacity.ui.timeline_identity import bar_identity
from planacity.ui.timeline_links import CRITICAL_COLORS


def _critical_plan(*, tied: bool = False) -> tuple[ProgramPlan, tuple[WorkItem, ...]]:
    group = WorkGroup(name="Launch Systems")
    first = WorkItem(
        title="A - Prepare",
        kind=WorkItemType.TASK,
        primary_group_id=group.id,
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
    )
    longer = WorkItem(
        title="B - Main branch",
        kind=WorkItemType.TASK,
        primary_group_id=group.id,
        start=date(2026, 1, 3),
        end=date(2026, 1, 5),
    )
    shorter = WorkItem(
        title="C - Parallel branch",
        kind=WorkItemType.TASK,
        primary_group_id=group.id,
        start=date(2026, 1, 3),
        end=date(2026, 1, 5) if tied else date(2026, 1, 3),
    )
    finish = WorkItem(
        title="D - Finish",
        kind=WorkItemType.TASK,
        primary_group_id=group.id,
        start=date(2026, 1, 6),
        end=date(2026, 1, 7),
    )
    items = (first, longer, shorter, finish)
    relationships = (
        Relationship(source_id=first.id, target_id=longer.id, kind=RelationshipType.BLOCKS),
        Relationship(source_id=first.id, target_id=shorter.id, kind=RelationshipType.BLOCKS),
        Relationship(source_id=longer.id, target_id=finish.id, kind=RelationshipType.BLOCKS),
        Relationship(source_id=shorter.id, target_id=finish.id, kind=RelationshipType.BLOCKS),
    )
    return (
        ProgramPlan(
            name="Critical fork",
            horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 10)),
            work_items=items,
            work_groups=(group,),
            relationships=relationships,
        ),
        items,
    )


def test_toggle_presents_critical_bars_links_float_and_assumptions(app) -> None:
    plan, (first, longer, shorter, finish) = _critical_plan()
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1500, 900)
    page.show()
    try:
        app.processEvents()
        assert not page.critical_toggle.isChecked()
        assert not page.schedule.show_critical_path
        assert not page.critical_details.isVisible()

        page._select_row(2)
        page.critical_toggle.setFocus()
        QTest.keyClick(page.critical_toggle, Qt.Key.Key_Space)
        app.processEvents()

        analysis = page.critical_analysis
        assert analysis is not None and analysis.complete
        assert page.schedule.critical_node_ids == {first.id, longer.id, finish.id}
        assert page.schedule.critical_relationship_ids == {
            plan.relationships[0].id,
            plan.relationships[2].id,
        }
        assert len(page.schedule.ordinary_dependency_paths()) == 2
        assert len(page.schedule.critical_dependency_paths()) == 2
        details = page.critical_details.toPlainText()
        assert "0 critical activities hidden" in details
        assert "Selected leaf: C - Parallel branch" in details
        assert "total float 2 days | not critical" in details
        assert "Entered gaps, calendars, capacity, priority, and filters do not change" in details
        assert "Critical path: red dashed outline" in page.legend.accessibleDescription()
        entries = [
            page.legend.items_layout.itemAt(index).widget()
            for index in range(page.legend.items_layout.count() - 1)
        ]
        assert all(
            label.geometry().right() <= entry.rect().right()
            for entry in entries
            for label in entry.findChildren(QLabel)
        )
        assert all(
            before.geometry().right() < after.geometry().left()
            for before, after in zip(entries, entries[1:], strict=False)
        )
        visible_entries = page.legend.items.findChildren(
            QWidget,
            options=Qt.FindChildOption.FindDirectChildrenOnly,
        )
        assert [entry for entry in visible_entries if entry.isVisible()] == entries
        assert session.document.plan is plan
        assert not session.document.dirty

        page.dependency_toggle.setChecked(False)
        assert page.schedule.ordinary_dependency_paths() == ()
        assert len(page.schedule.dependency_paths()) == 2
        assert len(page.schedule.critical_dependency_paths()) == 2
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_filters_only_hide_presentation_and_report_hidden_critical_work(app) -> None:
    plan, (first, longer, shorter, finish) = _critical_plan()
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1500, 900)
    page.show()
    try:
        page.critical_toggle.setChecked(True)
        page.search.setText("Main branch")
        app.processEvents()

        analysis = page.critical_analysis
        assert analysis is not None
        assert analysis.critical_node_ids == (first.id, longer.id, finish.id)
        assert analysis.activity(shorter.id).total_float == 2
        assert page.schedule.critical_node_ids == {first.id, longer.id, finish.id}
        assert page.label_model.rowCount() == 1
        assert page.schedule.critical_dependency_paths() == ()
        assert "2 critical activities hidden" in page.critical_details.toPlainText()
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_tied_branches_are_all_presented_as_critical(app) -> None:
    plan, items = _critical_plan(tied=True)
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1500, 900)
    page.show()
    try:
        page.critical_toggle.setChecked(True)
        app.processEvents()

        assert page.schedule.critical_node_ids == {item.id for item in items}
        assert page.schedule.critical_relationship_ids == {
            relationship.id for relationship in plan.relationships
        }
        assert len(page.schedule.critical_dependency_paths()) == 4
        assert "All tied critical branches are shown" in page.critical_details.toPlainText()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_incomplete_analysis_clears_overlay_and_explains_diagnostic(app) -> None:
    plan, items = _critical_plan()
    plan = replace(plan, work_items=(*items[:2], replace(items[2], end=None), items[3]))
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1500, 900)
    page.show()
    try:
        page.critical_toggle.setChecked(True)
        app.processEvents()

        assert page.critical_analysis is not None
        assert page.critical_analysis.status == CriticalPathStatus.INCOMPLETE
        assert not page.schedule.show_critical_path
        assert page.schedule.critical_node_ids == frozenset()
        assert page.schedule.critical_relationship_ids == frozenset()
        assert page.schedule.critical_dependency_paths() == ()
        details = page.critical_details.toPlainText()
        assert "inputs are incomplete" in details
        assert "missing its end date" in details
        assert details.endswith("No overlay is shown.")
        assert "Critical path: red dashed outline" not in page.legend.accessibleDescription()
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("theme", list(Theme))
def test_critical_outline_preserves_bar_identity_in_both_themes(app, window, theme) -> None:
    plan, _ = _critical_plan()
    window.session.apply(plan)
    window.show_page(2)
    window.set_theme(theme, persist=False)
    window.resize(1500, 900)
    window.show()
    page = window.timeline_page
    try:
        page.critical_toggle.setChecked(True)
        page.labels.clearSelection()
        page.schedule.clearSelection()
        app.processEvents()

        axis = page.schedule_model.axis
        projection = page.schedule_model.projection
        assert axis is not None and projection is not None
        column = axis.column_for_day(0)
        rect = page.schedule.visualRect(page.schedule_model.index(0, column))
        image = page.schedule.viewport().grab().toImage()
        assert rect.isValid() and not image.isNull()
        identity = bar_identity(projection.rows[0], projection.groups)
        center = image.pixelColor(rect.center()).name()
        assert center == QColor(identity.color(theme)).name()
        critical = QColor(CRITICAL_COLORS[theme.value]).name()
        colors = {
            image.pixelColor(x, y).name()
            for x in range(rect.left(), rect.right() + 1)
            for y in range(rect.top(), rect.bottom() + 1)
        }
        assert critical in colors
    finally:
        window.session.document.saved_plan = window.session.document.plan


def test_team_mode_hides_details_without_changing_overlay_choice(app) -> None:
    plan, _ = _critical_plan()
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.show()
    try:
        page.critical_toggle.setChecked(True)
        assert page.critical_details.isVisible()
        page.mode_box.setCurrentIndex(page.mode_box.findData("team"))
        assert page.critical_toggle.isChecked()
        assert not page.critical_details.isVisible()
        page.mode_box.setCurrentIndex(page.mode_box.findData("plan"))
        assert page.critical_details.isVisible()
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
