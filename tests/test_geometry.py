import math
import random

from PySide6.QtCore import QPointF

from luma.editor.geometry import arrow_polygon, recognize_shape, smooth_points


def noisy(coordinates, amount=2.0):
    generator = random.Random(7)
    return [
        QPointF(x + generator.uniform(-amount, amount), y + generator.uniform(-amount, amount))
        for x, y in coordinates
    ]


def test_wobbly_line_snaps_to_a_straight_line():
    stroke = noisy([(100 + step * 4, 100 + step * 1.2) for step in range(60)])
    kind, points = recognize_shape(stroke, allow_closed=True)
    assert kind == "line"
    assert points == [stroke[0], stroke[-1]]


def test_rough_circle_snaps_to_an_ellipse():
    stroke = noisy(
        [(300 + 120 * math.cos(t / 40 * math.tau), 200 + 80 * math.sin(t / 40 * math.tau)) for t in range(41)]
    )
    kind, _points = recognize_shape(stroke, allow_closed=True)
    assert kind == "ellipse"


def test_rough_rectangle_snaps_to_a_box():
    outline = (
        [(100 + step * 10, 350) for step in range(20)]
        + [(300, 350 + step * 10) for step in range(12)]
        + [(300 - step * 10, 470) for step in range(20)]
        + [(100, 470 - step * 10) for step in range(12)]
    )
    kind, _points = recognize_shape(noisy(outline), allow_closed=True)
    assert kind == "box"


def test_closed_shapes_are_ignored_when_not_allowed():
    stroke = noisy(
        [
            (300 + 100 * math.cos(t / 40 * math.tau), 200 + 100 * math.sin(t / 40 * math.tau))
            for t in range(41)
        ]
    )
    assert recognize_shape(stroke, allow_closed=False) is None


def test_a_squiggle_is_left_alone():
    stroke = [QPointF(500 + step * 3, 200 + 60 * math.sin(step / 6)) for step in range(60)]
    assert recognize_shape(stroke, allow_closed=True) is None


def test_tiny_strokes_are_ignored():
    assert recognize_shape([QPointF(i, i) for i in range(4)], allow_closed=True) is None


def test_smoothing_keeps_endpoints_and_reduces_jitter():
    stroke = noisy([(step * 5, 100) for step in range(40)], amount=4.0)
    smoothed = smooth_points(stroke)
    assert smoothed[0] == stroke[0] and smoothed[-1] == stroke[-1]
    assert max(p.y() for p in smoothed) - min(p.y() for p in smoothed) < max(p.y() for p in stroke) - min(
        p.y() for p in stroke
    )


def test_arrow_polygon_ends_at_the_tip_and_rejects_zero_length():
    start, end = QPointF(0, 0), QPointF(100, 0)
    polygon = arrow_polygon(start, end, 6)
    assert QPointF(100, 0) in list(polygon)
    assert arrow_polygon(start, start, 6) is None
