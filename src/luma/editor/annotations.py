from PySide6.QtCore import (
    QPointF,
    QRectF,
    QSizeF,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)

from luma.editor.geometry import arrow_polygon, recognize_shape, smooth_points

REDACT_BLOCK_FACTOR = 2.5
TEXT_FLAGS = (
    Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignTop.value | Qt.TextFlag.TextDontClip.value
)
TEXT_SHADOW = QColor(0, 0, 0, 150)
MARKER_WIDTH_FACTOR = 4
MARKER_ALPHA = 110


class Annotation:
    def __init__(self, kind, color, width, start, source):
        self.kind = kind
        self.color = QColor(color)
        self.width = width
        self.points = [QPointF(start)]
        self.source = source
        self.text = ""
        self.is_editing = False
        self.is_snapped = False

    def finish_stroke(self):
        if not self.is_snapped:
            self.points = smooth_points(self.points)

    def snap_to_shape(self):
        shape = recognize_shape(self.points, allow_closed=self.kind == "pen")
        if shape is None:
            return False
        shape_kind, self.points = shape
        if shape_kind != "line":
            self.kind = shape_kind
        self.is_snapped = True
        return True

    def extend(self, point):
        if self.kind in ("pen", "marker"):
            self.points.append(QPointF(point))
        else:
            self.points = [self.points[0], QPointF(point)]

    def paint(self, painter):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        getattr(self, f"paint_{self.kind}")(painter)
        painter.restore()

    def paint_arrow(self, painter):
        polygon = arrow_polygon(self.points[0], self.points[-1], self.width)
        if polygon is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.color)
            painter.drawPolygon(polygon)

    def paint_box(self, painter):
        painter.setPen(QPen(self.color, self.width, Qt.SolidLine, Qt.SquareCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(self.points[0], self.points[-1]).normalized())

    def paint_ellipse(self, painter):
        painter.setPen(QPen(self.color, self.width))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(self.points[0], self.points[-1]).normalized())

    def paint_pen(self, painter):
        self.paint_stroke(painter, self.color, self.width)

    def paint_marker(self, painter):
        color = QColor(self.color)
        color.setAlpha(MARKER_ALPHA)
        self.paint_stroke(painter, color, self.width * MARKER_WIDTH_FACTOR)

    def paint_stroke(self, painter, color, width):
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(self.points[0])
        for current, following in zip(self.points[1:-1], self.points[2:], strict=True):
            path.quadTo(current, (current + following) / 2)
        path.lineTo(self.points[-1])
        painter.drawPath(path)
        if len(self.points) == 1:
            painter.drawPoint(self.points[0])

    def paint_redact(self, painter):
        rect = QRectF(self.points[0], self.points[-1]).normalized().toAlignedRect()
        rect = rect.intersected(self.source.rect())
        if rect.isEmpty():
            return
        block = max(2, round(self.width * REDACT_BLOCK_FACTOR))
        small = self.source.copy(rect).scaled(
            max(1, rect.width() // block),
            max(1, rect.height() // block),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        painter.drawImage(
            rect.topLeft(), small.scaled(rect.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
        )

    def paint_text(self, painter):
        font = QFont()
        font.setPixelSize(round(self.width))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        origin = self.points[0]
        box = QRectF(origin, QSizeF(metrics.horizontalAdvance(self.text) + 4, metrics.height()))
        shadow_offset = max(1.0, self.width / 18)
        painter.setPen(TEXT_SHADOW)
        painter.drawText(box.translated(shadow_offset, shadow_offset), TEXT_FLAGS, self.text)
        painter.setPen(self.color)
        painter.drawText(box, TEXT_FLAGS, self.text)
        if self.is_editing:
            caret_x = box.left() + metrics.horizontalAdvance(self.text) + 2
            painter.setPen(QPen(self.color, max(1.0, self.width / 14)))
            painter.drawLine(QPointF(caret_x, box.top()), QPointF(caret_x, box.bottom()))
