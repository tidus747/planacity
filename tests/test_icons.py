"""Assets must load when the application is launched outside its source folder."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from planacity.ui.icons import navigation_icon, svg_icon


def test_packaged_icons_load_from_another_directory(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert not svg_icon("app.svg").isNull()
    for name in ("Overview", "Plan", "People", "Import"):
        for color in ("#142033", "#e7eef7"):
            assert not navigation_icon(name, color).pixmap(24, 24).isNull()
