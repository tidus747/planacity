"""Desktop application entry point."""

import ctypes
import sys
from importlib.metadata import version

from PySide6.QtWidgets import QApplication

from planacity.ui.icons import image_icon
from planacity.ui.main_window import MainWindow

WINDOWS_APP_ID = "Planacity.Planacity"


def _set_windows_runtime_identity() -> None:
    """Identify this hosted Python process to the Windows taskbar before UI creation."""
    if sys.platform != "win32":
        return
    try:
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        setter(WINDOWS_APP_ID)
    except (AttributeError, OSError):
        # The icon still works inside Qt if a restricted Windows environment
        # does not expose the shell API.
        return


def main() -> int:
    """Start the desktop shell and return Qt's exit status."""
    _set_windows_runtime_identity()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Planacity")
    app.setApplicationVersion(version("planacity"))
    app.setWindowIcon(image_icon("planacity-mark.png"))
    window = MainWindow()
    window.show()
    return app.exec()
