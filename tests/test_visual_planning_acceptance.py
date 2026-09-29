"""Walk the shipped fictional example through the complete Visual Planning loop."""

from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from planacity.persistence.project import restore_backup
from planacity.ui.theme import Theme


@pytest.mark.parametrize("theme", list(Theme))
def test_example_visual_planning_acceptance(app, window, tmp_path, theme):
    example = Path(__file__).resolve().parents[1] / "examples" / "aurora.planacity.json"
    original = restore_backup(example)
    window.session.apply(original)
    window.set_theme(theme, persist=False)
    window.resize(1440, 900)
    window.show_page(2)
    page = window.timeline_page
    try:
        for scale in ("day", "month", "week"):
            page.scale_box.setCurrentIndex(page.scale_box.findData(scale))
            app.processEvents()
            assert "9 scheduled | 2 partial | 1 unscheduled" in page.summary.text()
        for grouping in ("epic", "workgroup", "hierarchy"):
            page.grouping_box.setCurrentIndex(page.grouping_box.findData(grouping))
            assert {row.item_id for row in page.projection.rows} == {
                item.id for item in original.work_items
            }
        page.state_filter.setCurrentIndex(page.state_filter.findData("start_only"))
        assert [row.title for row in page.projection.rows] == ["Arrange fixture transport"]
        page.clear_filters.click()
        page.search.setText("procurement")
        assert "outside horizon" in page.label_model.index(0, 1).data()
        page.clear_filters.click()
        app.processEvents()
        assert len(page.schedule.dependency_paths()) == 3
        assert window.session.document.plan is original

        row_index = 2
        row = page.projection.rows[row_index]
        assert row.title == "Assemble test bench"
        view = page.schedule
        x = view.edge_x(row, "end")
        y = view.rowViewportPosition(row_index) + view.rowHeight(row_index) / 2
        start = QPoint(round(x), round(y))
        end = start + QPoint(54, 0)  # Three days at the weekly scale.
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        assert window.session.document.plan is original
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        changed = window.session.document.plan
        assert changed.work_item(row.item_id).end == date(2026, 10, 24)
        assert (
            changed.work_item(row.item_id).estimate_hours
            == original.work_item(row.item_id).estimate_hours
        )
        assert changed.relationships == original.relationships
        target = tmp_path / "visual-plan.planacity"
        window.session.document.save(target)
        window.session.document.open(target)
        window.session.changed.emit()
        assert window.session.document.plan == changed
        assert not window.session.document.dirty
        assert restore_backup(example) == original
    finally:
        window.session.document.saved_plan = window.session.document.plan
