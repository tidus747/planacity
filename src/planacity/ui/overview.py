"""A summary of the open plan, without fabricated capacity figures."""

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QPushButton

from planacity.ui.pages import Panel, WorkspacePage, label
from planacity.ui.session import Session


class OverviewPage(WorkspacePage):
    def __init__(
        self, session: Session, on_new: Callable[[], None], on_plan: Callable[[], None]
    ) -> None:
        super().__init__("Program overview", "Plan the work. Respect the capacity.")
        self.session = session
        metrics = QHBoxLayout()
        self.values = []
        for title in ("Work items", "People", "Planning horizon"):
            panel = Panel(title)
            value = label("Not set", "heading")
            self.values.append(value)
            panel.content.addWidget(value)
            metrics.addWidget(panel)
        self.content.addLayout(metrics)
        panel = Panel("Program Plan")
        self.name = label("No project open", "title")
        self.description = label("Create a plan or open a local project from the File menu.")
        panel.content.addWidget(self.name)
        panel.content.addWidget(self.description)
        actions = QHBoxLayout()
        for title, callback in (("New plan...", on_new), ("View plan", on_plan)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        panel.content.addLayout(actions)
        panel.content.addStretch()
        self.content.addWidget(panel, 1)
        self.content.addWidget(
            label(
                "Jira CSV is planned for v0.2. "
                "Capacity and recurring reservations are planned for v0.4."
            )
        )
        session.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        plan = self.session.document.plan
        if plan is None:
            return
        self.name.setText(plan.name)
        self.description.setText(
            plan.description or "Add a description through File -> Plan properties."
        )
        for widget, value in zip(
            self.values,
            (
                str(len(plan.work_items)),
                str(len(plan.people)),
                f"{plan.horizon.start.isoformat()} to {plan.horizon.end.isoformat()}",
            ),
            strict=True,
        ):
            widget.setText(value)
