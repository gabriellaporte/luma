from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QMouseEvent, QPointingDevice

from luma.capture.displays import Monitor, MonitorShot
from luma.editor.overlay import Overlay


class SessionStub:
    def open_settings(self):
        pass


def hover_event(position):
    point = QPointF(position)
    return QMouseEvent(
        QEvent.MouseMove,
        point,
        point,
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
        QPointingDevice.primaryPointingDevice(),
    )


def build_overlay():
    screen = QGuiApplication.primaryScreen()
    size = screen.geometry().size()
    image = QImage(size, QImage.Format.Format_RGB32)
    image.fill(QColor("gray"))
    shot = MonitorShot(Monitor(QRect(0, 0, size.width(), size.height()), 0), image)
    return Overlay(shot, screen, SessionStub())


def test_a_mouse_move_that_arrives_after_closing_does_not_bring_the_crosshair_back(
    qapp, isolated_preferences
):
    overlay = build_overlay()
    overlay.show()
    overlay.mouseMoveEvent(hover_event(QPoint(100, 100)))
    assert overlay.lines.is_visible

    overlay.close()
    overlay.mouseMoveEvent(hover_event(QPoint(120, 120)))

    assert not overlay.lines.is_visible
