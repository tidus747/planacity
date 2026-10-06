"""Transactional Plan inspector behavior across editing and selection changes."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QMessageBox
from test_allocation_settings import allocated_plan

from planacity.domain import Relationship, RelationshipType, WorkGroup
from planacity.domain.models import ImportedWork, ImportSnapshot
from planacity.ui.theme import Theme


def inspector_plan():
    plan = allocated_plan()
    epic, task, other = plan.work_items
    group = WorkGroup(name="Alpha", epic_ids=(epic.id,))
    link = Relationship(source_id=other.id, target_id=task.id, kind=RelationshipType.DEPENDS_ON)
    source = ImportSnapshot(
        name="source.csv",
        headers=("Key", "Summary"),
        rows=(("CTX-1", epic.title), ("CTX-2", task.title)),
        records=(
            ImportedWork(item=epic, external_reference="CTX-1", status="In Progress"),
            ImportedWork(item=task, external_reference="CTX-2", status="Open"),
        ),
    )
    return replace(plan, work_groups=(group,), relationships=(link,), imports=(source,))


@pytest.fixture
def loaded(app, window):
    plan = inspector_plan()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    page = window.plan_page
    page.table.setCurrentIndex(page.model.index_for_id(plan.work_items[1].id))
    app.processEvents()
    yield window, page, plan
    page.inspector.discard()
    window.session.document.saved_plan = window.session.document.plan


@pytest.mark.parametrize("theme", list(Theme))
def test_inspector_shows_context_and_applies_one_complete_draft(app, loaded, theme):
    window, page, plan = loaded
    window.set_theme(theme, persist=False)
    inspector = page.inspector
    task = plan.work_items[1]
    changed = QSignalSpy(window.session.changed)

    assert inspector.item_id == task.id
    assert "Alex [" in inspector.allocations.text()
    assert "60 h" in inspector.allocations.text()
    assert "depends_on" in inspector.dependencies.text()
    assert "CTX-2" in inspector.imported.text()
    assert "read-only" in inspector.imported.text()

    inspector.title.setText("Integrated build")
    inspector.description.setPlainText("First line\nSecond line")
    inspector.labels.setPlainText("hardware\nCustomer-A")
    inspector.primary_group.setCurrentIndex(1)
    inspector.estimate.setText("125.5")
    inspector.start.setText("2026-10-05")
    inspector.end.setText("2026-10-30")
    assert inspector.dirty and inspector.apply_button.isEnabled()
    QTest.mouseClick(inspector.apply_button, Qt.MouseButton.LeftButton)

    updated = window.session.document.plan
    item = updated.work_item(task.id)
    assert changed.count() == 1
    assert item.title == "Integrated build"
    assert item.description == "First line\nSecond line"
    assert item.labels == ("hardware", "Customer-A")
    assert item.primary_group_id == plan.work_groups[0].id
    assert item.estimate_hours == Decimal("125.5")
    assert (item.start, item.end) == (date(2026, 10, 5), date(2026, 10, 30))
    assert updated.imports == plan.imports
    assert not inspector.dirty
    assert page.model.item(page.table.currentIndex()).id == task.id


def test_noop_apply_does_not_dirty_or_emit_a_change(app, loaded):
    window, page, _ = loaded
    changed = QSignalSpy(window.session.changed)

    assert not page.inspector.dirty
    assert page.inspector.apply()

    assert changed.count() == 0
    assert not window.session.document.dirty


def test_invalid_complete_draft_changes_nothing_and_stays_selected(app, loaded, monkeypatch):
    window, page, plan = loaded
    inspector = page.inspector
    task, other = plan.work_items[1:]
    inspector.labels.setPlainText("firmware\nFirmware")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Save,
    )

    page.table.setCurrentIndex(page.model.index_for_id(other.id))
    app.processEvents()

    assert window.session.document.plan == plan
    assert inspector.item_id == task.id
    assert inspector.dirty
    assert "unique" in inspector.error.text()
    assert page.model.item(page.table.currentIndex()).id == task.id


@pytest.mark.parametrize(
    ("choice", "saved"),
    [
        (QMessageBox.StandardButton.Save, True),
        (QMessageBox.StandardButton.Discard, False),
    ],
)
def test_selection_change_resolves_valid_draft(app, loaded, monkeypatch, choice, saved):
    window, page, plan = loaded
    task, other = plan.work_items[1:]
    page.inspector.description.setPlainText("Draft description")
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: choice)

    page.table.setCurrentIndex(page.model.index_for_id(other.id))
    app.processEvents()

    assert page.inspector.item_id == other.id
    assert not page.inspector.dirty
    assert window.session.document.plan.work_item(task.id).description == (
        "Draft description" if saved else ""
    )


def test_cancelled_selection_and_filter_changes_keep_the_draft(app, loaded, monkeypatch):
    window, page, plan = loaded
    task, other = plan.work_items[1:]
    page.inspector.description.setPlainText("Keep this draft")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )

    page.table.setCurrentIndex(page.model.index_for_id(other.id))
    app.processEvents()
    assert page.model.item(page.table.currentIndex()).id == task.id
    assert page.inspector.description.toPlainText() == "Keep this draft"

    page.search.setText("Follow-up")
    app.processEvents()
    assert page.search.text() == ""
    assert page.inspector.item_id == task.id
    assert window.session.document.plan == plan


def test_container_effort_and_filter_context_are_read_only(app, window):
    plan = inspector_plan()
    window.session.document.new(plan)
    window.session.document.saved_plan = plan
    window.session.changed.emit()
    window.show_page(1)
    page = window.plan_page
    epic = plan.work_items[0]
    page.search.setText("Integration")
    page.table.setCurrentIndex(page.model.index_for_id(epic.id))
    app.processEvents()

    assert page.inspector.item_id == epic.id
    assert page.inspector.title.isReadOnly()
    assert page.inspector.estimate.isReadOnly()
    assert "derived" in page.inspector.estimate.text()
    assert "Ancestor context is read-only" in page.inspector.error.text()
    assert not page.inspector.apply_button.isEnabled()
    window.session.document.saved_plan = window.session.document.plan


def test_page_navigation_prompts_for_inspector_draft(app, loaded, monkeypatch):
    window, page, _ = loaded
    page.inspector.description.setPlainText("Stay on Plan")
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Cancel,
    )

    window.show_page(2)
    app.processEvents()

    assert window.pages.currentIndex() == 1
    assert page.inspector.dirty
