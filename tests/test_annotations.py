from PySide6.QtCore import QPoint

from luma.editor.annotations import Annotation


def annotation(kind, start, end, width=6.0, text=""):
    result = Annotation(kind, "#ff3b30", width, QPoint(*start), source=None)
    if end:
        result.extend(QPoint(*end))
    result.text = text
    return result


def test_bounds_cover_every_point_of_a_stroke_and_its_thickness():
    stroke = annotation("pen", (100, 100), (160, 140))
    stroke.extend(QPoint(90, 170))
    bounds = stroke.bounds()
    for point in stroke.points:
        assert bounds.contains(point)
    assert bounds.left() < 90 - stroke.width and bounds.bottom() > 170 + stroke.width


def test_a_marker_reserves_room_for_its_wider_stroke():
    pen = annotation("pen", (100, 100), (200, 100))
    marker = annotation("marker", (100, 100), (200, 100))
    assert marker.bounds().height() >= pen.bounds().height()


def test_text_bounds_grow_with_the_text():
    short = annotation("text", (50, 50), None, width=28.0, text="Hi")
    long = annotation("text", (50, 50), None, width=28.0, text="A much longer note")
    assert long.bounds().width() > short.bounds().width()
    assert short.bounds().contains(QPoint(50, 50))
