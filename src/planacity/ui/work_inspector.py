"""Transactional, keyboard-friendly editing for one selected WorkItem."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import ProgramPlan, WorkItem
from planacity.planning.allocations import summarize_allocations
from planacity.planning.estimate_units import estimate_text, parse_estimate
from planacity.planning.work_context import resolve_topic, update_work_details
from planacity.ui.allocations import allocation_summary_text
from planacity.ui.forms import CalendarLineEdit
from planacity.ui.pages import label
from planacity.ui.session import Session


def _date_text(value: date | None) -> str:
    return "" if value is None else value.isoformat()


def _parse_date(text: str) -> date | None:
    value = text.strip()
    if not value:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Enter dates as YYYY-MM-DD.") from error
    if parsed.isoformat() != value:
        raise ValueError("Enter dates as YYYY-MM-DD.")
    return parsed


class WorkInspector(QWidget):
    """Edit one complete draft and expose related planning context."""

    applied = Signal(object)
    dirty_changed = Signal(bool)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.item_id: UUID | None = None
        self.original_item: WorkItem | None = None
        self.editable = False
        self.dirty = False
        self._loading = False
        self._loaded_values: tuple[str, ...] = ()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.summary = label("Create or open a plan from the File menu.")
        self.summary.setAccessibleName("Selected work summary")
        layout.addWidget(self.summary)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title = QLineEdit()
        self.title.setObjectName("workInspectorTitle")
        self.title.setAccessibleName("Work title")
        self.description = QPlainTextEdit()
        self.description.setObjectName("workInspectorDescription")
        self.description.setAccessibleName("Work description")
        self.description.setPlaceholderText("Plain-text planning context")
        self.description.setMaximumHeight(88)
        self.labels = QPlainTextEdit()
        self.labels.setObjectName("workInspectorLabels")
        self.labels.setAccessibleName("Work labels")
        self.labels.setPlaceholderText("One label per line")
        self.labels.setMaximumHeight(68)
        self.primary_group = QComboBox()
        self.primary_group.setObjectName("workInspectorPrimaryGroup")
        self.primary_group.setAccessibleName("Primary reporting topic")
        self.topic = label("")
        self.topic.setAccessibleName("Resolved reporting topic")
        self.estimate = QLineEdit()
        self.estimate.setObjectName("workInspectorEstimate")
        self.estimate.setAccessibleName("Work estimate")
        self.start = CalendarLineEdit()
        self.start.setObjectName("workInspectorStart")
        self.start.setAccessibleName("Work start date")
        self.start.setPlaceholderText("YYYY-MM-DD")
        self.end = CalendarLineEdit()
        self.end.setObjectName("workInspectorEnd")
        self.end.setAccessibleName("Work end date")
        self.end.setPlaceholderText("YYYY-MM-DD")
        for title, widget in (
            ("&Title", self.title),
            ("&Description", self.description),
            ("&Labels", self.labels),
            ("Primary &topic", self.primary_group),
            ("Topic status", self.topic),
            ("&Estimate", self.estimate),
            ("&Start", self.start),
            ("&End", self.end),
        ):
            form.addRow(title, widget)
        layout.addLayout(form)

        self.error = label("")
        self.error.setAccessibleName("Work inspector validation message")
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("&Apply")
        self.apply_button.setAccessibleName("Apply work inspector changes")
        self.cancel_button = QPushButton("&Cancel")
        self.cancel_button.setAccessibleName("Cancel work inspector changes")
        actions.addWidget(self.apply_button)
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)

        self.allocations = label("")
        self.allocations.setAccessibleName("Allocated people")
        self.dependencies = label("")
        self.dependencies.setAccessibleName("Work dependencies")
        self.imported = label("")
        self.imported.setAccessibleName("Imported work reference")
        for widget in (self.allocations, self.dependencies, self.imported):
            widget.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            layout.addWidget(widget)

        for line_editor in (self.title, self.estimate, self.start, self.end):
            line_editor.textChanged.connect(self._update_dirty)
        for text_editor in (self.description, self.labels):
            text_editor.textChanged.connect(self._update_dirty)
        self.primary_group.currentIndexChanged.connect(self._update_dirty)
        self.apply_button.clicked.connect(self.apply)
        self.cancel_button.clicked.connect(self.discard)
        self.clear()

    def _controls(self) -> tuple[QWidget, ...]:
        return (
            self.title,
            self.description,
            self.labels,
            self.primary_group,
            self.estimate,
            self.start,
            self.end,
        )

    def _values(self) -> tuple[str, ...]:
        selected = self.primary_group.currentData()
        return (
            self.title.text(),
            self.description.toPlainText(),
            self.labels.toPlainText(),
            "" if selected is None else str(selected),
            self.estimate.text(),
            self.start.text(),
            self.end.text(),
        )

    def _set_dirty(self, dirty: bool) -> None:
        if dirty != self.dirty:
            self.dirty = dirty
            self.dirty_changed.emit(dirty)
        self.apply_button.setEnabled(self.editable and dirty)
        self.cancel_button.setEnabled(self.editable and dirty)

    def _update_dirty(self, *args: object) -> None:
        if not self._loading:
            self.error.clear()
            self._set_dirty(self.editable and self._values() != self._loaded_values)

    def clear(self) -> None:
        self._loading = True
        self.item_id = None
        self.original_item = None
        self.editable = False
        for control in self._controls():
            control.setEnabled(False)
        self.title.clear()
        self.description.clear()
        self.labels.clear()
        self.primary_group.clear()
        self.estimate.clear()
        self.start.clear()
        self.end.clear()
        self.topic.clear()
        self.allocations.clear()
        self.dependencies.clear()
        self.imported.clear()
        self.error.clear()
        self.summary.setText("Create or open a plan from the File menu.")
        self._loaded_values = self._values()
        self._loading = False
        self._set_dirty(False)

    def load(self, plan: ProgramPlan, item_id: UUID, *, editable: bool) -> None:
        item = plan.work_item(item_id)
        effort = next(
            summary
            for summary in summarize_allocations(plan, plan.allocations).work
            if summary.work_item_id == item_id
        )
        self._loading = True
        self.item_id = item_id
        self.original_item = item
        self.editable = editable
        self.title.setText(item.title)
        self.description.setPlainText(item.description)
        self.labels.setPlainText("\n".join(item.labels))
        self.primary_group.clear()
        self.primary_group.addItem("Inherit or leave ungrouped", None)
        for group in plan.work_groups:
            self.primary_group.addItem(group.name, str(group.id))
        selected = self.primary_group.findData(
            str(item.primary_group_id) if item.primary_group_id is not None else None
        )
        self.primary_group.setCurrentIndex(max(0, selected))
        resolution = resolve_topic(plan, item_id)
        if resolution.group_id is not None:
            resolved = plan.work_group(resolution.group_id).name
            source = "explicit or inherited" if item.primary_group_id is None else "explicit"
            self.topic.setText(f"Resolved: {resolved} ({source})")
        elif resolution.candidate_group_ids:
            self.topic.setText("Ambiguous: choose one primary topic for additive reporting.")
        else:
            self.topic.setText("Ungrouped: no reporting topic is resolved.")
        if effort.is_container:
            derived = estimate_text(plan, effort.known_estimate_hours)
            missing = (
                f"; {effort.missing_estimate_count} leaf estimate(s) missing"
                if effort.missing_estimate_count
                else ""
            )
            entered = (
                f" Entered reference: {item.estimate_hours} h."
                if item.estimate_hours is not None
                else " No entered reference estimate."
            )
            self.estimate.setText(f"{derived} derived{missing}.{entered}")
        else:
            self.estimate.setText(estimate_text(plan, item.estimate_hours, editing=True))
        self.start.setText(_date_text(item.start))
        self.end.setText(_date_text(item.end))
        self.summary.setText(
            f"{item.kind.value.title()} [{str(item.id)[:8]}]\n"
            + allocation_summary_text(plan, item_id)
        )
        self.allocations.setText(self._allocation_text(plan, item_id))
        self.dependencies.setText(self._dependency_text(plan, item_id))
        self.imported.setText(self._imported_text(plan, item_id))
        context_only = not editable
        self.title.setReadOnly(context_only)
        self.description.setReadOnly(context_only)
        self.labels.setReadOnly(context_only)
        self.primary_group.setEnabled(editable)
        self.estimate.setReadOnly(context_only or effort.is_container)
        self.start.setReadOnly(context_only)
        self.end.setReadOnly(context_only)
        for control in (
            self.title,
            self.description,
            self.labels,
            self.estimate,
            self.start,
            self.end,
        ):
            control.setEnabled(True)
        self.error.setText(
            "Ancestor context is read-only. Clear or change filters to edit this work."
            if context_only
            else ""
        )
        self._loaded_values = self._values()
        self._loading = False
        self._set_dirty(False)

    def candidate(self) -> ProgramPlan:
        plan = self.session.document.plan
        if plan is None or self.item_id is None or self.original_item is None:
            raise ValueError("Select an existing work item first.")
        if plan.work_item(self.item_id) != self.original_item:
            raise ValueError(
                "This work changed after the inspector draft was opened. "
                "Cancel the draft and review the latest values."
            )
        if not self.editable:
            raise ValueError("Clear or change filters before editing ancestor context.")
        item = plan.work_item(self.item_id)
        labels = tuple(
            value for line in self.labels.toPlainText().splitlines() if (value := line.strip())
        )
        selected = self.primary_group.currentData()
        estimate = (
            item.estimate_hours
            if plan.children(item.id)
            else parse_estimate(plan, self.estimate.text())
        )
        return update_work_details(
            plan,
            item.id,
            title=self.title.text(),
            description=self.description.toPlainText(),
            labels=labels,
            primary_group_id=UUID(selected) if selected else None,
            estimate_hours=estimate,
            start=_parse_date(self.start.text()),
            end=_parse_date(self.end.text()),
        )

    def apply(self) -> bool:
        if not self.dirty:
            return True
        try:
            candidate = self.candidate()
        except ValueError as problem:
            self.error.setText(str(problem))
            return False
        item_id = self.item_id
        self._set_dirty(False)
        if candidate != self.session.document.plan:
            self.session.apply(candidate)
        elif item_id is not None:
            self.load(candidate, item_id, editable=self.editable)
        if item_id is not None:
            self.applied.emit(item_id)
        return True

    def discard(self) -> None:
        plan = self.session.document.plan
        if plan is None or self.item_id is None:
            self.clear()
            return
        try:
            plan.work_item(self.item_id)
        except ValueError:
            self.clear()
            return
        self.load(plan, self.item_id, editable=self.editable)

    @staticmethod
    def _descendant_ids(plan: ProgramPlan, item_id: UUID) -> set[UUID]:
        result = {item_id}
        pending = [item_id]
        while pending:
            current = pending.pop()
            children = plan.children(current)
            result.update(child.id for child in children)
            pending.extend(child.id for child in children)
        return result

    def _allocation_text(self, plan: ProgramPlan, item_id: UUID) -> str:
        work_ids = self._descendant_ids(plan, item_id)
        totals: dict[UUID, Decimal] = {}
        for allocation in plan.allocations:
            if allocation.work_item_id in work_ids:
                totals[allocation.person_id] = (
                    totals.get(allocation.person_id, Decimal(0)) + allocation.hours
                )
        if not totals:
            return "Allocated people: none."
        lines = ["Allocated people:"]
        for person in plan.people:
            if person.id in totals:
                lines.append(f"- {person.name} [{str(person.id)[:8]}]: {totals[person.id]} h")
        return "\n".join(lines)

    @staticmethod
    def _dependency_text(plan: ProgramPlan, item_id: UUID) -> str:
        links = tuple(
            link for link in plan.relationships if item_id in (link.source_id, link.target_id)
        )
        if not links:
            return "Dependencies: none."
        lines = ["Dependencies:"]
        for link in links:
            other_id = link.target_id if link.source_id == item_id else link.source_id
            other = plan.work_item(other_id)
            direction = "outgoing" if link.source_id == item_id else "incoming"
            lines.append(f"- {link.kind.value} ({direction}): {other.title} [{str(other.id)[:8]}]")
        return "\n".join(lines)

    @staticmethod
    def _imported_text(plan: ProgramPlan, item_id: UUID) -> str:
        record = next(
            (
                record
                for source in plan.imports
                for record in source.records
                if record.item.id == item_id
            ),
            None,
        )
        if record is None:
            return "Imported reference: none (local work)."
        baseline = record.item
        estimate = "Not set" if baseline.estimate_hours is None else f"{baseline.estimate_hours} h"
        return (
            "Imported reference (read-only):\n"
            f"- {record.external_reference}; status: {record.status or 'Not set'}\n"
            f"- Title: {baseline.title}\n"
            f"- Estimate: {estimate}; dates: {_date_text(baseline.start)} to "
            f"{_date_text(baseline.end)}"
        )
