"""Small, theme-aware navigation icons rendered by Qt without external assets."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "Overview": '<path d="M3 10 12 3l9 7v11h-6v-7H9v7H3Z"/>',
    "Plan": '<rect x="4" y="3" width="16" height="18" rx="2"/>'
    '<path d="M8 8h1m3 0h5M8 12h1m3 0h5M8 16h1m3 0h5"/>',
    "People": '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3'
    'm1-17a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v3"/>',
    "Import": '<path d="M12 16V3m-5 5 5-5 5 5M4 14v7h16v-7"/>',
}


def navigation_icon(name: str, color: str) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)
