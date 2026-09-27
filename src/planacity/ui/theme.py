"""Shared colors and widget styling for the desktop's two appearances."""

from dataclasses import dataclass
from enum import StrEnum


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class Colors:
    background: str
    sidebar: str
    surface: str
    text: str
    muted: str
    border: str
    accent: str
    selected: str
    hover: str
    disabled: str


COLORS = {
    Theme.LIGHT: Colors(
        "#f8fafc",
        "#f1f5f9",
        "#ffffff",
        "#142033",
        "#596b82",
        "#dce4ee",
        "#006f93",
        "#dceff7",
        "#eaf2f7",
        "#8491a2",
    ),
    Theme.DARK: Colors(
        "#111923",
        "#16212e",
        "#1b2838",
        "#e7eef7",
        "#a5b6cc",
        "#34465c",
        "#68cbe8",
        "#203e51",
        "#253648",
        "#7e90a6",
    ),
}


def stylesheet(theme: Theme) -> str:
    """Keep every content surface, selection, and focus indicator in one theme."""
    c = COLORS[theme]
    return f"""
        QWidget {{ color: {c.text}; font-size: 14px; }}
        QMainWindow, QDialog, QMessageBox, QStackedWidget, QScrollArea, QWidget#page {{
            background: {c.background};
        }}
        QLabel {{ background: transparent; }}
        QLineEdit, QPlainTextEdit, QComboBox, QListWidget {{
            background: {c.surface}; color: {c.text}; border: 1px solid {c.border};
            padding: 6px; selection-background-color: {c.selected};
            selection-color: {c.text};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {c.accent}; }}
        QLabel[role="muted"] {{ color: {c.muted}; }}
        QLabel[role="title"] {{ font-size: 32px; font-weight: 700; }}
        QLabel[role="subtitle"] {{ color: {c.muted}; font-size: 16px; }}
        QLabel[role="heading"] {{ font-size: 18px; font-weight: 600; }}
        QLabel[role="metric"] {{ font-size: 30px; font-weight: 650; }}
        QLabel[role="eyebrow"] {{ color: {c.muted}; font-size: 12px; }}
        QLabel[role="badge"] {{
            background: {c.selected}; color: {c.accent};
            border-radius: 5px; padding: 6px 10px; font-size: 12px;
        }}
        QLabel#brand {{ font-size: 21px; font-weight: 700; }}
        QLabel#brandMark {{
            background: {c.accent}; color: {c.background}; border-radius: 8px;
            font-size: 20px; font-weight: 750;
        }}
        QFrame#sidebar {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
        QFrame[role="panel"] {{
            background: {c.surface}; border: 1px solid {c.border}; border-radius: 8px;
        }}
        QFrame[role="divider"] {{ background: {c.border}; border: none; }}
        QPushButton {{
            background: {c.surface}; border: 1px solid {c.border};
            border-radius: 6px; padding: 9px 14px;
        }}
        QPushButton:hover {{ background: {c.hover}; border-color: {c.accent}; }}
        QPushButton:checked {{ background: {c.selected}; color: {c.accent}; }}
        QPushButton:focus {{ border: 1px solid {c.accent}; }}
        QPushButton:disabled {{ background: {c.sidebar}; color: {c.disabled}; }}
        QPushButton[role="nav"] {{
            text-align: left; background: transparent; border: 1px solid transparent;
            padding: 13px 14px; font-size: 16px;
        }}
        QPushButton[role="nav"]:hover {{ background: {c.hover}; }}
        QPushButton[role="nav"]:checked {{
            background: {c.selected}; color: {c.accent}; font-weight: 600;
        }}
        QPushButton[role="nav"]:focus {{ border-color: {c.accent}; }}
        QMenuBar, QStatusBar {{ background: {c.sidebar}; color: {c.muted}; }}
        QMenuBar {{ border-bottom: 1px solid {c.border}; padding: 3px 12px; }}
        QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {c.selected}; }}
        QMenu {{ background: {c.surface}; border: 1px solid {c.border}; padding: 5px; }}
        QMenu::item {{ padding: 7px 28px; }}
        QMenu::item:disabled {{ color: {c.disabled}; }}
        QMenu::separator {{ height: 1px; background: {c.border}; margin: 5px; }}
        QStatusBar {{ border-top: 1px solid {c.border}; padding: 4px 12px; }}
        QStatusBar::item {{ border: none; }}
        QTreeView {{
            background: {c.surface}; alternate-background-color: {c.background};
            border: none; selection-background-color: {c.selected};
            selection-color: {c.text}; outline: none;
        }}
        QTreeView::item {{ padding: 10px; border-bottom: 1px solid {c.border}; }}
        QTreeView::item:focus {{ border: 1px solid {c.accent}; }}
        QHeaderView {{ background: {c.surface}; }}
        QHeaderView::section {{
            background: {c.surface}; color: {c.muted};
            border: none; border-bottom: 1px solid {c.border}; padding: 12px 8px;
        }}
        QSplitter::handle {{ background: {c.background}; }}
        QSplitter::handle:hover {{ background: {c.border}; }}
        QToolTip {{ background: {c.surface}; color: {c.text}; border: 1px solid {c.border}; }}
        QScrollBar:vertical {{ background: {c.background}; width: 10px; }}
        QScrollBar::handle:vertical {{
            background: {c.border}; min-height: 24px; border-radius: 4px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{ background: {c.background}; height: 10px; }}
        QScrollBar::handle:horizontal {{
            background: {c.border}; min-width: 24px; border-radius: 4px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
    """
