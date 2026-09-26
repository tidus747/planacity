"""Run Qt smoke tests without opening desktop windows."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if TYPE_CHECKING:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from planacity.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app() -> Iterator[QApplication]:
    from PySide6.QtWidgets import QApplication

    application = QApplication([])
    application.setStyle("Fusion")
    yield application
    application.quit()


@pytest.fixture
def settings(tmp_path: Path) -> QSettings:
    from PySide6.QtCore import QSettings

    return QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def window(app: QApplication, settings: QSettings) -> Iterator[MainWindow]:
    from planacity.ui.main_window import MainWindow

    widget = MainWindow(settings)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()
