"""Appearance changes must preserve workspace state and survive reopening."""

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSplitter

from planacity.ui.main_window import MainWindow
from planacity.ui.theme import Theme


def test_theme_controls_preserve_workspace(app: QApplication, window: MainWindow) -> None:
    window.navigation["Plan"].click()
    app.processEvents()
    split = window.pages.currentWidget().findChild(QSplitter)
    assert split is not None
    split.setSizes([450, 350])
    sizes = split.sizes()

    QTest.mouseClick(window.theme_buttons[Theme.DARK], Qt.MouseButton.LeftButton)
    app.processEvents()
    assert window.theme == Theme.DARK
    assert window.theme_actions[Theme.DARK].isChecked()
    assert not window.theme_actions[Theme.LIGHT].isChecked()
    assert window.pages.currentIndex() == 1
    assert split.sizes() == sizes

    window.theme_actions[Theme.LIGHT].trigger()
    app.processEvents()
    assert window.theme == Theme.LIGHT
    assert window.theme_buttons[Theme.LIGHT].isChecked()
    assert not window.theme_buttons[Theme.DARK].isChecked()
    assert window.pages.currentIndex() == 1
    assert split.sizes() == sizes


@pytest.mark.parametrize("theme", list(Theme))
def test_theme_survives_reopen(
    app: QApplication, settings: QSettings, window: MainWindow, theme: Theme
) -> None:
    window.theme_buttons[theme].click()
    window.close()
    restored_settings = QSettings(settings.fileName(), QSettings.Format.IniFormat)
    assert restored_settings.value("appearance/theme") == theme.value
    restored = MainWindow(restored_settings)
    try:
        assert restored.theme == theme
        assert restored.theme_actions[theme].isChecked()
        assert restored.theme_buttons[theme].isChecked()
    finally:
        restored.close()
        restored.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("value", ["unknown-theme", 12])
def test_invalid_preference_falls_back_to_system(
    app: QApplication, settings: QSettings, value: object
) -> None:
    settings.setValue("appearance/theme", value)
    QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    window = MainWindow(settings)
    try:
        assert window.theme == Theme.LIGHT
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
