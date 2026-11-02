from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from luma.system.keyboard import user32

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_ASYNCWINDOWPOS = 0x4000
LINE_OPACITY = 0.45
LINE_FLAGS = (
    Qt.Tool
    | Qt.FramelessWindowHint
    | Qt.WindowStaysOnTopHint
    | Qt.WindowTransparentForInput
    | Qt.WindowDoesNotAcceptFocus
)


class CrosshairLines:
    """A full-screen crosshair made of two thin windows that the system moves.

    Repainting a line inside the overlay always trails the system cursor by a few frames. A window
    moved with SetWindowPos is composed by the desktop in the same pass as the cursor, so it keeps up.
    """

    def __init__(self, monitor_rect, ratio):
        self.origin = monitor_rect.topLeft()
        self.size = monitor_rect.size()
        self.thickness = max(1, round(ratio))
        self.horizontal = None
        self.vertical = None

    def rects_for(self, point):
        """Screen rectangles (physical pixels) of the horizontal and vertical line through point."""
        half = self.thickness // 2
        horizontal = QRect(
            self.origin.x(), self.origin.y() + point.y() - half, self.size.width(), self.thickness
        )
        vertical = QRect(
            self.origin.x() + point.x() - half, self.origin.y(), self.thickness, self.size.height()
        )
        return horizontal, vertical

    @property
    def is_visible(self):
        return self.horizontal is not None and self.horizontal.isVisible()

    def follow(self, point):
        horizontal, vertical = self.rects_for(point)
        if not self.is_visible:
            self.show_lines(horizontal, vertical)
            return
        for line, rect in ((self.horizontal, horizontal), (self.vertical, vertical)):
            user32.SetWindowPos(
                int(line.winId()),
                0,
                rect.x(),
                rect.y(),
                0,
                0,
                SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS,
            )

    def show_lines(self, horizontal, vertical):
        if self.horizontal is None:
            self.horizontal, self.vertical = self.build_line(), self.build_line()
        for line, rect in ((self.horizontal, horizontal), (self.vertical, vertical)):
            line.show()
            user32.SetWindowPos(
                int(line.winId()),
                HWND_TOPMOST,
                rect.x(),
                rect.y(),
                rect.width(),
                rect.height(),
                SWP_NOACTIVATE,
            )

    def build_line(self):
        line = QWidget(None, LINE_FLAGS)
        line.setAttribute(Qt.WA_ShowWithoutActivating)
        line.setAutoFillBackground(True)
        palette = line.palette()
        palette.setColor(QPalette.Window, QColor("white"))
        line.setPalette(palette)
        line.setWindowOpacity(LINE_OPACITY)
        return line

    def raise_to_top(self):
        if not self.is_visible:
            return
        for line in (self.horizontal, self.vertical):
            user32.SetWindowPos(
                int(line.winId()), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )

    def hide(self):
        if self.horizontal is not None:
            self.horizontal.hide()
            self.vertical.hide()

    def close(self):
        if self.horizontal is not None:
            self.horizontal.close()
            self.vertical.close()
