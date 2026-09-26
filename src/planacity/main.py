"""Desktop application entry point."""

import sys
from importlib.metadata import version

from PySide6.QtWidgets import QApplication

from planacity.ui.main_window import MainWindow


def main() -> int:
    """Start the desktop shell and return Qt's exit status."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Planacity")
    app.setApplicationVersion(version("planacity"))
    window = MainWindow()
    window.show()
    return app.exec()
