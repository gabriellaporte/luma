from PySide6.QtCore import QPoint, QRect

from luma.editor.crosshair import CrosshairLines


def test_lines_cross_exactly_at_the_cursor_on_a_monitor_with_an_offset():
    monitor = QRect(-1080, -304, 1080, 1920)
    lines = CrosshairLines(monitor, ratio=1.0)
    horizontal, vertical = lines.rects_for(QPoint(300, 500))
    assert horizontal == QRect(-1080, -304 + 500, 1080, 1)
    assert vertical == QRect(-1080 + 300, -304, 1, 1920)


def test_thickness_follows_the_display_scale_and_stays_centered():
    lines = CrosshairLines(QRect(0, 0, 2560, 1600), ratio=2.0)
    horizontal, vertical = lines.rects_for(QPoint(1000, 800))
    assert horizontal.height() == vertical.width() == 2
    assert horizontal.center().y() in (800, 799) and vertical.center().x() in (1000, 999)
    assert horizontal.width() == 2560 and vertical.height() == 1600


def test_nothing_is_created_until_the_lines_are_shown():
    lines = CrosshairLines(QRect(0, 0, 100, 100), ratio=1.0)
    assert lines.horizontal is None and not lines.is_visible
