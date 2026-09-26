"""Run Qt smoke tests without opening desktop windows."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from planacity.ui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="session")
def app() -> Iterator[QApplication]:
    application = QApplication([])
    application.setStyle("Fusion")
    yield application
    application.quit()


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def window(app: QApplication, settings: QSettings) -> Iterator[MainWindow]:
    widget = MainWindow(settings)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()
