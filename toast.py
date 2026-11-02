from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

THUMBNAIL_SIZE = (150, 96)
VISIBLE_MS = 1400
FADE_MS = 350
BOTTOM_MARGIN = 72

STYLE = """
#toast { background: rgba(28, 28, 30, 240); border: 1px solid rgba(255, 255, 255, 38);
         border-radius: 14px; }
#toast QLabel { color: white; font-size: 14px; font-weight: 600; }
"""


class Toast(QWidget):
    """Brief on-screen confirmation with a thumbnail of what was just captured."""

    def __init__(self, image, message):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        frame = QFrame(self)
        frame.setObjectName("toast")
        frame.setStyleSheet(STYLE)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 12, 18, 12)
        row.setSpacing(14)

        thumbnail = QLabel()
        thumbnail.setPixmap(
            QPixmap.fromImage(image).scaled(
                *THUMBNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        row.addWidget(thumbnail)
        row.addWidget(QLabel(message))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self.adjustSize()

        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(FADE_MS)
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)
        self.fade.setEasingCurve(QEasingCurve.InQuad)
        self.fade.finished.connect(self.close)

    def show_briefly(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(
            area.left() + (area.width() - self.width()) // 2,
            area.bottom() - self.height() - BOTTOM_MARGIN,
        )
        self.show()
        QTimer.singleShot(VISIBLE_MS, self.fade.start)
