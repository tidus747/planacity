"""Focused group and relationship editors over the shared plan."""

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from planacity.domain import ProgramPlan, Relationship, RelationshipType, WorkGroup, WorkItemType
from planacity.planning.structure import (
    add_relationship,
    add_work_group,
    remove_relationship,
    remove_work_group,
    rename_work_group,
    set_group_epics,
)
from planacity.ui.forms import validated_form
from planacity.ui.session import Session


def manage_structure(parent: QWidget, session: Session, *, groups: bool) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("WorkGroups" if groups else "Relationships")
    dialog.resize(660, 420)
    layout = QVBoxLayout(dialog)
    listing = QListWidget()
    listing.setAccessibleName(dialog.windowTitle())
    layout.addWidget(listing)
    buttons = QHBoxLayout()
    layout.addLayout(buttons)

    def refresh() -> None:
        listing.clear()
        plan = session.document.plan
        if plan is None:
            return
        if groups:
            rows = [(g.id, f"{g.name} ({len(g.epic_ids)} Epics)") for g in plan.work_groups]
        else:
            rows = [
                (
                    r.id,
                    f"{plan.work_item(r.source_id).title} {r.kind.value} "
                    f"{plan.work_item(r.target_id).title}",
                )
                for r in plan.relationships
            ]
        for item_id, title in rows:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, str(item_id))
            listing.addItem(item)

    def edit(*, existing: bool = False) -> None:
        plan = session.document.plan
        selected = listing.currentItem()
        if plan is None or (existing and selected is None):
            return
        if groups:
            group = (
                plan.work_group(UUID(selected.data(Qt.ItemDataRole.UserRole))) if existing else None
            )
            name = QLineEdit(group.name if group else "")
            members = QListWidget()
            for epic in plan.work_items:
                if epic.kind == WorkItemType.EPIC:
                    row = QListWidgetItem(f"{epic.title} [{str(epic.id)[:8]}]")
                    row.setData(Qt.ItemDataRole.UserRole, str(epic.id))
                    row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    row.setCheckState(
                        Qt.CheckState.Checked
                        if group and epic.id in group.epic_ids
                        else Qt.CheckState.Unchecked
                    )
                    members.addItem(row)

            def build_group() -> ProgramPlan:
                ids = tuple(
                    UUID(members.item(i).data(Qt.ItemDataRole.UserRole))
                    for i in range(members.count())
                    if members.item(i).checkState() == Qt.CheckState.Checked
                )
                if group:
                    ids = tuple(i for i in group.epic_ids if i in ids) + tuple(
                        i for i in ids if i not in group.epic_ids
                    )
                    return set_group_epics(
                        rename_work_group(plan, group.id, name.text()), group.id, ids
                    )
                return add_work_group(plan, WorkGroup(name=name.text(), epic_ids=ids))

            updated = validated_form(
                dialog,
                "Edit WorkGroup" if group else "Add WorkGroup",
                [("&Name", name), ("&Epics", members)],
                build_group,
            )
        else:
            source, target, kind = QComboBox(), QComboBox(), QComboBox()
            for work in plan.work_items:
                label = f"{work.title} [{str(work.id)[:8]}]"
                source.addItem(label, str(work.id))
                target.addItem(label, str(work.id))
            for value in RelationshipType:
                kind.addItem(value.value, value.value)

            def build_link() -> ProgramPlan:
                if source.currentData() is None or target.currentData() is None:
                    raise ValueError("Add work items before creating a relationship.")
                return add_relationship(
                    plan,
                    Relationship(
                        source_id=UUID(source.currentData()),
                        target_id=UUID(target.currentData()),
                        kind=RelationshipType(kind.currentData()),
                    ),
                )

            updated = validated_form(
                dialog,
                "Add relationship",
                [("&Source", source), ("&Relationship", kind), ("&Target", target)],
                build_link,
            )
        if updated is not None:
            session.apply(updated)
            refresh()

    def remove() -> None:
        row, plan = listing.currentItem(), session.document.plan
        if row is None or plan is None:
            return
        item_id = UUID(row.data(Qt.ItemDataRole.UserRole))
        primary_references = (
            tuple(item for item in plan.work_items if item.primary_group_id == item_id)
            if groups
            else ()
        )
        message = "Remove this entry? Work items will be preserved."
        if primary_references:
            message = (
                f"Remove this WorkGroup? {len(primary_references)} work item(s) use it as "
                "their primary reporting topic. Their primary topic will be cleared; "
                "the work items themselves will be preserved."
            )
        if (
            QMessageBox.question(
                dialog,
                "Remove entry?",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        session.apply(
            remove_work_group(
                plan,
                item_id,
                clear_primary_references=bool(primary_references),
            )
            if groups
            else remove_relationship(plan, item_id)
        )
        refresh()

    add = QPushButton("&Add")
    add.clicked.connect(lambda: edit())
    buttons.addWidget(add)
    if groups:
        rename = QPushButton("&Edit")
        rename.clicked.connect(lambda: edit(existing=True))
        buttons.addWidget(rename)
    delete = QPushButton("&Remove")
    delete.clicked.connect(remove)
    buttons.addWidget(delete)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    refresh()
    dialog.exec()
    dialog.deleteLater()
