"""Shared workspace layout widgets."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
