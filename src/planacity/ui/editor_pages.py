"""Keyboard-friendly Plan and People workspaces with validated editing actions."""

from functools import partial
from uuid import UUID

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeView,
)

from planacity.domain import Person, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.availability_settings import person_availability
from planacity.planning.people import add_person, remove_person, rename_person
from planacity.planning.work_calendar import nominal_capacity
from planacity.planning.work_items import add_work_item, move_work_item, remove_work_item
from planacity.ui.availability import manage_availability
from planacity.ui.forms import ValidatedDelegate, validated_form
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.plan_model import PlanModel
from planacity.ui.reservations import reserve_capacity_dialog
from planacity.ui.session import Session
from planacity.ui.structure_dialogs import manage_structure
from planacity.ui.work_calendars import choose_person_calendar, manage_work_calendars


class PlanPage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__(
            "Plan", "Structure the work. Estimates are in hours; dates use YYYY-MM-DD."
        )
        self.session = session
        self.model = PlanModel(session)
        self.table = QTreeView()
        self.table.setObjectName("Plan work items")
        self.table.setAccessibleName("Plan work items")
        self.table.setModel(self.model)
        self.table.setItemDelegate(ValidatedDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setColumnWidth(0, 250)
        for column in (2, 3, 4):
            self.table.setColumnWidth(column, 130)
        self.table.setMinimumHeight(260)
        self.toolbar = QHBoxLayout()
        self.content.addLayout(self.toolbar)
        self.buttons: list[QPushButton] = []
        for kind in WorkItemType:
            button = QPushButton(f"Add {kind.value.title()}")
            button.clicked.connect(partial(self.add_item, kind))
            self.toolbar.addWidget(button)
            self.buttons.append(button)
        for title, callback in (("Move...", self.move_item), ("Delete...", self.delete_item)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            self.toolbar.addWidget(button)
            self.buttons.append(button)
        self.toolbar.addStretch()
        split = QSplitter()
        split.addWidget(self.table)
        detail = Panel("Selected work")
        self.detail = label("Create or open a plan from the File menu.")
        detail.content.addWidget(self.detail)
        for title, groups in (("WorkGroups...", True), ("Relationships...", False)):
            button = QPushButton(title)
            button.clicked.connect(partial(self.manage, groups))
            detail.content.addWidget(button)
            self.buttons.append(button)
        detail.content.addStretch()
        split.addWidget(detail)
        split.setSizes([780, 280])
        self.content.addWidget(split, 1)
        self.error = label("")
        self.error.setAccessibleName("Plan validation message")
        self.content.addWidget(self.error)
        self.model.error.connect(self.error.setText)
        self.table.selectionModel().currentChanged.connect(self.selection_changed)
        self.selected_id: UUID | None = None
        self.expanded_ids: list[UUID] = []
        self.model.modelAboutToBeReset.connect(self.remember_selection)
        self.model.modelReset.connect(self.restore_selection)
        session.changed.connect(self.refresh)
        self.refresh()

    def commit_editor(self) -> bool:
        editor = self.table.findChild(QLineEdit)
        if editor is None or not editor.isVisible():
            return True
        index = editor.property("planIndex")
        if not isinstance(index, QPersistentModelIndex) or not index.isValid():
            return True
        if not self.model.setData(index, editor.text()):
            editor.setFocus()
            return False
        self.table.itemDelegate().closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
        return True

    def manage(self, groups: bool) -> None:
        if self.commit_editor():
            manage_structure(self, self.session, groups=groups)

    def remember_selection(self) -> None:
        item = self.model.item(self.table.currentIndex())
        self.selected_id = item.id if item else None
        self.expanded_ids = (
            [
                i.id
                for i in self.model.plan.work_items
                if self.table.isExpanded(self.model.index_for_id(i.id))
            ]
            if self.model.plan
            else []
        )

    def restore_selection(self) -> None:
        for item_id in self.expanded_ids:
            self.table.setExpanded(self.model.index_for_id(item_id), True)
        self.table.setCurrentIndex(self.model.index_for_id(self.selected_id))

    def refresh(self) -> None:
        for button in self.buttons:
            button.setEnabled(self.session.document.plan is not None)
        self.selection_changed()

    def selection_changed(
        self, current: QModelIndex | None = None, previous: QModelIndex | None = None
    ) -> None:
        item = self.model.item(self.table.currentIndex())
        if item is None:
            self.detail.setText(
                "Select work to edit it. F2 edits a cell. Add Tasks under a selected Epic, "
                "or Subtasks under a selected Task."
            )
        else:
            self.detail.setText(
                f"{item.title}\n\n{item.kind.value.title()}\n\n"
                "Double-click a title, estimate, or date to edit. Use the calendar button or type "
                "a date as YYYY-MM-DD. Clear a value to leave it unset. "
                "Escape cancels an inline edit.\n\nAssignments and capacity are planned for v0.4."
            )

    def add_item(self, kind: WorkItemType) -> None:
        if not self.commit_editor():
            return
        plan = self.session.document.plan
        if plan is None:
            return
        selected = self.model.item(self.table.currentIndex())
        parent_id = None
        if kind == WorkItemType.TASK and selected and selected.kind == WorkItemType.EPIC:
            parent_id = selected.id
        if kind == WorkItemType.SUBTASK:
            if selected is None or selected.kind != WorkItemType.TASK:
                self.error.setText("Select a Task before adding a Subtask.")
                return
            parent_id = selected.id
        title = QLineEdit()
        item_id: list[UUID] = []

        def build() -> ProgramPlan:
            item = WorkItem(title=title.text(), kind=kind, parent_id=parent_id)
            updated = add_work_item(plan, item)
            item_id.append(item.id)
            return updated

        updated = validated_form(self, f"Add {kind.value.title()}", [("&Title", title)], build)
        if updated is not None:
            self.session.apply(updated)
            self.table.setExpanded(self.model.index_for_id(parent_id), True)
            self.table.setCurrentIndex(self.model.index_for_id(item_id[0]))
            self.error.clear()

    def move_item(self) -> None:
        if not self.commit_editor():
            return
        plan, item = self.session.document.plan, self.model.item(self.table.currentIndex())
        if plan is None or item is None:
            return
        parents = QComboBox()
        if item.kind != WorkItemType.SUBTASK:
            parents.addItem("Plan root", None)
        expected = WorkItemType.EPIC if item.kind == WorkItemType.TASK else WorkItemType.TASK
        if item.kind != WorkItemType.EPIC:
            for candidate in plan.work_items:
                if candidate.kind == expected:
                    parents.addItem(
                        f"{candidate.title} [{str(candidate.id)[:8]}]", str(candidate.id)
                    )
        current = parents.findData(str(item.parent_id) if item.parent_id else None)
        parents.setCurrentIndex(max(0, current))

        def build() -> ProgramPlan:
            value = parents.currentData()
            return move_work_item(plan, item.id, UUID(value) if value else None)

        updated = validated_form(self, "Move work", [("&New parent", parents)], build)
        if updated is not None:
            self.session.apply(updated)
            self.table.expand(self.model.index_for_id(updated.work_item(item.id).parent_id))
            self.table.setCurrentIndex(self.model.index_for_id(item.id))

    def delete_item(self) -> None:
        if not self.commit_editor():
            return
        plan, item = self.session.document.plan, self.model.item(self.table.currentIndex())
        if plan is None or item is None:
            return
        updated = remove_work_item(plan, item.id, delete_descendants=True, remove_references=True)
        count = len(plan.work_items) - len(updated.work_items)
        links = len(plan.relationships) - len(updated.relationships)
        memberships = sum(len(g.epic_ids) for g in plan.work_groups) - sum(
            len(g.epic_ids) for g in updated.work_groups
        )
        if (
            QMessageBox.question(
                self,
                "Delete work?",
                f"Delete '{item.title}' and its subtree ({count} work item(s))?\n"
                f"This also removes {links} relationship(s) and {memberships} group membership(s).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.session.apply(updated)


class PeoplePage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__(
            "People",
            "Calendar hours and availability before program events, reservations, and allocations.",
        )
        self.session = session
        self.horizon_notice = label("")
        self.content.addWidget(self.horizon_notice)
        self.table = QTreeView()
        self.table.setAccessibleName("People roster")
        self.table.setRootIsDecorated(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model = QStandardItemModel(0, 7, self.table)
        self.model.setHorizontalHeaderLabels(
            [
                "Person",
                "Work calendar",
                "Nominal hours",
                "Working days",
                "Unavailable hours",
                "Available hours",
                "Overlap periods",
            ]
        )
        self.table.setModel(self.model)
        self.content.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.buttons: list[QPushButton] = []
        for title, operation in (
            ("Add person...", "add"),
            ("Rename...", "rename"),
            ("Remove...", "remove"),
        ):
            button = QPushButton(title)
            button.clicked.connect(partial(self.edit, operation))
            buttons.addWidget(button)
            self.buttons.append(button)
        buttons.addStretch()
        self.content.addLayout(buttons)
        buttons = QHBoxLayout()
        self.calendar_button = QPushButton("Work calendars...")
        self.calendar_button.clicked.connect(lambda: manage_work_calendars(self, self.session))
        buttons.addWidget(self.calendar_button)
        self.buttons.append(self.calendar_button)
        self.assign_button = QPushButton("Assign calendar...")
        self.assign_button.clicked.connect(self.assign_calendar)
        buttons.addWidget(self.assign_button)
        self.availability_button = QPushButton("Availability...")
        self.availability_button.clicked.connect(self.edit_availability)
        buttons.addWidget(self.availability_button)
        self.reserve_button = QPushButton("Reserve capacity...")
        self.reserve_button.clicked.connect(lambda: reserve_capacity_dialog(self, self.session))
        buttons.addWidget(self.reserve_button)
        self.buttons.append(self.reserve_button)
        buttons.addStretch()
        self.content.addLayout(buttons)
        session.changed.connect(self.refresh)
        self.table.selectionModel().currentChanged.connect(self._selection_changed)
        self.refresh()

    def refresh(self) -> None:
        selected = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        self.model.removeRows(0, self.model.rowCount())
        plan = self.session.document.plan
        self.horizon_notice.setText(
            f"Planning horizon: {plan.horizon.start} to {plan.horizon.end}. "
            "Unknown means no calendar is assigned. "
            f"{len(plan.reservation_rules)} reservation rules; "
            "use Reserve capacity to review totals."
            if plan
            else "Open a plan to configure calendars."
        )
        for button in self.buttons:
            button.setEnabled(plan is not None)
        if plan:
            assigned = {
                value.person_id: plan.work_calendar(value.calendar_id)
                for value in plan.person_calendars
            }
            for person in plan.people:
                calendar = assigned.get(person.id)
                capacity = nominal_capacity(calendar, plan.horizon) if calendar else None
                available = person_availability(plan, person.id)
                row = [
                    QStandardItem(value)
                    for value in (
                        person.name,
                        calendar.name if calendar else "Not configured",
                        str(capacity.total_hours) if capacity else "Unknown",
                        str(capacity.working_days) if capacity else "Unknown",
                        str(available.unavailable_hours) if available else "Unknown",
                        str(available.available_hours) if available else "Unknown",
                        str(len(available.overlaps)) if available else "Unknown",
                    )
                ]
                for item in row:
                    item.setData(str(person.id), Qt.ItemDataRole.UserRole)
                    item.setEditable(False)
                self.model.appendRow(row)
                if str(person.id) == selected:
                    self.table.setCurrentIndex(row[0].index())
        self._selection_changed()
        for column in range(7):
            self.table.resizeColumnToContents(column)

    def _selection_changed(self) -> None:
        selected = bool(self.table.currentIndex().data(Qt.ItemDataRole.UserRole))
        self.assign_button.setEnabled(selected)
        self.availability_button.setEnabled(selected)

    def edit_availability(self) -> None:
        selected = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        if selected:
            manage_availability(self, self.session, UUID(selected))

    def assign_calendar(self) -> None:
        selected = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        if selected:
            choose_person_calendar(self, self.session, UUID(selected))

    def edit(self, operation: str) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        selected = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        if operation != "add" and not selected:
            return
        person = plan.person(UUID(selected)) if selected else None
        if operation == "remove" and person:
            entries = sum(e.person_id == person.id for e in plan.availability_events)
            rules = [rule.name for rule in plan.reservation_rules if person.id in rule.person_ids]
            reservation_notice = (
                "\nAlso remove them from these reservation rules: "
                + ", ".join(rules)
                + ". Rules with no remaining people will be deleted."
                if rules
                else ""
            )
            if (
                QMessageBox.question(
                    self,
                    "Remove person?",
                    f"Remove '{person.name}' from the roster and clear their calendar assignment "
                    f"and {entries} availability entries?" + reservation_notice,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                if self.session.document.plan is plan:
                    self.session.apply(
                        remove_person(
                            plan, person.id, remove_availability=True, remove_reservations=True
                        )
                    )
            return
        name = QLineEdit(person.name if person and operation == "rename" else "")

        def build() -> ProgramPlan:
            if operation == "rename" and person:
                return rename_person(plan, person.id, name.text())
            return add_person(plan, Person(name=name.text()))

        updated = validated_form(self, "Person", [("&Name", name)], build)
        if updated is not None:
            self.session.apply(updated)
