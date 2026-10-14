"""Timeline dependency graph interaction remains read-only and filter-aware."""

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_timeline_dependencies import dependency_plan

from planacity.ui.session import Session
from planacity.ui.timeline import TimelinePage


def test_graph_card_keyboard_navigation_reveals_filtered_work_and_recenters(app):
    plan = dependency_plan()
    first, second = plan.work_items
    first = replace(first, end=None)
    plan = replace(plan, work_items=(first, second))
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.resize(1440, 1000)
    page.show()
    try:
        page.dependency_graph_toggle.setChecked(True)
        page._select_row(1)
        page.search.setText("Verify")
        app.processEvents()
        assert page.label_model.rowCount() == 1
        predecessor = page.dependency_graph.card_buttons[first.id][0]
        assert "hidden by filters" in predecessor.text()
        assert "Warning:" in predecessor.text()

        predecessor.setFocus()
        QTest.keyClick(predecessor, Qt.Key.Key_Space)
        app.processEvents()

        assert page.search.text() == ""
        assert page.label_model.rowCount() == 2
        assert page._selected_id() == first.id
        assert page.schedule.currentIndex().column() == 1
        assert not session.document.dirty
        assert second.id in page.dependency_graph.card_buttons
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_graph_toggle_and_team_mode_visibility_do_not_change_plan(app):
    plan = dependency_plan()
    session = Session()
    session.apply(plan)
    session.document.saved_plan = plan
    page = TimelinePage(session)
    page.show()
    try:
        page._select_row(0)
        assert not page.dependency_graph.isVisible()
        page.dependency_graph_toggle.setChecked(True)
        assert page.dependency_graph.isVisible()
        page.mode_box.setCurrentIndex(page.mode_box.findData("team"))
        assert not page.dependency_graph.isVisible()
        page.mode_box.setCurrentIndex(page.mode_box.findData("plan"))
        assert page.dependency_graph.isVisible()
        assert session.document.plan is plan
        assert not session.document.dirty
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()
