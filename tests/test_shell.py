"""Check the initial desktop navigation and application lifecycle."""

import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTreeView

from planacity.ui.main_window import MainWindow


def test_shell_navigation_and_close(app: QApplication, window: MainWindow) -> None:
    assert window.isVisible()
    assert not window.windowIcon().isNull()
    brand = window.findChild(QLabel, "brandLogo")
    assert brand is window.brand_logo
    assert brand.accessibleName() == "Planacity"
    assert brand.text() == ""
    assert brand.pixmap() is not None
    assert not brand.pixmap().isNull()
    assert window.pages.count() == 6
    assert tuple(window.navigation) == (
        "Overview",
        "Plan",
        "Timeline",
        "People",
        "Import",
        "Changes",
    )
    for index, button in enumerate(window.navigation.values()):
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert window.pages.currentIndex() == index
        assert window.pages.currentWidget().isVisible()
        assert button.isChecked()
        assert sum(b.isChecked() for b in window.navigation.values()) == 1
    assert window.close()
    assert not window.isVisible()


def test_keyboard_navigation_and_empty_workspaces(app: QApplication, window: MainWindow) -> None:
    plan_button = window.navigation["Plan"]
    plan_button.setFocus()
    QTest.keyClick(plan_button, Qt.Key.Key_Space)
    app.processEvents()
    assert window.pages.currentIndex() == 1
    tables = window.findChildren(QTreeView)
    assert len(tables) == 4
    assert all(table.model().rowCount() == 0 for table in tables)


def test_entry_point_starts_and_exits() -> None:
    # A fresh process exercises the real entry point without a second QApplication.
    script = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import planacity.main as entry

events = []

class TimedApplication(QApplication):
    def __init__(self, *args, **kwargs):
        assert events == ["identity"]
        super().__init__(*args, **kwargs)

    def exec(self):
        assert not self.windowIcon().isNull()
        QTimer.singleShot(0, self.quit)
        return super().exec()

entry._set_windows_runtime_identity = lambda: events.append("identity")
entry.QApplication = TimedApplication
raise SystemExit(entry.main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
