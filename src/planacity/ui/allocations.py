"""Draft allocation editing; Save applies the complete candidate, Cancel discards it."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import Allocation, ProgramPlan
from planacity.planning.allocation_settings import (
    add_allocation,
    allocation_by_id,
    remove_allocation,
    update_allocation,
)
from planacity.planning.allocations import summarize_allocations
from planacity.planning.assignment_policy import assignment_policy_conflicts
from planacity.planning.assignment_resolution import (
    AssignmentConsolidationPreview,
    preview_assignment_consolidation,
)
from planacity.planning.findings import findings_for_work, planning_findings
from planacity.planning.work_items import resolve_container_effort
from planacity.ui.forms import validated_form
from planacity.ui.pages import label
from planacity.ui.planning_findings import FindingView
from planacity.ui.session import Session


def allocation_summary_text(plan: ProgramPlan, work_id: UUID) -> str:
    summary = next(
        w for w in summarize_allocations(plan, plan.allocations).work if w.work_item_id == work_id
    )
    if summary.is_container:
        estimate = f"Effective estimate: {summary.known_estimate_hours} h known"
        if summary.missing_estimate_count:
            estimate += f"; {summary.missing_estimate_count} leaf estimate(s) missing"
        else:
            estimate = f"Effective estimate: {summary.known_estimate_hours} h"
        reference = (
            f"Entered reference: {summary.entered_estimate_hours} h"
            if summary.entered_estimate_hours is not None
            else "Entered reference: not set"
        )
        allocated = (
            f"Allocated: {summary.allocated_hours} h total "
            f"({summary.direct_allocated_hours} h direct; "
            f"{summary.descendant_allocated_hours} h in descendants)"
        )
    else:
        estimate = (
            "Missing estimate"
            if summary.missing_estimate
            else f"Estimate: {summary.estimate_hours} h"
        )
        reference = ""
        allocated = f"Allocated: {summary.allocated_hours} h"
    remaining = (
        "Remaining: unknown"
        if summary.remaining_hours is None
        else f"Remaining: {summary.remaining_hours} h"
    )
    status = "No positive allocation." if summary.unassigned else ""
    if summary.mixed_level_effort:
        status = (
            "Mixed-level effort: direct container allocations and descendant allocations "
            "are both counted. Move the direct effort to a leaf to resolve it."
        )
    elif summary.has_direct_container_allocations:
        status = "Direct container allocations are counted but must be moved to leaf work."
    elif summary.remaining_hours is not None and summary.remaining_hours < 0:
        status = "Allocated hours exceed the estimate."
    return f"{estimate}\n{reference}\n{allocated}\n{remaining}\n{status}".strip()


def _signed_hours(value: Decimal) -> str:
    return f"+{value}" if value > 0 else str(value)


class AssignmentConsolidationDialog(QDialog):
    """Require an explicit survivor before presenting an atomic candidate."""

    def __init__(self, parent: QWidget, plan: ProgramPlan, work_id: UUID) -> None:
        super().__init__(parent)
        self.plan = plan
        self.work_id = work_id
        self.preview: AssignmentConsolidationPreview | None = None
        work = plan.work_item(work_id)
        self.setWindowTitle("Resolve multiple assignments")
        self.resize(780, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(
            label(
                f"{work.title}\nChoose the existing allocation that will keep its person and "
                "ID. Its hours will become the exact sum of every direct allocation."
            )
        )
        self.survivor = QComboBox()
        self.survivor.setAccessibleName("Surviving allocation")
        self.survivor.addItem("Choose the surviving allocation...", None)
        for allocation in plan.allocations:
            if allocation.work_item_id != work_id:
                continue
            person = plan.person(allocation.person_id)
            self.survivor.addItem(
                f"{person.name} - {allocation.hours} h - {allocation.id}", str(allocation.id)
            )
        layout.addWidget(self.survivor)
        self.details = QPlainTextEdit()
        self.details.setAccessibleName("Assignment consolidation preview")
        self.details.setReadOnly(True)
        self.details.setTabChangesFocus(True)
        layout.addWidget(self.details, 1)
        layout.addWidget(
            label(
                "Consolidation changes only current-plan allocations. Estimates, dates, "
                "dependencies, hierarchy, and imported baselines stay unchanged. Cancel "
                "preserves the complete draft."
            )
        )
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.confirm_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm_button.setText("&Consolidate")
        self.confirm_button.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.survivor.currentIndexChanged.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self) -> None:
        value = self.survivor.currentData()
        if value is None:
            self.preview = None
            self.details.setPlainText(
                "Select one existing allocation to calculate the exact candidate and its "
                "person-load effects."
            )
            self.confirm_button.setEnabled(False)
            return
        self.preview = preview_assignment_consolidation(self.plan, self.work_id, UUID(value))
        survivor = next(
            allocation
            for allocation in self.plan.allocations
            if allocation.id == self.preview.surviving_allocation_id
        )
        lines = [
            f"Surviving person: {self.plan.person(survivor.person_id).name}",
            f"Preserved allocation ID: {survivor.id}",
            f"Consolidated hours: {self.preview.total_hours} h",
            "",
            "Removed allocation IDs:",
            *(f"- {identifier}" for identifier in self.preview.removed_allocation_ids),
            "",
            "Whole-plan allocated hours:",
        ]
        for change in self.preview.person_loads:
            person = self.plan.person(change.person_id)
            lines.append(
                f"- {person.name}: {change.before_hours} h -> {change.after_hours} h "
                f"({_signed_hours(change.delta_hours)} h)"
            )
        lines.extend(("", "Relevant findings before:"))
        before_lines = [
            f"- {finding.title}: {finding.explanation}" for finding in self.preview.before_findings
        ]
        lines.extend(before_lines or ("- None",))
        lines.extend(("", "Relevant findings after:"))
        after_lines = [
            f"- {finding.title}: {finding.explanation}" for finding in self.preview.after_findings
        ]
        lines.extend(after_lines or ("- None",))
        self.details.setPlainText("\n".join(lines))
        self.details.moveCursor(QTextCursor.MoveOperation.Start)
        self.confirm_button.setEnabled(True)

    def accept(self) -> None:
        if self.preview is None:
            return
        super().accept()


class AllocationDialog(QDialog):
    def __init__(self, parent: QWidget, session: Session, work_id: UUID) -> None:
        super().__init__(parent)
        if session.document.plan is None:
            raise ValueError("Open a plan before editing allocations.")
        self.session = session
        self.original = self.candidate = session.document.plan
        self.work_id = work_id
        work = self.original.work_item(work_id)
        self.setWindowTitle("Work allocations")
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        guidance = (
            "Review direct and descendant effort; add new allocations to leaf work."
            if self.original.children(work_id)
            else "Assign this leaf to one roster member with explicit hours."
        )
        layout.addWidget(label(f"{work.title}\n{guidance}"))
        self.summary = label("")
        self.summary.setAccessibleName("Allocation totals")
        layout.addWidget(self.summary)
        self.findings = FindingView("Allocation planning findings")
        layout.addWidget(self.findings)
        self.table = QTreeView()
        self.table.setAccessibleName("Work allocations")
        self.table.setRootIsDecorated(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.model = QStandardItemModel(self.table)
        self.model.setHorizontalHeaderLabels(["Person", "Allocated hours"])
        self.table.setModel(self.model)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.add_button = QPushButton("&Add...")
        self.edit_button = QPushButton("&Edit...")
        self.remove_button = QPushButton("&Remove")
        self.consolidate_button = QPushButton("&Consolidate legacy...")
        self.resolve_button = QPushButton("&Move direct effort to leaf...")
        self.add_button.clicked.connect(lambda: self.edit(False))
        self.edit_button.clicked.connect(lambda: self.edit(True))
        self.remove_button.clicked.connect(self.remove)
        self.consolidate_button.clicked.connect(self.consolidate)
        self.resolve_button.clicked.connect(self.resolve)
        for button in (
            self.add_button,
            self.edit_button,
            self.remove_button,
            self.consolidate_button,
            self.resolve_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(
            label(
                "Enter explicit hours, regardless of the Plan estimate display unit. "
                "Container totals include descendant work once; direct legacy allocations "
                "remain visible until moved or removed. Legacy multiple assignments keep all "
                "hours and show a resolution finding; new leaves accept at most one allocation. "
                "The preview compares dated demand with the whole team's calendars, "
                "availability, reservations, and concurrent work. Save applies all changes. "
                "Cancel discards them."
            )
        )
        self.error = label("")
        self.error.setAccessibleName("Allocation validation message")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.table.selectionModel().currentChanged.connect(self.selection_changed)
        self.refresh()

    def selected(self) -> UUID | None:
        value = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        return UUID(value) if value else None

    def selection_changed(self) -> None:
        selected = self.selected() is not None
        self.edit_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def refresh(self, selected: UUID | None = None) -> None:
        self.model.removeRows(0, self.model.rowCount())
        for allocation in self.candidate.allocations:
            if allocation.work_item_id != self.work_id:
                continue
            row = [
                QStandardItem(self.candidate.person(allocation.person_id).name),
                QStandardItem(str(allocation.hours)),
            ]
            for cell in row:
                cell.setData(str(allocation.id), Qt.ItemDataRole.UserRole)
                cell.setEditable(False)
            self.model.appendRow(row)
            if allocation.id == selected:
                self.table.setCurrentIndex(row[0].index())
        self.table.setColumnWidth(0, 340)
        self.summary.setText(allocation_summary_text(self.candidate, self.work_id))
        calculated = planning_findings(self.candidate)
        self.findings.set_findings(findings_for_work(self.candidate, calculated, self.work_id))
        summary = next(
            item
            for item in summarize_allocations(self.candidate, self.candidate.allocations).work
            if item.work_item_id == self.work_id
        )
        self.add_button.setEnabled(bool(self.candidate.people) and not summary.is_container)
        self.consolidate_button.setEnabled(
            any(
                conflict.work_item_id == self.work_id
                for conflict in assignment_policy_conflicts(self.candidate)
            )
        )
        self.resolve_button.setEnabled(summary.has_direct_container_allocations)
        self.error.setText(
            "Add roster members in People first."
            if not self.candidate.people
            else (
                "Add new allocations to leaf work; this container total is derived."
                if summary.is_container
                else ""
            )
        )
        self.selection_changed()

    def current(self) -> None:
        if self.session.document.plan is not self.original:
            raise ValueError("The plan changed. Cancel and reopen Work allocations.")

    def edit(self, existing: bool) -> None:
        identifier = self.selected() if existing else None
        if existing and identifier is None:
            return
        original = allocation_by_id(self.candidate, identifier) if identifier else None
        people = QComboBox()
        people.setAccessibleName("Allocation person")
        for person in self.candidate.people:
            people.addItem(person.name, str(person.id))
        if original:
            people.setCurrentIndex(people.findData(str(original.person_id)))
        hours = QLineEdit(str(original.hours) if original else "")
        hours.setAccessibleName("Allocation hours")
        identifier_holder: list[UUID] = []

        def build() -> ProgramPlan:
            self.current()
            if not people.currentData():
                raise ValueError("Choose a person from the roster first.")
            try:
                value = Decimal(hours.text().strip())
            except InvalidOperation as error:
                raise ValueError("Enter explicit hours, such as 12.5. Zero is allowed.") from error
            allocation = Allocation(
                work_item_id=self.work_id,
                person_id=UUID(people.currentData()),
                hours=value,
                **({"id": original.id} if original else {}),
            )
            updated = (
                update_allocation(self.candidate, allocation)
                if original
                else add_allocation(self.candidate, allocation)
            )
            identifier_holder.append(allocation.id)
            return updated

        updated = validated_form(
            self,
            "Edit allocation" if existing else "Add allocation",
            [("&Person", people), ("&Hours", hours)],
            build,
        )
        if updated is not None:
            self.candidate = updated
            self.refresh(identifier_holder[-1])

    def remove(self) -> None:
        identifier = self.selected()
        if identifier is None:
            return
        try:
            self.current()
            self.candidate = remove_allocation(self.candidate, identifier)
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.refresh()

    def resolve(self) -> None:
        title = QLineEdit(f"{self.candidate.work_item(self.work_id).title} effort")

        def build() -> ProgramPlan:
            self.current()
            return resolve_container_effort(self.candidate, self.work_id, title.text())

        updated = validated_form(
            self,
            "Move direct effort to leaf",
            [("&New leaf title", title)],
            build,
        )
        if updated is not None:
            self.candidate = updated
            self.refresh()

    def consolidate(self) -> None:
        try:
            self.current()
        except ValueError as error:
            self.error.setText(str(error))
            return
        dialog = AssignmentConsolidationDialog(self, self.candidate, self.work_id)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.preview is None:
            return
        try:
            self.current()
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.candidate = dialog.preview.candidate
        self.refresh(dialog.preview.surviving_allocation_id)

    def save(self) -> None:
        try:
            self.current()
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.session.apply(self.candidate)
        self.accept()
