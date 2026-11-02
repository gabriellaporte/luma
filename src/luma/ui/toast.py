from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

THUMBNAIL_SIZE = 40
THUMBNAIL_RADIUS = 8
SHADOW_MARGIN = 18
BOTTOM_MARGIN = 56
SLIDE_PIXELS = 10
FADE_IN_MS = 180
VISIBLE_MS = 1700
FADE_OUT_MS = 320

STYLE = """
#toast { background: rgba(36, 36, 40, 238); border: 1px solid rgba(255, 255, 255, 26);
         border-radius: 14px; }
#title { color: #f5f5f7; font-size: 13px; font-weight: 600; }
#detail { color: #9a9aa2; font-size: 11px; }
"""


def rounded_thumbnail(image, ratio):
    """A square, center-cropped preview with rounded corners, sharp at any display scale."""
    side = round(THUMBNAIL_SIZE * ratio)
    scaled = QPixmap.fromImage(image).scaled(
        side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    square = scaled.copy((scaled.width() - side) // 2, (scaled.height() - side) // 2, side, side)
    result = QPixmap(side, side)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, side, side, THUMBNAIL_RADIUS * ratio, THUMBNAIL_RADIUS * ratio)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, square)
    painter.end()
    result.setDevicePixelRatio(ratio)
    return result


class Toast(QWidget):
    """A slim, short-lived confirmation with a small preview of what was just captured."""

    def __init__(self, image, title, detail=""):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        frame = QFrame()
        frame.setObjectName("toast")
        frame.setStyleSheet(STYLE)
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 110))
        frame.setGraphicsEffect(shadow)

        thumbnail = QLabel()
        thumbnail.setPixmap(rounded_thumbnail(image, QGuiApplication.primaryScreen().devicePixelRatio()))
        thumbnail.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

        text = QVBoxLayout()
        text.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("title")
        text.addWidget(title_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setObjectName("detail")
            text.addWidget(detail_label)

        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 8, 18, 8)
        row.setSpacing(12)
        row.addWidget(thumbnail)
        row.addLayout(text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
        outer.addWidget(frame)
        self.adjustSize()
        self.animation = None

    def show_briefly(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        target = QPoint(
            area.left() + (area.width() - self.width()) // 2,
            area.bottom() - self.height() - BOTTOM_MARGIN,
        )
        start = target + QPoint(0, SLIDE_PIXELS)
        self.setWindowOpacity(0.0)
        self.move(start)
        self.show()

        appear = QParallelAnimationGroup()
        appear.addAnimation(self.property_animation(b"windowOpacity", 0.0, 1.0, FADE_IN_MS))
        appear.addAnimation(self.property_animation(b"pos", start, target, FADE_IN_MS))
        self.animation = QSequentialAnimationGroup(self)
        self.animation.addAnimation(appear)
        self.animation.addPause(VISIBLE_MS)
        self.animation.addAnimation(self.property_animation(b"windowOpacity", 1.0, 0.0, FADE_OUT_MS))
        self.animation.finished.connect(self.close)
        self.animation.start()

    def property_animation(self, name, start, end, duration):
        animation = QPropertyAnimation(self, name)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        return animation
