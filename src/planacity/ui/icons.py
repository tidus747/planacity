"""Load packaged SVG assets independently of the process working directory."""

from importlib.resources import files

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def svg_icon(filename: str, color: str | None = None) -> QIcon:
    data = files("planacity").joinpath("resources", "icons", filename).read_bytes()
    if color is not None:
        data = data.replace(b"currentColor", color.encode("ascii"))
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        raise ValueError(f"The packaged icon {filename!r} is not a valid SVG.")
    icon = QIcon()
    for size in (24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def navigation_icon(name: str, color: str) -> QIcon:
    return svg_icon(f"{name.lower()}.svg", color)
