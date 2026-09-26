"""Honest empty-state layouts for the initial planning workspace."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


def label(text: str, role: str = "muted") -> QLabel:
    widget = QLabel(text)
    widget.setProperty("role", role)
    widget.setWordWrap(True)
    return widget


class Panel(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setProperty("role", "panel")
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(22, 22, 22, 22)
        self.content.setSpacing(16)
        self.content.addWidget(label(title, "heading"))


class WorkspacePage(QWidget):
    def __init__(self, title: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("page")
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(32, 32, 32, 32)
        self.content.setSpacing(24)
        self.header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        titles.addWidget(label(title, "title"))
        titles.addWidget(label(subtitle, "subtitle"))
        self.header.addLayout(titles, 1)
        self.content.addLayout(self.header)


def _button(text: str, callback: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.clicked.connect(callback)
    return button


def overview_page(on_plan: Callable[[], None], on_people: Callable[[], None]) -> WorkspacePage:
    page = WorkspacePage("Program overview", "Plan the work. Respect the capacity.")
    badge = label("No planning horizon", "badge")
    page.header.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)
    metrics = QHBoxLayout()
    metrics.setSpacing(16)
    for title, description in (
        ("Work items", "Epics, Tasks & Subtasks"),
        ("People", "Your program team"),
        ("Planning horizon", "A date range that fits your program"),
    ):
        panel = Panel(title)
        panel.content.addWidget(label("Not set", "metric"))
        panel.content.addWidget(label(description))
        metrics.addWidget(panel, 1)
    page.content.addLayout(metrics)

    panels = QHBoxLayout()
    panels.setSpacing(16)
    structure = Panel("Program structure")
    structure.content.addStretch()
    structure.content.addWidget(label("Your program starts here", "heading"))
    structure.content.addWidget(
        label("Organize the work into Epics, Tasks and Subtasks, then add estimates and dates.")
    )
    structure.content.addWidget(
        label("No project is open. Creating and saving a plan is coming in v0.1.")
    )
    actions = QHBoxLayout()
    actions.addWidget(_button("View plan", on_plan))
    actions.addWidget(_button("View people", on_people))
    actions.addStretch()
    structure.content.addLayout(actions)
    structure.content.addStretch()
    panels.addWidget(structure, 3)

    checklist = Panel("Planning Foundation")
    checklist.content.addWidget(label("COMING IN v0.1", "eyebrow"))
    for title, description in (
        ("01  Define the program", "Name your plan and choose its planning horizon."),
        ("02  Structure the work", "Add work, people, estimates and relationships."),
        ("03  Save and continue", "Keep your plan locally and reopen it when you need it."),
    ):
        checklist.content.addWidget(label(title, "heading"))
        checklist.content.addWidget(label(description))
    checklist.content.addStretch()
    panels.addWidget(checklist, 2)
    page.content.addLayout(panels, 1)
    page.content.addWidget(
        label(
            "Development preview | Navigation and appearance are available. Plan editing is next."
        )
    )
    return page


def _empty_table(headers: list[str], name: str) -> QTreeView:
    table = QTreeView()
    table.setObjectName(name)
    table.setAccessibleName(name)
    model = QStandardItemModel(0, len(headers), table)
    model.setHorizontalHeaderLabels(headers)
    table.setModel(model)
    table.setRootIsDecorated(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setMinimumHeight(130)
    table.setColumnWidth(0, 180)
    for column in range(1, len(headers)):
        table.setColumnWidth(column, 105)
    return table


def work_page(*, people: bool = False) -> WorkspacePage:
    """Reserve a real Qt model/view surface and a resizable detail panel."""
    title = "People" if people else "Program plan"
    subtitle = "The people behind your program." if people else "Structure the work. Make the plan."
    page = WorkspacePage(title, subtitle)
    add = QPushButton("+  Add person" if people else "+  Add item")
    add.setEnabled(False)
    add.setToolTip(
        "People editing is coming in v0.1." if people else "Work editing is coming in v0.1."
    )
    page.header.addWidget(add, alignment=Qt.AlignmentFlag.AlignTop)

    split = QSplitter(Qt.Orientation.Horizontal)
    split.setChildrenCollapsible(False)
    split.setHandleWidth(16)
    listing = Panel("Team roster" if people else "Planned work")
    headers = (
        ["Person", "Notes"] if people else ["Work item", "Type", "Estimate (h)", "Start", "End"]
    )
    listing.content.addWidget(
        _empty_table(headers, "People roster" if people else "Plan work items")
    )
    listing.content.addWidget(label("No people yet" if people else "No work items yet", "heading"))
    listing.content.addWidget(
        label(
            "People editing will be available with the v0.1 planning workspace."
            if people
            else "Work editing will be available with the v0.1 planning workspace."
        )
    )
    listing.content.addStretch()
    listing.setMinimumWidth(320)
    split.addWidget(listing)
    details = Panel("Person details" if people else "Work item details")
    details.setMinimumWidth(240)
    details.content.addWidget(label("No person selected" if people else "No work item selected"))
    details.content.addWidget(
        label(
            "This panel will show the selected person's details."
            if people
            else "This panel will show the selected item's estimate, dates and relationships."
        )
    )
    details.content.addStretch()
    details.content.addWidget(
        label(
            "Team availability and capacity are planned for v0.4."
            if people
            else "Estimates are in hours. Dates can span any planning horizon."
        )
    )
    split.addWidget(details)
    split.setStretchFactor(0, 3)
    split.setStretchFactor(1, 2)
    split.setSizes([600, 300])
    page.content.addWidget(split, 1)
    page.content.addWidget(label("Development preview | No project open"))
    return page


def import_page() -> WorkspacePage:
    page = WorkspacePage("Import work", "Bring existing planning data into Planacity.")
    panels = QHBoxLayout()
    panels.setSpacing(16)
    for title, description in (
        ("Jira CSV", "Bring work from an exported Jira CSV file."),
        (
            "Field mapping",
            "Match exported columns to Planacity fields and review before importing.",
        ),
    ):
        panel = Panel(title)
        panel.content.addWidget(label(description))
        panel.content.addWidget(label("PLANNED FOR v0.2", "eyebrow"))
        panels.addWidget(panel, 1)
    page.content.addLayout(panels)
    notice = Panel("Import is coming in v0.2")
    notice.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    notice.content.addWidget(
        label(
            "The first release focuses on building and saving plans manually. "
            "Jira CSV import, reusable field mappings and a preview step will follow."
        )
    )
    notice.content.addWidget(label("No file is read or imported by this preview."))
    page.content.addWidget(notice)
    page.content.addStretch()
    return page
