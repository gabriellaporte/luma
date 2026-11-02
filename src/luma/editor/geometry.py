import math

from PySide6.QtCore import (
    QPointF,
    QRectF,
)
from PySide6.QtGui import (
    QPolygonF,
)

SMOOTHING_WINDOW = 2
SMOOTHING_PASSES = 3
MIN_SNAP_POINTS = 8
MIN_SNAP_SIZE = 24
LINE_TOLERANCE = 0.06
CLOSED_SHAPE_RATIO = 0.3
SHAPE_TOLERANCE = 0.06


def arrow_polygon(start, end, width):
    dx, dy = end.x() - start.x(), end.y() - start.y()
    length = math.hypot(dx, dy)
    if length < 1:
        return None
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    head_length = min(width * 4 + 6, length)
    head_half = width * 2 + 3
    half = width / 2
    bx, by = end.x() - ux * head_length, end.y() - uy * head_length
    return QPolygonF(
        [
            QPointF(start.x() + nx * half, start.y() + ny * half),
            QPointF(bx + nx * half, by + ny * half),
            QPointF(bx + nx * head_half, by + ny * head_half),
            QPointF(end),
            QPointF(bx - nx * head_half, by - ny * head_half),
            QPointF(bx - nx * half, by - ny * half),
            QPointF(start.x() - nx * half, start.y() - ny * half),
        ]
    )


def smooth_points(points):
    """Moving average that keeps both endpoints, to take the tremor out of a hand-drawn stroke."""
    smoothed = list(points)
    if len(smoothed) < 3:
        return smoothed
    for _pass in range(SMOOTHING_PASSES):
        previous = list(smoothed)
        for index in range(1, len(previous) - 1):
            window = previous[max(0, index - SMOOTHING_WINDOW) : index + SMOOTHING_WINDOW + 1]
            smoothed[index] = QPointF(
                sum(p.x() for p in window) / len(window),
                sum(p.y() for p in window) / len(window),
            )
    return smoothed


def distance(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def recognize_shape(points, allow_closed):
    """The clean shape a rough stroke was meant to be, as (kind, points), or None."""
    if len(points) < MIN_SNAP_POINTS:
        return None
    xs, ys = [p.x() for p in points], [p.y() for p in points]
    bounds = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
    diagonal = math.hypot(bounds.width(), bounds.height())
    if diagonal < MIN_SNAP_SIZE:
        return None

    start, end = points[0], points[-1]
    chord = distance(start, end)
    if chord > diagonal * CLOSED_SHAPE_RATIO:
        return line_if_straight(points, chord)
    if not allow_closed:
        return None
    return closed_shape(points, bounds, diagonal)


def line_if_straight(points, chord):
    start, end = points[0], points[-1]
    dx, dy = end.x() - start.x(), end.y() - start.y()
    deviation = max(abs(dx * (p.y() - start.y()) - dy * (p.x() - start.x())) / chord for p in points)
    if deviation > chord * LINE_TOLERANCE:
        return None
    return ("line", [start, end])


def closed_shape(points, bounds, diagonal):
    center = bounds.center()
    radius_x, radius_y = bounds.width() / 2, bounds.height() / 2
    if radius_x < 1 or radius_y < 1:
        return None
    box_error = sum(
        min(
            abs(p.x() - bounds.left()),
            abs(p.x() - bounds.right()),
            abs(p.y() - bounds.top()),
            abs(p.y() - bounds.bottom()),
        )
        for p in points
    )
    oval_error = sum(
        abs(math.hypot((p.x() - center.x()) / radius_x, (p.y() - center.y()) / radius_y) - 1)
        * min(radius_x, radius_y)
        for p in points
    )
    kind, error = min(("box", box_error), ("ellipse", oval_error), key=lambda pair: pair[1])
    if error / len(points) > diagonal * SHAPE_TOLERANCE:
        return None
    return (kind, [bounds.topLeft(), bounds.bottomRight()])
