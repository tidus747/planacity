"""Load packaged image assets independently of the process working directory."""

from importlib.resources import files

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def image_pixmap(filename: str) -> QPixmap:
    """Load a packaged raster image without relying on the working directory."""
    data = files("planacity").joinpath("resources", "images", filename).read_bytes()
    pixmap = QPixmap()
    if not pixmap.loadFromData(data):
        raise ValueError(f"The packaged image {filename!r} is not valid.")
    return pixmap


def image_icon(filename: str) -> QIcon:
    """Create an application icon from a packaged raster image."""
    return QIcon(image_pixmap(filename))


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
    filename = "plan" if name == "Changes" else name.lower()
    return svg_icon(f"{filename}.svg", color)
