from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPixmap

ARM_LENGTH = 40
CENTER_GAP = 6
HALO = QColor(0, 0, 0, 170)
LINE = QColor(255, 255, 255, 235)


def crosshair_cursor():
    """A large crosshair drawn by the system cursor, so it follows the mouse with no frame delay."""
    side = ARM_LENGTH * 2 + 1
    center = ARM_LENGTH
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    for color, thickness in ((HALO, 3), (LINE, 1)):
        offset = thickness // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRect(center - ARM_LENGTH, center - offset, ARM_LENGTH - CENTER_GAP, thickness)
        painter.drawRect(center + CENTER_GAP + 1, center - offset, ARM_LENGTH - CENTER_GAP, thickness)
        painter.drawRect(center - offset, center - ARM_LENGTH, thickness, ARM_LENGTH - CENTER_GAP)
        painter.drawRect(center - offset, center + CENTER_GAP + 1, thickness, ARM_LENGTH - CENTER_GAP)
    painter.setBrush(HALO)
    painter.drawRect(center - 1, center - 1, 3, 3)
    painter.setBrush(LINE)
    painter.drawRect(center, center, 1, 1)
    painter.end()
    return QCursor(pixmap, center, center)
