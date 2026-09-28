"""Assets must load when the application is launched outside its source folder."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from planacity.ui.icons import image_icon, image_pixmap, navigation_icon


def test_packaged_icons_load_from_another_directory(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert not image_icon("planacity-mark.png").isNull()
    assert image_pixmap("planacity-mark.png").hasAlphaChannel()
    assert image_pixmap("planacity-wordmark.png").hasAlphaChannel()
    for name in ("Overview", "Plan", "People", "Import"):
        for color in ("#142033", "#e7eef7"):
            assert not navigation_icon(name, color).pixmap(24, 24).isNull()


def test_invalid_packaged_image_is_rejected(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = tmp_path / "resources" / "images" / "ignored.png"
    image.parent.mkdir(parents=True)
    image.write_text("not an image", encoding="utf-8")
    monkeypatch.setattr(
        "planacity.ui.icons.files",
        lambda package: tmp_path,
    )
    with pytest.raises(ValueError, match="not valid"):
        image_pixmap("ignored.png")
