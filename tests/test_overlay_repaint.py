"""Partial repaints must leave exactly the pixels a full repaint would produce."""

import random

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QMouseEvent, QPainter, QPointingDevice, QRegion

from luma.capture.displays import Monitor, MonitorShot
from luma.editor.overlay import Overlay


class SessionStub:
    def claim(self, owner):
        pass

    def open_settings(self):
        pass

    def finish(self, owner, action):
        pass

    def cancel(self):
        pass


class LinesStub:
    def follow(self, point):
        pass

    def hide(self):
        pass

    def close(self):
        pass

    def raise_to_top(self):
        pass


@pytest.fixture
def overlay(qapp, isolated_preferences):
    screen = QGuiApplication.primaryScreen()
    size = screen.geometry().size()
    image = QImage(size, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    for x in range(0, size.width(), 40):
        painter.fillRect(x, 0, 40, size.height(), QColor.fromHsv((x * 7) % 360, 120, 200))
    painter.end()
    shot = MonitorShot(Monitor(QRect(0, 0, size.width(), size.height()), 0), image)
    widget = Overlay(shot, screen, SessionStub())
    widget.lines = LinesStub()
    widget.resize(size)
    return widget


def mouse_event(kind, position, button=Qt.LeftButton, buttons=Qt.LeftButton):
    point = QPointF(position)
    return QMouseEvent(
        kind, point, point, button, buttons, Qt.NoModifier, QPointingDevice.primaryPointingDevice()
    )


class Screen:
    """Mimics a window's backing store: starts as a full paint, then only dirty regions are updated."""

    def __init__(self, widget):
        self.widget = widget
        self.buffer = QImage(widget.size(), QImage.Format.Format_RGB32)
        self.dirty = QRegion()
        widget.invalidate = self.collect
        widget.update = lambda *args: self.collect_update(*args)
        self.track_toolbar(widget.toolbar)
        self.flush_all()

    def track_toolbar(self, toolbar):
        """Qt repaints what a child widget uncovers on its own; do the same for the stand-in screen."""
        hide, move, show = toolbar.hide, toolbar.move, toolbar.show

        def mark():
            if not toolbar.isHidden():
                self.dirty = self.dirty.united(toolbar.geometry())

        toolbar.hide = lambda: (mark(), hide(), mark())[1]
        toolbar.move = lambda *args: (mark(), move(*args), mark())[1]
        toolbar.show = lambda: (show(), mark())[0]

    def collect(self, *rects):
        for rect in rects:
            self.dirty = self.dirty.united(self.widget.widget_rect(rect))

    def collect_update(self, *args):
        self.dirty = self.dirty.united(QRegion(self.widget.rect()) if not args else QRegion(args[0]))

    def flush_all(self):
        self.widget.render(self.buffer)
        self.dirty = QRegion()

    def flush_dirty(self):
        self.widget.render(self.buffer, self.dirty.boundingRect().topLeft(), self.dirty)
        self.dirty = QRegion()

    def matches_full_repaint(self):
        expected = QImage(self.widget.size(), QImage.Format.Format_RGB32)
        self.widget.render(expected)
        return self.buffer == expected


def drag(screen, start, end, steps=12):
    widget = screen.widget
    widget.mousePressEvent(mouse_event(QEvent.MouseButtonPress, start))
    screen.flush_dirty()
    for step in range(1, steps + 1):
        position = QPoint(
            start.x() + (end.x() - start.x()) * step // steps,
            start.y() + (end.y() - start.y()) * step // steps,
        )
        widget.mouseMoveEvent(mouse_event(QEvent.MouseMove, position))
        screen.flush_dirty()
    widget.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, end, buttons=Qt.NoButton))
    screen.flush_dirty()


def test_partial_repaints_match_a_full_repaint_after_dragging_right_then_left(overlay):
    screen = Screen(overlay)
    drag(screen, QPoint(200, 200), QPoint(560, 420))
    assert screen.matches_full_repaint()
    drag(screen, QPoint(640, 380), QPoint(90, 140))
    assert screen.matches_full_repaint()


def test_partial_repaints_match_after_a_tiny_selection_grows_wide(overlay):
    screen = Screen(overlay)
    drag(screen, QPoint(300, 300), QPoint(310, 306), steps=3)
    drag(screen, QPoint(300, 300), QPoint(780, 330), steps=20)
    assert screen.matches_full_repaint()


def test_random_drags_and_drawings_never_leave_stale_pixels(overlay):
    screen = Screen(overlay)
    generator = random.Random(1)
    width, height = overlay.width(), overlay.height()
    tools = [None, None, "pen", "arrow", "marker", "box", "ellipse", "redact"]
    for _ in range(150):
        overlay.tool = generator.choice(tools)
        start = QPoint(generator.randrange(width), generator.randrange(height))
        if overlay.selection and generator.random() < 0.5:
            rect = overlay.selection
            start = generator.choice(
                [rect.topLeft(), rect.bottomRight(), rect.center(), QPoint(rect.left(), rect.center().y())]
            )
        overlay.mousePressEvent(mouse_event(QEvent.MouseButtonPress, start))
        screen.flush_dirty()
        position = QPoint(start)
        for _step in range(generator.randrange(1, 25)):
            position = QPoint(
                min(max(position.x() + generator.randrange(-90, 91), 0), width - 1),
                min(max(position.y() + generator.randrange(-60, 61), 0), height - 1),
            )
            overlay.mouseMoveEvent(mouse_event(QEvent.MouseMove, position))
            screen.flush_dirty()
            assert screen.matches_full_repaint(), f"stale pixels after moving to {position.toTuple()}"
        overlay.mouseReleaseEvent(mouse_event(QEvent.MouseButtonRelease, position, buttons=Qt.NoButton))
        screen.flush_dirty()
        assert screen.matches_full_repaint()
