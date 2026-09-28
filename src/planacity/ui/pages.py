"""Shared workspace layout widgets and the deferred Jira import page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def label(text: str, role: str = "muted") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
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
