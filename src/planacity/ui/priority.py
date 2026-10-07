"""Shared labels and theme-aware icons for canonical work priorities."""

from functools import lru_cache

from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication

from planacity.domain import WorkPriority
from planacity.ui.icons import svg_icon

PRIORITY_ORDER = tuple(WorkPriority)
PRIORITY_LABELS = {
    WorkPriority.HIGHEST: "Highest",
    WorkPriority.HIGH: "High",
    WorkPriority.MEDIUM: "Medium",
    WorkPriority.LOW: "Low",
    WorkPriority.LOWEST: "Lowest",
}
_PRIORITY_ICONS = {
    WorkPriority.HIGHEST: "priority-highest.svg",
    WorkPriority.HIGH: "priority-high.svg",
    WorkPriority.MEDIUM: "priority-medium.svg",
    WorkPriority.LOW: "priority-low.svg",
    WorkPriority.LOWEST: "priority-lowest.svg",
    None: "priority-unset.svg",
}


def priority_label(priority: WorkPriority | None) -> str:
    return "Unset" if priority is None else PRIORITY_LABELS[priority]


def priority_rank(priority: WorkPriority | None) -> int:
    return len(PRIORITY_ORDER) if priority is None else PRIORITY_ORDER.index(priority)


@lru_cache(maxsize=24)
def _icon(filename: str, color: str) -> QIcon:
    return svg_icon(filename, color)


def priority_icon(priority: WorkPriority | None) -> QIcon:
    color = QApplication.palette().color(QPalette.ColorRole.Text).name()
    return _icon(_PRIORITY_ICONS[priority], color)
