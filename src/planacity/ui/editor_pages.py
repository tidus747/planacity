"""Keyboard-friendly Plan and People workspaces with validated editing actions."""

from datetime import date
from fractions import Fraction
from functools import partial
from uuid import UUID

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
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

from planacity.domain import (
    Person,
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
    WorkPriority,
)
from planacity.planning.availability import availability_capacity
from planacity.planning.capacity_breakdown import (
    CapacityBreakdown,
    CapacityBucket,
    CapacityBucketScale,
    CapacityLoadState,
    calculate_capacity_breakdown,
    day_period,
    week_period,
)
from planacity.planning.people import add_person, remove_person, rename_person
from planacity.planning.people_groups import (
    PeopleGroupProjection,
    PersonTopic,
    calculate_people_groups,
)
from planacity.planning.timeline import TimelineDateState
from planacity.planning.timeline_view import TimelineFilters
from planacity.planning.work_calendar import nominal_capacity
from planacity.planning.work_items import add_work_item, move_work_item, remove_work_item
from planacity.ui.allocations import AllocationDialog
from planacity.ui.availability import manage_availability
from planacity.ui.forms import (
    CalendarLineEdit,
    PriorityDelegate,
    ValidatedDelegate,
    validated_form,
)
from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.plan_filter_model import PlanFilterModel
from planacity.ui.plan_model import PlanModel
from planacity.ui.planning_findings import FindingView
from planacity.ui.priority import PRIORITY_ORDER, priority_icon, priority_label
from planacity.ui.reservations import hours_text, reserve_capacity_dialog
from planacity.ui.session import Session
from planacity.ui.structure_dialogs import manage_structure
from planacity.ui.work_calendars import choose_person_calendar, manage_work_calendars
from planacity.ui.work_inspector import WorkInspector


