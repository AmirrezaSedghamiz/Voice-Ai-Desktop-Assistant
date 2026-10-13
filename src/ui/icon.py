"""
Application Icon Generator and Manager:
Renders a modern, high-resolution vector-style icon for David.
Exports both PNG and multi-resolution ICO for Windows desktop integration and PyInstaller.
"""

import struct
from pathlib import Path
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_PNG_PATH = ASSETS_DIR / "david_icon.png"
ICON_ICO_PATH = ASSETS_DIR / "david_icon.ico"


def create_david_pixmap(size: int = 256) -> QPixmap:
    """Renders a polished modern application icon onto a QPixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Outer rounded badge with subtle deep blue / purple gradient
    margin = size * 0.06
    rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    corner_radius = size * 0.22

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor(24, 28, 44))
    grad.setColorAt(0.5, QColor(16, 20, 34))
    grad.setColorAt(1.0, QColor(10, 12, 22))

    path = QPainterPath()
    path.addRoundedRect(rect, corner_radius, corner_radius)

    painter.fillPath(path, QBrush(grad))

    # Outer border: subtle glowing cyan/indigo border
    pen = QPen(QColor(66, 133, 244, 180))
    pen.setWidthF(max(1.5, size * 0.015))
    painter.setPen(pen)
    painter.drawPath(path)

    # Stylized wave monogram in center
    cx = size / 2.0
    cy = size / 2.0

    # Draw soundwave arcs in vibrant colors
    accent_pen = QPen(QColor(76, 201, 240))
    accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

    # Left mic bar / wave bar 1
    accent_pen.setWidthF(max(1.0, size * 0.05))
    painter.setPen(accent_pen)
    painter.drawLine(QPointF(cx - size * 0.16, cy - size * 0.10), QPointF(cx - size * 0.16, cy + size * 0.10))

    # Center tall wave bar
    accent_pen.setColor(QColor(67, 97, 238))
    painter.setPen(accent_pen)
    painter.drawLine(QPointF(cx - size * 0.05, cy - size * 0.22), QPointF(cx - size * 0.05, cy + size * 0.22))

    # Center-right wave bar
    accent_pen.setColor(QColor(114, 9, 183))
    painter.setPen(accent_pen)
    painter.drawLine(QPointF(cx + size * 0.06, cy - size * 0.15), QPointF(cx + size * 0.06, cy + size * 0.15))

    # Outer wave bar
    accent_pen.setColor(QColor(247, 37, 133))
    painter.setPen(accent_pen)
    painter.drawLine(QPointF(cx + size * 0.17, cy - size * 0.08), QPointF(cx + size * 0.17, cy + size * 0.08))

    painter.end()
    return pixmap


def _pixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    return bytes(ba.data())


def ensure_icon_files() -> Path:
    """Ensures icon PNG and multi-resolution ICO files exist on disk."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    pm256 = create_david_pixmap(256)
    if not ICON_PNG_PATH.exists():
        pm256.save(str(ICON_PNG_PATH), "PNG")

    if not ICON_ICO_PATH.exists():
        sizes = [16, 32, 48, 64, 128, 256]
        images_data = []
        for sz in sizes:
            pm = create_david_pixmap(sz)
            images_data.append((sz, _pixmap_to_png_bytes(pm)))

        # Header: Reserved(2), Type(2, 1=icon), Count(2)
        count = len(images_data)
        header = struct.pack("<HHH", 0, 1, count)
        dir_entries = []
        offset = 6 + count * 16

        for sz, png_bytes in images_data:
            w = 0 if sz >= 256 else sz
            h = 0 if sz >= 256 else sz
            dir_entries.append(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png_bytes), offset))
            offset += len(png_bytes)

        ico_bytes = header + b"".join(dir_entries) + b"".join(data for _, data in images_data)
        ICON_ICO_PATH.write_bytes(ico_bytes)

    return ICON_PNG_PATH


def get_app_icon() -> QIcon:
    """Returns a QIcon containing multiple resolutions."""
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(create_david_pixmap(sz))
    return icon
