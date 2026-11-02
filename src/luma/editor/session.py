import logging

from PySide6.QtCore import (
    QObject,
    Signal,
)
from PySide6.QtGui import (
    QCursor,
    QGuiApplication,
)

from luma.editor.overlay import Overlay

log = logging.getLogger("luma")


class CaptureSession(QObject):
    finished = Signal(object, str)
    color_picked = Signal(object)
    settings_requested = Signal()
    cancelled = Signal()

    def __init__(self, shots):
        super().__init__()
        self.overlays = [Overlay(shot, self.screen_for(shot), self) for shot in shots]

    @staticmethod
    def screen_for(shot):
        size = (shot.image.width(), shot.image.height())
        for screen in QGuiApplication.screens():
            geometry = screen.geometry()
            ratio = screen.devicePixelRatio()
            if (round(geometry.width() * ratio), round(geometry.height() * ratio)) == size:
                return screen
        raise RuntimeError(f"No Qt screen matches captured monitor {size}")

    def show(self):
        for overlay in self.overlays:
            overlay.show()
        cursor = QCursor.pos()
        under_cursor = next((o for o in self.overlays if o.geometry().contains(cursor)), self.overlays[0])
        under_cursor.activate()

    def open_settings(self):
        self.settings_requested.emit()

    def refocus(self):
        cursor = QCursor.pos()
        target = next((o for o in self.overlays if o.geometry().contains(cursor)), self.overlays[0])
        target.refocus()

    def claim(self, owner):
        for overlay in self.overlays:
            if overlay is not owner:
                overlay.clear_selection()

    def finish(self, owner, action):
        image = owner.render_selection()
        self.close_overlays()
        self.finished.emit(image, action)

    def pick_color(self, color):
        self.close_overlays()
        self.color_picked.emit(color)

    def cancel(self):
        self.close_overlays()
        self.cancelled.emit()

    def close_overlays(self):
        for overlay in self.overlays:
            if overlay.stats.has_data():
                log.info(
                    "overlay %dx%d: %s",
                    overlay.bounds.width(),
                    overlay.bounds.height(),
                    overlay.stats.summary(),
                )
            overlay.close()
            overlay.deleteLater()
