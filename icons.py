import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

GRID = 24
RENDER_SCALE = 4
STROKE = 1.8
WHITE = QColor("white")


def render_icon(size, draw):
    """Draws on a 24x24 grid at 4x resolution so the icon stays sharp at any display scale."""
    side = size * RENDER_SCALE
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(side / GRID, side / GRID)
    draw(painter)
    painter.end()
    pixmap.setDevicePixelRatio(RENDER_SCALE)
    return QIcon(pixmap)


def outline(painter, width=STROKE, color=WHITE):
    painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)


def points(*coordinates):
    return [QPointF(x, y) for x, y in coordinates]


def draw_pen(painter):
    outline(painter)
    painter.drawPolygon(QPolygonF(points((4, 20), (5.2, 15.2), (15.5, 4.9), (19.1, 8.5), (8.8, 18.8))))
    painter.drawLine(QPointF(13.3, 7.1), QPointF(16.9, 10.7))


def draw_arrow(painter):
    outline(painter)
    painter.drawLine(QPointF(6, 18), QPointF(18, 6))
    painter.drawPolyline(points((10, 6), (18, 6), (18, 14)))


def draw_marker(painter):
    outline(painter)
    painter.drawPolygon(QPolygonF(points((14.5, 3.5), (20, 9), (11.5, 17.5), (6, 12))))
    painter.drawLine(QPointF(6, 12), QPointF(4, 17))
    painter.drawLine(QPointF(4, 17), QPointF(9, 15))
    highlight = QColor(255, 255, 255, 120)
    outline(painter, 3.2, highlight)
    painter.drawLine(QPointF(11, 21), QPointF(20, 21))


def draw_box(painter):
    outline(painter)
    painter.drawRoundedRect(QRectF(4.5, 6.5, 15, 11), 2, 2)


def draw_ellipse(painter):
    outline(painter)
    painter.drawEllipse(QPointF(12, 12), 7.5, 7.5)


def draw_text(painter):
    outline(painter, 2.0)
    painter.drawLine(QPointF(6, 6.5), QPointF(18, 6.5))
    painter.drawLine(QPointF(12, 6.5), QPointF(12, 18.5))
    painter.drawLine(QPointF(9, 18.5), QPointF(15, 18.5))


def draw_redact(painter):
    painter.setPen(Qt.NoPen)
    for row in range(3):
        for column in range(3):
            shade = QColor(255, 255, 255, 235 if (row + column) % 2 == 0 else 95)
            painter.setBrush(shade)
            painter.drawRoundedRect(QRectF(5 + column * 5, 5 + row * 5, 4.4, 4.4), 0.8, 0.8)


def draw_undo(painter):
    outline(painter)
    painter.drawPolyline(points((9, 5.5), (5, 9.5), (9, 13.5)))
    path = QPainterPath(QPointF(5, 9.5))
    path.lineTo(14, 9.5)
    path.arcTo(QRectF(9, 9.5, 10, 10), 90, -180)
    path.lineTo(9, 19.5)
    painter.drawPath(path)


def draw_save(painter):
    outline(painter)
    painter.drawLine(QPointF(12, 4.5), QPointF(12, 14.5))
    painter.drawPolyline(points((8, 10.5), (12, 14.5), (16, 10.5)))
    painter.drawPolyline(points((5, 15), (5, 19.5), (19, 19.5), (19, 15)))


def draw_copy(painter):
    outline(painter)
    painter.drawRoundedRect(QRectF(9, 9, 10.5, 10.5), 2, 2)
    painter.drawPolyline(points((15.5, 9), (15.5, 5), (5, 5), (5, 15.5), (9, 15.5)))


def draw_close(painter):
    outline(painter, 2.0)
    painter.drawLine(QPointF(7, 7), QPointF(17, 17))
    painter.drawLine(QPointF(17, 7), QPointF(7, 17))


def draw_gear(painter):
    teeth, outer, inner = 8, 10.2, 7.6
    outline_points = []
    for tooth in range(teeth):
        base = tooth * 360 / teeth
        for angle, radius in [(-13, inner), (-8, outer), (8, outer), (13, inner)]:
            radians = math.radians(base + angle - 90)
            outline_points.append(QPointF(12 + radius * math.cos(radians), 12 + radius * math.sin(radians)))
    path = QPainterPath()
    path.setFillRule(Qt.OddEvenFill)
    path.addPolygon(QPolygonF(outline_points))
    path.closeSubpath()
    path.addEllipse(QPointF(12, 12), 3.4, 3.4)
    painter.setPen(Qt.NoPen)
    painter.setBrush(WHITE)
    painter.drawPath(path)


GLYPHS = {
    "pen": draw_pen,
    "arrow": draw_arrow,
    "marker": draw_marker,
    "box": draw_box,
    "ellipse": draw_ellipse,
    "text": draw_text,
    "redact": draw_redact,
    "undo": draw_undo,
    "save": draw_save,
    "copy": draw_copy,
    "close": draw_close,
    "gear": draw_gear,
}


def glyph_icon(name, size):
    return render_icon(size, GLYPHS[name])


def swatch_icon(color, size):
    def draw(painter):
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(12, 12), 8, 8)

    return render_icon(size, draw)


def thickness_icon(stroke_size, size):
    def draw(painter):
        outline(painter, stroke_size * 0.55)
        painter.drawLine(QPointF(5, 12), QPointF(19, 12))

    return render_icon(size, draw)