class PlanPage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__(
            "Plan", "Structure the work. Choose estimate units from Planning; dates use YYYY-MM-DD."
        )
        self.session = session
        self.source_model = PlanModel(session)
        self.model = PlanFilterModel(self.source_model)
        self.table = QTreeView()
        self.table.setObjectName("Plan work items")
        self.table.setAccessibleName("Plan work items")
        self.table.setModel(self.model)
        self.table.setItemDelegate(ValidatedDelegate(self.table))
        self.table.setItemDelegateForColumn(PlanModel.PRIORITY_COLUMN, PriorityDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.table.setColumnWidth(0, 250)
        for column in (
            PlanModel.PRIORITY_COLUMN,
            PlanModel.ESTIMATE_COLUMN,
            PlanModel.START_COLUMN,
            PlanModel.END_COLUMN,
        ):
            self.table.setColumnWidth(column, 130)
        self.table.setMinimumHeight(260)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search work titles...")
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All types", "")
        for kind in WorkItemType:
            self.kind_filter.addItem(kind.value.title(), kind.value)
        self.group_filter = QComboBox()
        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All priorities", "*")
        self.priority_filter.addItem(priority_icon(None), "Unset", "")
        for priority in PRIORITY_ORDER:
            self.priority_filter.addItem(
                priority_icon(priority), priority_label(priority), priority.value
            )
        self.state_filter = QComboBox()
        self.state_filter.addItem("All schedules", "")
        for state in TimelineDateState:
            self.state_filter.addItem(state.value.replace("_", " ").title(), state.value)
        self.clear_filters_button = QPushButton("Clear filters")
        self.priority_sort = QComboBox()
        self.priority_sort.addItem("Plan order", False)
        self.priority_sort.addItem("Priority: Highest first", True)
        for widget, name in (
            (self.search, "Search titles"),
            (self.kind_filter, "Work type"),
            (self.group_filter, "WorkGroup"),
            (self.priority_filter, "Priority"),
            (self.state_filter, "Schedule state"),
            (self.priority_sort, "Sort work"),
        ):
            widget.setAccessibleName(name)
            widget.setToolTip(name)
            filters.addWidget(widget)
        filters.addWidget(self.clear_filters_button)
        self.content.addLayout(filters)
        self.filter_summary = label("")
        self.filter_summary.setAccessibleName("Plan filter summary")
        self.content.addWidget(self.filter_summary)
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
        self.inspector = WorkInspector(session)
        self.detail = self.inspector.summary
        detail.content.addWidget(self.inspector)
        self.finding_view = FindingView("Selected work planning findings")
        detail.content.addWidget(self.finding_view)
        self.allocation_button = QPushButton("Work allocations...")
        self.allocation_button.clicked.connect(self.edit_allocations)
        detail.content.addWidget(self.allocation_button)
        for title, groups in (("WorkGroups...", True), ("Relationships...", False)):
            button = QPushButton(title)
            button.clicked.connect(partial(self.manage, groups))
            detail.content.addWidget(button)
            self.buttons.append(button)
        detail.content.addStretch()
        split.addWidget(detail)
        split.setSizes([700, 430])
        self.content.addWidget(split, 1)
        self.error = label("")
        self.error.setAccessibleName("Plan validation message")
        self.content.addWidget(self.error)
        self.model.error.connect(self.error.setText)
        self.table.selectionModel().currentChanged.connect(self.selection_changed)
        self.table.itemDelegate().closeEditor.connect(lambda *args: self.model.refresh_filters())
        self.selected_id: UUID | None = None
        self.expanded_ids: list[UUID] = []
        self._selection_guard = False
        self.inspector.applied.connect(self.report_hidden)
        self.model.modelAboutToBeReset.connect(self.remember_selection)
        self.model.modelReset.connect(self.restore_selection)
        self.model.filters_about_to_change.connect(self.remember_selection)
        self.model.filters_changed.connect(self.filters_changed)
        self.search.textChanged.connect(self.apply_filters)
        for combo in (
            self.kind_filter,
            self.group_filter,
            self.priority_filter,
            self.state_filter,
        ):
            combo.currentIndexChanged.connect(self.apply_filters)
        self.priority_sort.currentIndexChanged.connect(self.change_priority_sort)
        self.clear_filters_button.clicked.connect(lambda: self.change_filters(TimelineFilters()))
        session.changed.connect(self.refresh)
        self.refresh()

    def apply_filters(self) -> None:
        kind = self.kind_filter.currentData()
        group = self.group_filter.currentData()
        priority = self.priority_filter.currentData()
        state = self.state_filter.currentData()
        self.change_filters(
            TimelineFilters(
                text=self.search.text(),
                kind=WorkItemType(kind) if kind else None,
                group_id=UUID(group) if group else None,
                state=TimelineDateState(state) if state else None,
                priority=WorkPriority(priority) if priority not in ("*", "") else None,
                priority_is_set=priority != "*",
            )
        )

    def change_priority_sort(self) -> None:
        if not self.flush_edits():
            self.priority_sort.blockSignals(True)
            self.priority_sort.setCurrentIndex(
                self.priority_sort.findData(self.model.priority_sort_enabled)
            )
            self.priority_sort.blockSignals(False)
            return
        self.model.set_priority_sort(bool(self.priority_sort.currentData()))

    def change_filters(self, filters: TimelineFilters) -> None:
        if not self.flush_edits():
            self.sync_filters()
            return
        self.error.clear()
        self.model.set_filters(filters)

    def sync_filters(self) -> None:
        controls = (
            self.search,
            self.kind_filter,
            self.group_filter,
            self.priority_filter,
            self.state_filter,
            self.priority_sort,
        )
        for control in controls:
            control.blockSignals(True)
            control.setEnabled(self.model.plan is not None)
        current = self.model.filters
        self.search.setText(current.text)
        self.kind_filter.setCurrentIndex(
            self.kind_filter.findData(current.kind.value if current.kind else "")
        )
        self.group_filter.clear()
        self.group_filter.addItem("All WorkGroups", "")
        if self.model.plan:
            for group in self.model.plan.work_groups:
                self.group_filter.addItem(group.name, str(group.id))
        self.group_filter.setCurrentIndex(
            self.group_filter.findData(str(current.group_id) if current.group_id else "")
        )
        priority_data = (
            current.priority.value
            if current.priority_is_set and current.priority is not None
            else ""
            if current.priority_is_set
            else "*"
        )
        self.priority_filter.setCurrentIndex(self.priority_filter.findData(priority_data))
        self.state_filter.setCurrentIndex(
            self.state_filter.findData(current.state.value if current.state else "")
        )
        self.priority_sort.setCurrentIndex(
            self.priority_sort.findData(self.model.priority_sort_enabled)
        )
        for control in controls:
            control.blockSignals(False)
        self.clear_filters_button.setEnabled(self.model.plan is not None)
        result = self.model.result
        self.filter_summary.setText(
            f"{len(result.matches)} of {result.total} work items match"
            f"; {len(result.visible - result.matches)} ancestors shown for context."
        )

    def filters_changed(self) -> None:
        self.restore_selection()
        if self.model.filters != TimelineFilters():
            self.table.expandAll()
        self.sync_filters()
        self.selection_changed()
        self.table.viewport().update()

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
        if self.flush_edits():
            manage_structure(self, self.session, groups=groups)

    def flush_edits(self) -> bool:
        return self.commit_editor() and self.resolve_inspector_draft()

    def resolve_inspector_draft(self) -> bool:
        if not self.inspector.dirty:
            return True
        choice = QMessageBox.warning(
            self,
            "Unsaved work changes",
            "Save changes in the work inspector before continuing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            return self.inspector.apply()
        if choice == QMessageBox.StandardButton.Discard:
            self.inspector.discard()
            return True
        return False

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
        current = self.model.item(self.table.currentIndex())
        if current is None or current.id != self.selected_id:
            self.table.setCurrentIndex(self.model.index_for_id(self.selected_id))

    def refresh(self) -> None:
        for button in self.buttons:
            button.setEnabled(self.session.document.plan is not None)
        self.sync_filters()
        if self.model.filters != TimelineFilters():
            self.table.expandAll()
        self.selection_changed()

    def selection_changed(
        self, current: QModelIndex | None = None, previous: QModelIndex | None = None
    ) -> None:
        if self._selection_guard:
            return
        item = self.model.item(self.table.currentIndex())
        target_id = item.id if item is not None else None
        if self.inspector.dirty and target_id != self.inspector.item_id:
            original_id = self.inspector.item_id
            self._selection_guard = True
            accepted = self.resolve_inspector_draft()
            if not accepted:
                self.table.setCurrentIndex(self.model.index_for_id(original_id))
            self._selection_guard = False
            if not accepted:
                return
            item = self.model.item(self.table.currentIndex())
        self.allocation_button.setEnabled(item is not None)
        if item is not None and self.model.plan is not None:
            if not self.inspector.dirty or self.inspector.item_id != item.id:
                self.inspector.load(
                    self.model.plan,
                    item.id,
                    editable=item.id in self.model.result.matches,
                )
            self.finding_view.set_findings(self.source_model.findings.get(item.id, ()))
        else:
            if not self.inspector.dirty:
                self.inspector.clear()
                self.detail.setText(
                    "Select work to inspect it. Add Tasks under a selected Epic, "
                    "or Subtasks under a selected Task."
                )
            self.finding_view.set_findings(())

    def edit_allocations(self) -> None:
        if not self.flush_edits():
            return
        item = self.model.item(self.table.currentIndex())
        if item is None:
            return
        dialog = AllocationDialog(self, self.session, item.id)
        dialog.exec()
        dialog.deleteLater()

    def add_item(self, kind: WorkItemType) -> None:
        if not self.flush_edits():
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
        transfer_confirmed = False

        def build() -> ProgramPlan:
            nonlocal transfer_confirmed
            item = WorkItem(title=title.text(), kind=kind, parent_id=parent_id)
            if parent_id is not None and self._allocated_leaf(plan, parent_id):
                if not transfer_confirmed:
                    transfer_confirmed = self._confirm_effort_transfer(
                        plan, parent_id, f"the new leaf '{item.title}'"
                    )
                if not transfer_confirmed:
                    raise ValueError("No work was added; the effort transfer was cancelled.")
            updated = add_work_item(plan, item, transfer_parent_effort=transfer_confirmed)
            item_id.append(item.id)
            return updated

        updated = validated_form(self, f"Add {kind.value.title()}", [("&Title", title)], build)
        if updated is not None:
            self.session.apply(updated)
            self.table.setExpanded(self.model.index_for_id(parent_id), True)
            self.table.setCurrentIndex(self.model.index_for_id(item_id[0]))
            self.report_hidden(item_id[0])

    def move_item(self) -> None:
        if not self.flush_edits():
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
        confirmed_parent: UUID | None = None

        def build() -> ProgramPlan:
            nonlocal confirmed_parent
            value = parents.currentData()
            parent_id = UUID(value) if value else None
            resolve = False
            if parent_id is not None and self._allocated_leaf(plan, parent_id):
                if confirmed_parent != parent_id:
                    target = plan.work_item(parent_id)
                    confirmed = self._confirm_effort_transfer(
                        plan, parent_id, f"a new leaf named '{target.title} effort'"
                    )
                    if not confirmed:
                        raise ValueError(
                            "The work was not moved; the effort transfer was cancelled."
                        )
                    confirmed_parent = parent_id
                resolve = True
            return move_work_item(plan, item.id, parent_id, resolve_parent_effort=resolve)

        updated = validated_form(self, "Move work", [("&New parent", parents)], build)
        if updated is not None:
            self.session.apply(updated)
            self.table.expand(self.model.index_for_id(updated.work_item(item.id).parent_id))
            self.table.setCurrentIndex(self.model.index_for_id(item.id))
            self.report_hidden(item.id)

    @staticmethod
    def _allocated_leaf(plan: ProgramPlan, item_id: UUID) -> bool:
        return not plan.children(item_id) and any(
            allocation.work_item_id == item_id for allocation in plan.allocations
        )

    def _confirm_effort_transfer(self, plan: ProgramPlan, item_id: UUID, destination: str) -> bool:
        item = plan.work_item(item_id)
        count = sum(allocation.work_item_id == item_id for allocation in plan.allocations)
        estimate = (
            f"Its entered estimate of {item.estimate_hours} h"
            if item.estimate_hours is not None
            else "Its missing estimate"
        )
        return (
            QMessageBox.question(
                self,
                "Move effort to leaf work",
                f"'{item.title}' is allocated leaf work. Making it a container requires "
                f"an explicit resolution.\n\n{estimate} and {count} allocation(s) will move "
                f"to {destination}. Allocation IDs and hours stay unchanged. Dates, groups, "
                "relationships, and imported baselines do not move.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        )

    def report_hidden(self, item_id: UUID) -> None:
        self.error.setText(
            "The work was saved but is hidden by the current filters. Clear filters to see it."
            if not self.model.index_for_id(item_id).isValid()
            else ""
        )

    def delete_item(self) -> None:
        if not self.flush_edits():
            return
        plan, item = self.session.document.plan, self.model.item(self.table.currentIndex())
        if plan is None or item is None:
            return
        updated = remove_work_item(
            plan, item.id, delete_descendants=True, remove_references=True, remove_allocations=True
        )
        count = len(plan.work_items) - len(updated.work_items)
        links = len(plan.relationships) - len(updated.relationships)
        memberships = sum(len(g.epic_ids) for g in plan.work_groups) - sum(
            len(g.epic_ids) for g in updated.work_groups
        )
        removed = {work.id for work in plan.work_items} - {work.id for work in updated.work_items}
        hidden = len(removed - self.model.result.visible)
        allocations = len(plan.allocations) - len(updated.allocations)
        if (
            QMessageBox.question(
                self,
                "Delete work?",
                f"Delete '{item.title}' and its subtree ({count} work item(s))?\n"
                f"Includes {hidden} work item(s) hidden by filters.\n"
                f"This also removes {links} relationship(s), {memberships} group membership(s), "
                f"and {allocations} work allocation(s).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        ):
            if self.session.document.plan is plan:
                self.session.apply(updated)


class PeoplePage(WorkspacePage):
    def __init__(self, session: Session) -> None:
        super().__init__(
            "People",
            "Compare planning capacity with dated work, reservations, and availability.",
        )
        self.session = session
        self.period: PlanningHorizon | None = None
        self.plan_id: UUID | None = None
        self.selected_person_id: UUID | None = None
        self.breakdown: CapacityBreakdown | None = None
        self.group_projection: PeopleGroupProjection | None = None
        self.detail_buckets: tuple[CapacityBucket, ...] = ()
        self.group_topics: tuple[PersonTopic, ...] = ()
        self._refreshing = False

        ranges = QHBoxLayout()
        self.range_start = CalendarLineEdit()
        self.range_start.setAccessibleName("Capacity range start")
        self.range_start.setPlaceholderText("YYYY-MM-DD")
        self.range_end = CalendarLineEdit()
        self.range_end.setAccessibleName("Capacity range end")
        self.range_end.setPlaceholderText("YYYY-MM-DD")
        ranges.addWidget(label("From"))
        ranges.addWidget(self.range_start)
        ranges.addWidget(label("To"))
        ranges.addWidget(self.range_end)
        for title, mode in (
            ("Day", "day"),
            ("Week", "week"),
            ("Plan horizon", "horizon"),
        ):
            button = QPushButton(title)
            button.setAccessibleName(f"Use {title.lower()} capacity range")
            button.clicked.connect(partial(self.apply_range, mode))
            ranges.addWidget(button)
        self.apply_range_button = QPushButton("Apply range")
        self.apply_range_button.clicked.connect(partial(self.apply_range, "custom"))
        ranges.addWidget(self.apply_range_button)
        self.content.addLayout(ranges)
        self.range_error = label("")
        self.range_error.setAccessibleName("Capacity range validation message")
        self.content.addWidget(self.range_error)
        self.horizon_notice = label("")
        self.content.addWidget(self.horizon_notice)
        filters = QHBoxLayout()
        group_filter_label = label("WorkGroup")
        self.group_filter = QComboBox()
        self.group_filter.setAccessibleName("People WorkGroup filter")
        self.group_filter.addItem("All WorkGroups", "")
        group_filter_label.setBuddy(self.group_filter)
        filters.addWidget(group_filter_label)
        filters.addWidget(self.group_filter)
        filters.addStretch()
        self.content.addLayout(filters)
        self.group_filter_notice = label("")
        self.group_filter_notice.setAccessibleName("People WorkGroup filter summary")
        self.content.addWidget(self.group_filter_notice)
        self.table = QTreeView()
        self.table.setAccessibleName("People roster")
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model = QStandardItemModel(0, 14, self.table)
        self.model.setHorizontalHeaderLabels(
            [
                "Person",
                "Work calendar",
                "Nominal hours",
                "Working days",
                "Unavailable hours",
                "Available hours",
                "Overlap periods",
                "Reserved hours",
                "Planning hours",
                "Allocated work",
                "Remaining hours",
                "Unplaced demand",
                "Status",
                "WorkGroups",
            ]
        )
        self.table.setModel(self.model)
        self.table.header().moveSection(13, 1)
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

        groups = Panel("Selected person WorkGroups")
        self.group_heading = label("Select a person to inspect their whole-plan associations.")
        self.group_heading.setAccessibleName("Selected person WorkGroup summary")
        groups.content.addWidget(self.group_heading)
        self.group_table = QTreeView()
        self.group_table.setAccessibleName("Selected person WorkGroup associations")
        self.group_table.setRootIsDecorated(False)
        self.group_table.setAlternatingRowColors(True)
        self.group_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.group_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.group_model = QStandardItemModel(0, 6, self.group_table)
        self.group_model.setHorizontalHeaderLabels(
            [
                "Reporting topic",
                "Context WorkGroups",
                "Allocated work",
                "Whole-plan hours",
                "Selected-range scheduled",
                "Selected-range unplaced",
            ]
        )
        self.group_table.setModel(self.group_model)
        groups.content.addWidget(self.group_table, 1)
        group_actions = QHBoxLayout()
        self.group_work_choice = QComboBox()
        self.group_work_choice.setAccessibleName("Allocated work in selected reporting topic")
        self.group_work_button = QPushButton("Open allocation...")
        self.group_work_button.clicked.connect(self.open_group_work)
        group_actions.addWidget(self.group_work_choice, 1)
        group_actions.addWidget(self.group_work_button)
        groups.content.addLayout(group_actions)
        self.content.addWidget(groups, 1)

        detail = Panel("Selected person capacity")
        detail_controls = QHBoxLayout()
        detail_controls.addWidget(label("Scale"))
        self.scale = QComboBox()
        self.scale.setAccessibleName("Capacity detail scale")
        for title, value in (
            ("Day", CapacityBucketScale.DAY),
            ("Week", CapacityBucketScale.WEEK),
            ("Selected period", CapacityBucketScale.PERIOD),
        ):
            self.scale.addItem(title, value.value)
        self.scale.setCurrentIndex(self.scale.findData(CapacityBucketScale.WEEK.value))
        self.scale.currentIndexChanged.connect(self.refresh)
        detail_controls.addWidget(self.scale)
        detail_controls.addStretch()
        detail.content.addLayout(detail_controls)
        self.detail_heading = label("Select a person to inspect dated capacity.")
        self.detail_heading.setAccessibleName("Selected person capacity summary")
        detail.content.addWidget(self.detail_heading)
        self.detail_table = QTreeView()
        self.detail_table.setAccessibleName("Selected person capacity periods")
        self.detail_table.setRootIsDecorated(False)
        self.detail_table.setAlternatingRowColors(True)
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_model = QStandardItemModel(0, 7, self.detail_table)
        self.detail_model.setHorizontalHeaderLabels(
            [
                "Period",
                "Planning capacity",
                "Allocated work",
                "Remaining",
                "Load status",
                "Reservations",
                "Work",
            ]
        )
        self.detail_table.setModel(self.detail_model)
        detail.content.addWidget(self.detail_table, 1)
        self.detail_notice = label("")
        self.detail_notice.setAccessibleName("Selected person capacity gaps")
        detail.content.addWidget(self.detail_notice)
        source_actions = QHBoxLayout()
        self.reservation_choice = QComboBox()
        self.reservation_choice.setAccessibleName("Reservation in selected period")
        self.reservation_button = QPushButton("Open reservation...")
        self.reservation_button.clicked.connect(self.open_reservation)
        self.work_choice = QComboBox()
        self.work_choice.setAccessibleName("Work in selected period")
        self.work_button = QPushButton("Open work allocation...")
        self.work_button.clicked.connect(self.open_work)
        for widget in (
            self.reservation_choice,
            self.reservation_button,
            self.work_choice,
            self.work_button,
        ):
            source_actions.addWidget(widget)
        detail.content.addLayout(source_actions)
        self.content.addWidget(detail, 1)

        session.changed.connect(self.refresh)
        self.group_filter.currentIndexChanged.connect(self.refresh)
        self.table.selectionModel().currentChanged.connect(self._selection_changed)
        self.group_table.selectionModel().currentChanged.connect(
            self._group_detail_selection_changed
        )
        self.detail_table.selectionModel().currentChanged.connect(self._detail_selection_changed)
        self.refresh()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        selected = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        if selected:
            self.selected_person_id = UUID(selected)
        self.model.removeRows(0, self.model.rowCount())
        self.breakdown = None
        self.group_projection = None
        plan = self.session.document.plan
        if plan is None:
            self.period = None
            self.plan_id = None
            self.range_start.clear()
            self.range_end.clear()
        elif self.plan_id != plan.id or self.period is None:
            self.plan_id = plan.id
            self._set_period(plan.horizon)
        period = self.period
        self.horizon_notice.setText(
            f"Selected range: {period.start} to {period.end}. "
            f"Plan horizon: {plan.horizon.start} to {plan.horizon.end}. "
            "Unknown capacity is never treated as free time."
            if plan and period
            else "Open a plan to configure calendars."
        )
        for button in (*self.buttons, self.apply_range_button):
            button.setEnabled(plan is not None)
        for editor in (self.range_start, self.range_end):
            editor.setEnabled(plan is not None)
        self.scale.setEnabled(plan is not None)
        if plan and period:
            scale = CapacityBucketScale(self.scale.currentData())
            breakdown = calculate_capacity_breakdown(plan, period, scale)
            self.breakdown = breakdown
            projection = calculate_people_groups(plan, breakdown)
            self.group_projection = projection
            self._refresh_group_filter(projection)
            assigned = {
                value.person_id: plan.work_calendar(value.calendar_id)
                for value in plan.person_calendars
            }
            association_key = self.group_filter.currentData() or ""
            visible_people = tuple(
                person for person in projection.people if person.matches(association_key)
            )
            self.group_filter_notice.setText(
                f"Showing {len(visible_people)} of {len(projection.people)} people. "
                "WorkGroup associations use positive whole-plan allocations; capacity values "
                "still include all competing work in the selected range."
            )
            for group_person in visible_people:
                capacity = breakdown.person(group_person.person_id)
                person = plan.person(group_person.person_id)
                calendar = assigned.get(capacity.person_id)
                nominal = nominal_capacity(calendar, period) if calendar else None
                availability = (
                    availability_capacity(
                        calendar,
                        period,
                        person.id,
                        tuple(
                            event
                            for event in plan.availability_events
                            if event.person_id == person.id
                        ),
                    )
                    if calendar
                    else None
                )
                row = [
                    QStandardItem(value)
                    for value in (
                        f"{person.name} [{str(person.id)[:8]}]",
                        calendar.name if calendar else "Not configured",
                        str(nominal.total_hours) if nominal else "Unknown",
                        str(nominal.working_days) if nominal else "Unknown",
                        str(availability.unavailable_hours) if availability else "Unknown",
                        str(availability.available_hours) if availability else "Unknown",
                        str(len(availability.overlaps)) if availability else "Unknown",
                        self._hours(capacity.reserved_hours),
                        self._hours(capacity.planning_hours),
                        self._hours(capacity.allocated_hours),
                        self._hours(capacity.remaining_hours),
                        self._hours(capacity.unplaced_hours),
                        self._state_text(capacity.state),
                        ", ".join(association.label for association in group_person.associations),
                    )
                ]
                for item in row:
                    item.setData(str(person.id), Qt.ItemDataRole.UserRole)
                    item.setEditable(False)
                self._decorate_status(row[-1], capacity.state, capacity.gaps)
                self.model.appendRow(row)
                if capacity.person_id == self.selected_person_id:
                    self.table.setCurrentIndex(row[0].index())
            if not self.table.currentIndex().isValid() and self.model.rowCount():
                self.table.setCurrentIndex(self.model.index(0, 0))
        else:
            self._refresh_group_filter(None)
            self.group_filter_notice.setText("Open a plan to inspect WorkGroup associations.")
        self._refreshing = False
        self._selection_changed()
        for column in range(self.model.columnCount()):
            self.table.resizeColumnToContents(column)
        self.table.setColumnWidth(13, min(self.table.columnWidth(13), 360))

    def _selection_changed(self, *args: object) -> None:
        selected_value = self.table.currentIndex().data(Qt.ItemDataRole.UserRole)
        selected = bool(selected_value)
        self.selected_person_id = UUID(selected_value) if selected_value else None
        self.assign_button.setEnabled(selected)
        self.availability_button.setEnabled(selected)
        self._refresh_group_detail()
        self._refresh_detail()

    def _refresh_group_filter(self, projection: PeopleGroupProjection | None) -> None:
        selected = self.group_filter.currentData() or ""
        choices = projection.filters if projection is not None else ()
        available = {choice.key for choice in choices}
        if selected not in available:
            selected = ""
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All WorkGroups", "")
        for choice in choices:
            title = (
                f"{choice.label} [{str(choice.group_id)[:8]}]"
                if choice.group_id is not None
                else choice.label
            )
            self.group_filter.addItem(title, choice.key)
        self.group_filter.setCurrentIndex(max(0, self.group_filter.findData(selected)))
        self.group_filter.setEnabled(projection is not None)
        self.group_filter.blockSignals(False)

    @staticmethod
    def _hours(value: Fraction | None) -> str:
        return hours_text(value) if value is not None else "Unknown"

    @staticmethod
    def _state_text(state: CapacityLoadState) -> str:
        return {
            CapacityLoadState.UNKNOWN: "Unknown",
            CapacityLoadState.INCOMPLETE: "Incomplete",
            CapacityLoadState.OVERLOADED: "Overloaded",
            CapacityLoadState.FULL: "Fully allocated",
            CapacityLoadState.WITHIN_CAPACITY: "Within capacity",
            CapacityLoadState.NO_WORK: "No allocated work",
            CapacityLoadState.NO_CAPACITY: "No planning capacity",
        }[state]

    @staticmethod
    def _decorate_status(
        item: QStandardItem, state: CapacityLoadState, gaps: tuple[object, ...]
    ) -> None:
        colors = {
            CapacityLoadState.UNKNOWN: QColor(128, 128, 128, 70),
            CapacityLoadState.INCOMPLETE: QColor(245, 166, 35, 70),
            CapacityLoadState.OVERLOADED: QColor(219, 68, 55, 80),
            CapacityLoadState.FULL: QColor(245, 166, 35, 55),
            CapacityLoadState.WITHIN_CAPACITY: QColor(39, 174, 96, 55),
            CapacityLoadState.NO_WORK: QColor(32, 139, 173, 45),
            CapacityLoadState.NO_CAPACITY: QColor(128, 128, 128, 45),
        }
        item.setBackground(colors[state])
        messages = tuple(str(getattr(gap, "message", gap)) for gap in gaps)
        if messages:
            item.setToolTip("\n".join(dict.fromkeys(messages)))

    def _set_period(self, period: PlanningHorizon) -> None:
        self.period = period
        self.range_start.setText(str(period.start))
        self.range_end.setText(str(period.end))
        self.range_error.clear()

    def apply_range(self, mode: str) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        try:
            if mode == "horizon":
                period = plan.horizon
            else:
                start = date.fromisoformat(self.range_start.text().strip())
                if mode == "day":
                    period = day_period(start)
                elif mode == "week":
                    period = week_period(start)
                else:
                    period = PlanningHorizon(
                        start, date.fromisoformat(self.range_end.text().strip())
                    )
        except ValueError as error:
            self.range_error.setText(
                f"Enter valid dates as YYYY-MM-DD with the start on or before the end. {error}"
            )
            return
        self._set_period(period)
        self.refresh()

    def _refresh_group_detail(self) -> None:
        self.group_model.removeRows(0, self.group_model.rowCount())
        self.group_topics = ()
        projection = self.group_projection
        person_id = self.selected_person_id
        if projection is None or person_id is None:
            self.group_heading.setText("Select a person to inspect their whole-plan associations.")
            self._group_detail_selection_changed()
            return
        person = projection.person(person_id)
        self.group_topics = person.topics
        associations = ", ".join(value.label for value in person.associations)
        self.group_heading.setText(
            f"{person.person_name}: whole-plan associations: {associations}. "
            f"Range hours use {projection.period.start} to {projection.period.end}; "
            "capacity still includes the complete competing workload."
        )
        for index, topic in enumerate(person.topics):
            topic_label = (
                f"{topic.label} [{str(topic.group_id)[:8]}]"
                if topic.group_id is not None
                else topic.label
            )
            context = ", ".join(value.label for value in topic.context_groups)
            work = ", ".join(
                f"{value.title} [{str(value.work_item_id)[:8]}]" for value in topic.work_items
            )
            row = [
                QStandardItem(value)
                for value in (
                    topic_label,
                    context,
                    work,
                    self._hours(topic.whole_plan_hours),
                    self._hours(topic.scheduled_hours),
                    self._hours(topic.unplaced_hours),
                )
            ]
            for item in row:
                item.setData(index, Qt.ItemDataRole.UserRole)
                item.setEditable(False)
            self.group_model.appendRow(row)
        if self.group_model.rowCount():
            self.group_table.setCurrentIndex(self.group_model.index(0, 0))
        for column in range(self.group_model.columnCount()):
            self.group_table.resizeColumnToContents(column)
        self._group_detail_selection_changed()

    def _group_detail_selection_changed(self, *args: object) -> None:
        self.group_work_choice.clear()
        index = self.group_table.currentIndex().data(Qt.ItemDataRole.UserRole)
        topic = (
            self.group_topics[index]
            if isinstance(index, int) and index < len(self.group_topics)
            else None
        )
        if topic is not None:
            for work in topic.work_items:
                self.group_work_choice.addItem(
                    f"{work.title} [{str(work.work_item_id)[:8]}] - whole plan "
                    f"{self._hours(work.whole_plan_hours)} h; selected range "
                    f"{self._hours(work.scheduled_hours)} h; unplaced "
                    f"{self._hours(work.unplaced_hours)} h",
                    str(work.work_item_id),
                )
        self.group_work_button.setEnabled(self.group_work_choice.count() > 0)

    def open_group_work(self) -> None:
        selected = self.group_work_choice.currentData()
        if selected:
            dialog = AllocationDialog(self, self.session, UUID(selected))
            dialog.exec()
            dialog.deleteLater()

    def _refresh_detail(self) -> None:
        self.detail_model.removeRows(0, self.detail_model.rowCount())
        self.detail_buckets = ()
        plan = self.session.document.plan
        if (
            plan is None
            or self.period is None
            or self.selected_person_id is None
            or self.breakdown is None
        ):
            self.detail_heading.setText("Select a person to inspect dated capacity.")
            self.detail_notice.clear()
            self._detail_selection_changed()
            return
        person = self.breakdown.person(self.selected_person_id)
        self.detail_buckets = person.buckets
        self.detail_heading.setText(
            f"{plan.person(person.person_id).name}: "
            f"planning {self._hours(person.planning_hours)} h; "
            f"allocated {self._hours(person.allocated_hours)} h; "
            f"remaining {self._hours(person.remaining_hours)} h."
        )
        unique_messages = tuple(dict.fromkeys(gap.message for gap in person.gaps))
        self.detail_notice.setText("\n".join(unique_messages))
        for index, bucket in enumerate(person.buckets):
            reservation_names = {rule.id: rule.name for rule in plan.reservation_rules}
            reservations = ", ".join(
                f"{reservation_names.get(entry.rule_id, 'Unknown reservation')}: "
                f"{self._hours(entry.hours)} h"
                for entry in bucket.reservations
            )
            work = ", ".join(
                f"{plan.work_item(entry.work_item_id).title}: {self._hours(entry.hours)} h"
                for entry in bucket.allocations
            )
            row = [
                QStandardItem(value)
                for value in (
                    self._period_text(bucket.period),
                    self._hours(bucket.planning_hours),
                    self._hours(bucket.allocated_hours),
                    self._hours(bucket.remaining_hours),
                    self._state_text(bucket.state),
                    reservations or "-",
                    work or "-",
                )
            ]
            for item in row:
                item.setData(index, Qt.ItemDataRole.UserRole)
                item.setEditable(False)
            self._decorate_status(row[4], bucket.state, bucket.gaps)
            self.detail_model.appendRow(row)
        if self.detail_model.rowCount():
            self.detail_table.setCurrentIndex(self.detail_model.index(0, 0))
        for column in range(self.detail_model.columnCount()):
            self.detail_table.resizeColumnToContents(column)
        self._detail_selection_changed()

    @staticmethod
    def _period_text(period: PlanningHorizon) -> str:
        return (
            str(period.start) if period.start == period.end else f"{period.start} to {period.end}"
        )

    def _detail_selection_changed(self, *args: object) -> None:
        self.reservation_choice.blockSignals(True)
        self.work_choice.blockSignals(True)
        self.reservation_choice.clear()
        self.work_choice.clear()
        index = self.detail_table.currentIndex().data(Qt.ItemDataRole.UserRole)
        plan = self.session.document.plan
        bucket = (
            self.detail_buckets[index]
            if isinstance(index, int) and index < len(self.detail_buckets)
            else None
        )
        if plan is not None and bucket is not None:
            names = {rule.id: rule.name for rule in plan.reservation_rules}
            for entry in bucket.reservations:
                self.reservation_choice.addItem(
                    f"{names.get(entry.rule_id, 'Unknown reservation')} "
                    f"({self._hours(entry.hours)} h)",
                    str(entry.rule_id),
                )
            for allocation_entry in bucket.allocations:
                self.work_choice.addItem(
                    f"{plan.work_item(allocation_entry.work_item_id).title} "
                    f"({self._hours(allocation_entry.hours)} h)",
                    str(allocation_entry.work_item_id),
                )
        self.reservation_choice.blockSignals(False)
        self.work_choice.blockSignals(False)
        self.reservation_button.setEnabled(self.reservation_choice.count() > 0)
        self.work_button.setEnabled(self.work_choice.count() > 0)

    def open_reservation(self) -> None:
        selected = self.reservation_choice.currentData()
        if selected:
            reserve_capacity_dialog(self, self.session, UUID(selected))

    def open_work(self) -> None:
        selected = self.work_choice.currentData()
        if selected:
            dialog = AllocationDialog(self, self.session, UUID(selected))
            dialog.exec()
            dialog.deleteLater()

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
            owned = sum(item.assignee_id == person.id for item in plan.work_items)
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
                    f"and {entries} availability entries?\n"
                    f"This removes {sum(a.person_id == person.id for a in plan.allocations)} "
                    f"work allocation(s) and clears {owned} work assignee reference(s)."
                    + reservation_notice,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                == QMessageBox.StandardButton.Yes
            ):
                if self.session.document.plan is plan:
                    self.session.apply(
                        remove_person(
                            plan,
                            person.id,
                            remove_availability=True,
                            remove_reservations=True,
                            remove_allocations=True,
                            clear_assignees=True,
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
