"""Filtering preserves canonical data and safe editing of the visible hierarchy."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester, QSignalSpy, QTest
from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QLineEdit, QMessageBox
from test_editor_forms import drive_dialog

from planacity.domain import PlanningHorizon, ProgramPlan, WorkGroup, WorkItem, WorkItemType
from planacity.planning.plan_filters import filter_plan
from planacity.planning.timeline import TimelineDateState
from planacity.planning.timeline_view import TimelineFilters
from planacity.ui.theme import Theme


@pytest.fixture
def plan():
    epic = WorkItem(title="Platform", kind=WorkItemType.EPIC)
    task = WorkItem(title="Build", kind=WorkItemType.TASK, parent_id=epic.id)
    child = WorkItem(
        title="Check hardware",
        kind=WorkItemType.SUBTASK,
        parent_id=task.id,
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )
    hidden = WorkItem(title="Documentation", kind=WorkItemType.TASK, parent_id=epic.id)
    other = WorkItem(title="Check software", kind=WorkItemType.TASK)
    return ProgramPlan(
        name="Filter checks",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 12, 31)),
        work_items=(epic, task, child, hidden, other),
        work_groups=(WorkGroup(name="Alpha", epic_ids=(epic.id,)),),
    )


@pytest.fixture
def page(app, window, plan):
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    app.processEvents()
    yield window.plan_page
    window.session.document.saved_plan = window.session.document.plan


def test_combined_filters_inherit_groups_and_keep_ancestor_context(plan):
    filters = TimelineFilters(
        text=" CHECK ",
        kind=WorkItemType.SUBTASK,
        group_id=plan.work_groups[0].id,
        state=TimelineDateState.SCHEDULED,
    )
    result = filter_plan(plan, filters)
    assert result.matches == {plan.work_items[2].id}
    assert result.visible == {item.id for item in plan.work_items[:3]}
    assert result.total == 5
    assert filter_plan(plan, TimelineFilters()).matches == {i.id for i in plan.work_items}
    assert not filter_plan(plan, TimelineFilters(text="absent")).visible
    assert not filter_plan(None, filters).visible


def test_controls_context_and_clear_do_not_change_plan(app, page, plan):
    tester = QAbstractItemModelTester(
        page.model, QAbstractItemModelTester.FailureReportingMode.Warning
    )
    assert tester.model() is page.model
    page.search.setText("check")
    page.kind_filter.setCurrentIndex(page.kind_filter.findData("subtask"))
    page.group_filter.setCurrentIndex(page.group_filter.findData(str(plan.work_groups[0].id)))
    page.state_filter.setCurrentIndex(page.state_filter.findData("scheduled"))
    assert page.model.result.matches == {plan.work_items[2].id}
    assert "1 of 5" in page.filter_summary.text()
    assert "2 ancestors" in page.filter_summary.text()
    ancestor = page.model.index_for_id(plan.work_items[0].id)
    assert page.table.isExpanded(ancestor)
    assert not page.model.flags(ancestor) & Qt.ItemFlag.ItemIsEditable
    assert "Context only" in page.model.data(ancestor.siblingAtColumn(5))
    assert not page.model.setData(ancestor, "Accidental rename")
    assert page.session.document.plan is plan
    assert not page.session.document.dirty
    page.clear_filters_button.click()
    assert len(page.model.result.matches) == 5
    ancestor = page.model.index_for_id(plan.work_items[0].id)
    assert page.model.flags(ancestor) & Qt.ItemFlag.ItemIsEditable
    assert page.model.rowCount() == 2
    assert page.session.document.plan is plan
    assert not page.session.document.dirty


@pytest.mark.parametrize("theme", list(Theme))
def test_keyboard_edit_of_filtered_row_keeps_identity_and_clears_selection(
    app,
    window,
    page,
    plan,
    theme,
):
    window.set_theme(theme, persist=False)
    page.search.setText("Check software")
    index = page.model.index(0, 0)
    assert page.model.item(index).id == plan.work_items[4].id
    page.table.setCurrentIndex(index)
    page.table.setFocus()
    QTest.keyClick(page.table, Qt.Key.Key_F2)
    app.processEvents()
    editor = page.table.findChild(QLineEdit)
    assert editor is not None and editor.isVisible()
    editor.setText("Updated software")
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QTest.qWait(100)
    assert page.session.document.plan.work_items[:4] == plan.work_items[:4]
    assert page.session.document.plan.work_items[4].title == "Updated software"
    assert page.model.rowCount() == 0
    assert not page.table.currentIndex().isValid()
    page.clear_filters_button.click()
    assert page.model.index_for_id(plan.work_items[4].id).isValid()


def test_invalid_draft_blocks_filter_change_and_escape_cancels(app, page, plan):
    index = page.model.index_for_id(plan.work_items[0].id)
    page.table.setCurrentIndex(index)
    page.table.edit(index)
    app.processEvents()
    editor = page.table.findChild(QLineEdit)
    editor.setText(" ")
    page.search.setText("Check")
    app.processEvents()
    assert editor.isVisible()
    assert not page.search.text()
    assert page.model.filters == TimelineFilters()
    assert page.error.text()
    assert page.session.document.plan is plan
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    app.processEvents()
    page.search.setText("Check")
    assert len(page.model.result.matches) == 2
    assert not page.session.document.dirty


def test_date_edit_stops_matching_after_commit(app, page, plan):
    page.change_filters(TimelineFilters(state=TimelineDateState.SCHEDULED))
    index = page.model.index_for_id(plan.work_items[2].id)
    page.table.setCurrentIndex(index)
    assert page.model.setData(index.siblingAtColumn(4), "")
    app.processEvents()
    assert not page.model.result.matches
    assert not page.table.currentIndex().isValid()
    assert page.session.document.plan.work_items[2].start == plan.work_items[2].start
    assert page.session.document.plan.work_items[2].end is None


def test_hidden_selection_does_not_jump_to_another_match(app, page, plan):
    page.search.setText("Check")
    selected = page.model.index_for_id(plan.work_items[4].id)
    page.table.setCurrentIndex(selected)
    assert page.model.setData(selected, "Software complete")
    app.processEvents()
    assert page.model.result.matches == {plan.work_items[2].id}
    assert not page.table.currentIndex().isValid()
    page.table.setCurrentIndex(page.model.index_for_id(plan.work_items[2].id))
    page.clear_filters_button.click()
    assert page.model.item(page.table.currentIndex()).id == plan.work_items[2].id


def test_cell_edits_preserve_indexes_when_visible_rows_do_not_change(app, page, plan):
    index = page.model.index_for_id(plan.work_items[2].id).siblingAtColumn(4)
    layouts = QSignalSpy(page.model.layoutChanged)
    assert page.model.setData(index, "2026-10-03")
    app.processEvents()
    assert layouts.count() == 0
    assert page.model.data(index, Qt.ItemDataRole.EditRole) == "2026-10-03"
    assert page.model.item(index).id == plan.work_items[2].id


def test_delete_previews_hidden_descendants_and_cancel_is_safe(page, plan, monkeypatch):
    page.search.setText("Check hardware")
    page.table.setCurrentIndex(page.model.index_for_id(plan.work_items[0].id))
    prompts = []

    def confirm(*args):
        prompts.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", confirm)
    page.delete_item()
    assert "4 work item(s)" in prompts[0]
    assert "1 work item(s) hidden" in prompts[0]
    assert page.session.document.plan is plan
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    page.delete_item()
    assert page.session.document.plan.work_items == (plan.work_items[4],)
    assert not page.table.currentIndex().isValid()


def test_add_hidden_work_and_move_out_of_group_have_explicit_feedback(app, page, plan):
    page.change_filters(TimelineFilters(group_id=plan.work_groups[0].id))
    page.table.setCurrentIndex(page.model.index_for_id(plan.work_items[1].id))

    def move(dialog):
        dialog.findChild(QComboBox).setCurrentIndex(0)
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()

    drive_dialog(app, page.move_item, move)
    assert page.session.document.plan.work_item(plan.work_items[1].id).parent_id is None
    assert not page.table.currentIndex().isValid()
    assert "hidden" in page.error.text()

    def add(dialog):
        dialog.findChild(QLineEdit).setText("New standalone work")
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()

    drive_dialog(app, lambda: page.add_item(WorkItemType.TASK), add)
    assert len(page.session.document.plan.work_items) == 6
    assert "hidden" in page.error.text()
    assert not page.table.currentIndex().isValid()
    page.clear_filters_button.click()
    assert len(page.model.result.matches) == 6


def test_removed_group_and_new_document_reset_stale_filters(app, page, plan):
    page.change_filters(TimelineFilters(text="Check", group_id=plan.work_groups[0].id))
    page.session.apply(replace(plan, work_groups=()))
    app.processEvents()
    assert page.model.filters == TimelineFilters(text="Check")
    assert page.group_filter.currentText() == "All WorkGroups"
    assert len(page.model.result.matches) == 2
    page.session.document.new(replace(plan, id=uuid4()))
    page.session.changed.emit()
    app.processEvents()
    assert page.model.filters == TimelineFilters()
    assert page.search.text() == ""
    assert len(page.model.result.matches) == 5
