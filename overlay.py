import ctypes
import math
from ctypes import wintypes

from PySide6.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QSizeF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QMenu, QToolButton, QWidget

from icons import glyph_icon, swatch_icon, thickness_icon
from preferences import preferences
from saving import open_save_folder
from theme import MENU_STYLE

PALETTE = ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#ffffff", "#1c1c1e"]
STROKE_SIZES = [3, 6, 10]
TEXT_PIXELS = {3: 18, 6: 28, 10: 44}
REDACT_BLOCK_FACTOR = 2.5
TEXT_FLAGS = (
    Qt.AlignmentFlag.AlignLeft.value
    | Qt.AlignmentFlag.AlignTop.value
    | Qt.TextFlag.TextDontClip.value
)
TEXT_SHADOW = QColor(0, 0, 0, 150)
LOUPE_PIXELS = 15
LOUPE_CELL = 9
LOUPE_OFFSET = 26
CROSSHAIR_COLOR = QColor(255, 255, 255, 90)
HINT_TEXT = (
    "Drag to select   |   Double-click: whole screen   |   "
    "Hold Ctrl: magnifier, Ctrl+C: copy color   |   Right-click: menu   |   Esc: cancel"
)
SNAP_HOLD_MS = 450
SMOOTHING_WINDOW = 2
SMOOTHING_PASSES = 3
MIN_SNAP_POINTS = 8
MIN_SNAP_SIZE = 24
LINE_TOLERANCE = 0.06
CLOSED_SHAPE_RATIO = 0.3
SHAPE_TOLERANCE = 0.06
VK_CONTROL = 0x11
KEY_DOWN_MASK = 0x8000
HINT_TOP = 56
NUDGE_PIXELS = 1
NUDGE_PIXELS_FAST = 10
TOOLS = [
    ("pen", "Pen", Qt.Key_P),
    ("arrow", "Arrow", Qt.Key_A),
    ("marker", "Marker", Qt.Key_M),
    ("box", "Box", Qt.Key_B),
    ("ellipse", "Ellipse", Qt.Key_O),
    ("text", "Text", Qt.Key_T),
    ("redact", "Redact", Qt.Key_R),
]
MARKER_WIDTH_FACTOR = 4
MARKER_ALPHA = 110
SETTINGS_BUTTON_MARGIN = 20
SETTINGS_BUTTON_STYLE = """
QToolButton { background: rgba(28, 28, 30, 235); color: white; border: 1px solid rgba(255, 255, 255, 38);
              border-radius: 10px; padding: 6px 12px; font-size: 12px; }
QToolButton:hover { background: rgba(58, 58, 60, 240); }
"""
ACCENT = QColor("#0a84ff")
HANDLE_SIZE = 9
HANDLE_HIT_MARGIN = 8
MIN_SELECTION_SIZE = 4
TOOLBAR_GAP = 8
LABEL_PADDING = 6
LABEL_FONT_PIXELS = 12
ICON_SIZE = 22
SWATCH_ICON_SIZE = 24
SETTINGS_ICON_SIZE = 18

TOOLBAR_STYLE = """
#toolbar { background: rgba(32, 32, 36, 244); border: 1px solid rgba(255, 255, 255, 30);
           border-radius: 14px; }
#toolbar QToolButton { color: #f5f5f7; border: none; border-radius: 9px; padding: 6px;
                       font-size: 12px; font-weight: 600; }
#toolbar QToolButton:hover { background: rgba(255, 255, 255, 30); }
#toolbar QToolButton:checked { background: rgba(10, 132, 255, 230); }
#toolbar QToolButton#swatch { border: 2px solid transparent; border-radius: 15px; padding: 3px; }
#toolbar QToolButton#swatch:hover { background: transparent; border-color: rgba(255, 255, 255, 90); }
#toolbar QToolButton#swatch:checked { background: transparent; border-color: white; }
#toolbar QToolButton#primary { background: #0a84ff; padding: 6px 14px 6px 10px; }
#toolbar QToolButton#primary:hover { background: #3b9bff; }
#toolbar QFrame#separator { background: rgba(255, 255, 255, 40); max-width: 1px; min-width: 1px; }
"""

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
TOOL_HINTS = {
    "pen": "hold still at the end of a stroke to snap it to a line, oval or box",
    "marker": "hold still at the end of a stroke to straighten it",
}
KEYEVENTF_KEYUP = 0x0002
VK_MENU = 0x12

FREEHAND_TOOLS = ("pen", "marker")

ARROW_KEY_DIRECTIONS = {
    Qt.Key_Left: QPoint(-1, 0),
    Qt.Key_Right: QPoint(1, 0),
    Qt.Key_Up: QPoint(0, -1),
    Qt.Key_Down: QPoint(0, 1),
}

CURSOR_BY_EDGES = {
    "l": Qt.SizeHorCursor,
    "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor,
    "b": Qt.SizeVerCursor,
    "lt": Qt.SizeFDiagCursor,
    "rb": Qt.SizeFDiagCursor,
    "rt": Qt.SizeBDiagCursor,
    "lb": Qt.SizeBDiagCursor,
}


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


class Annotation:
    def __init__(self, kind, color, width, start, source):
        self.kind = kind
        self.color = QColor(color)
        self.width = width
        self.points = [QPointF(start)]
        self.source = source
        self.text = ""
        self.is_editing = False
        self.is_snapped = False

    def finish_stroke(self):
        if not self.is_snapped:
            self.points = smooth_points(self.points)

    def snap_to_shape(self):
        shape = recognize_shape(self.points, allow_closed=self.kind == "pen")
        if shape is None:
            return False
        shape_kind, self.points = shape
        if shape_kind != "line":
            self.kind = shape_kind
        self.is_snapped = True
        return True

    def extend(self, point):
        if self.kind in ("pen", "marker"):
            self.points.append(QPointF(point))
        else:
            self.points = [self.points[0], QPointF(point)]

    def paint(self, painter):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        getattr(self, f"paint_{self.kind}")(painter)
        painter.restore()

    def paint_arrow(self, painter):
        polygon = arrow_polygon(self.points[0], self.points[-1], self.width)
        if polygon is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.color)
            painter.drawPolygon(polygon)

    def paint_box(self, painter):
        painter.setPen(QPen(self.color, self.width, Qt.SolidLine, Qt.SquareCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(self.points[0], self.points[-1]).normalized())

    def paint_ellipse(self, painter):
        painter.setPen(QPen(self.color, self.width))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(self.points[0], self.points[-1]).normalized())

    def paint_pen(self, painter):
        self.paint_stroke(painter, self.color, self.width)

    def paint_marker(self, painter):
        color = QColor(self.color)
        color.setAlpha(MARKER_ALPHA)
        self.paint_stroke(painter, color, self.width * MARKER_WIDTH_FACTOR)

    def paint_stroke(self, painter, color, width):
        painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(self.points[0])
        for current, following in zip(self.points[1:-1], self.points[2:]):
            path.quadTo(current, (current + following) / 2)
        path.lineTo(self.points[-1])
        painter.drawPath(path)
        if len(self.points) == 1:
            painter.drawPoint(self.points[0])

    def paint_redact(self, painter):
        rect = QRectF(self.points[0], self.points[-1]).normalized().toAlignedRect()
        rect = rect.intersected(self.source.rect())
        if rect.isEmpty():
            return
        block = max(2, round(self.width * REDACT_BLOCK_FACTOR))
        small = self.source.copy(rect).scaled(
            max(1, rect.width() // block),
            max(1, rect.height() // block),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        painter.drawImage(rect.topLeft(), small.scaled(rect.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation))

    def paint_text(self, painter):
        font = QFont()
        font.setPixelSize(round(self.width))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        origin = self.points[0]
        box = QRectF(origin, QSizeF(metrics.horizontalAdvance(self.text) + 4, metrics.height()))
        shadow_offset = max(1.0, self.width / 18)
        painter.setPen(TEXT_SHADOW)
        painter.drawText(box.translated(shadow_offset, shadow_offset), TEXT_FLAGS, self.text)
        painter.setPen(self.color)
        painter.drawText(box, TEXT_FLAGS, self.text)
        if self.is_editing:
            caret_x = box.left() + metrics.horizontalAdvance(self.text) + 2
            painter.setPen(QPen(self.color, max(1.0, self.width / 14)))
            painter.drawLine(QPointF(caret_x, box.top()), QPointF(caret_x, box.bottom()))


def force_foreground(window):
    """Windows only lets the foreground app take focus; a synthetic Alt press lifts that lock."""
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(int(window.winId()))


class Toolbar(QFrame):
    def __init__(self, parent, overlay):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setStyleSheet(TOOLBAR_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.tool_buttons = {}
        for kind, label, key in TOOLS:
            hint = TOOL_HINTS.get(kind)
            tooltip = f"{label} ({chr(key)})" + (f" - {hint}" if hint else "")
            button = self.add_button(layout, glyph_icon(kind, ICON_SIZE), tooltip, checkable=True)
            button.clicked.connect(lambda _checked, kind=kind: overlay.toggle_tool(kind))
            self.tool_buttons[kind] = button
        self.add_separator(layout)

        self.color_buttons = []
        for color in PALETTE:
            button = self.add_button(
                layout, swatch_icon(color, SWATCH_ICON_SIZE), "Color", checkable=True, name="swatch"
            )
            button.clicked.connect(lambda _checked, color=color: overlay.select_color(color))
            self.color_buttons.append((color, button))
        self.add_separator(layout)

        self.size_buttons = []
        for size in STROKE_SIZES:
            button = self.add_button(
                layout,
                thickness_icon(size, ICON_SIZE),
                "Thickness, text size and blur strength",
                checkable=True,
            )
            button.clicked.connect(lambda _checked, size=size: overlay.select_size(size))
            self.size_buttons.append((size, button))
        self.add_separator(layout)

        self.add_button(layout, glyph_icon("undo", ICON_SIZE), "Undo (Ctrl+Z)").clicked.connect(overlay.undo)
        self.add_button(
            layout, glyph_icon("save", ICON_SIZE), "Save to a file (Ctrl+S)"
        ).clicked.connect(overlay.save)
        copy_button = self.add_button(
            layout, glyph_icon("copy", ICON_SIZE), "Copy to clipboard (Enter)", name="primary", text="Copy"
        )
        copy_button.clicked.connect(overlay.copy)
        self.add_button(layout, glyph_icon("close", ICON_SIZE), "Close (Esc)").clicked.connect(overlay.cancel)
        self.adjustSize()

    def add_button(self, layout, icon, tooltip, checkable=False, name=None, text=""):
        button = QToolButton()
        button.setIcon(icon)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        if name:
            button.setObjectName(name)
        if text:
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        layout.addWidget(button)
        return button

    def add_separator(self, layout):
        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(22)
        layout.addSpacing(5)
        layout.addWidget(line)
        layout.addSpacing(5)

    def sync(self, tool, color, size):
        for kind, button in self.tool_buttons.items():
            button.setChecked(kind == tool)
        for value, button in self.color_buttons:
            button.setChecked(value == color)
        for value, button in self.size_buttons:
            button.setChecked(value == size)


class Overlay(QWidget):
    """A frozen copy of one monitor, drawn pixel-for-pixel, with selection and annotation tools."""

    def __init__(self, shot, screen, session):
        super().__init__()
        self.session = session
        self.source = shot.image
        self.pixmap = QPixmap.fromImage(shot.image)
        self.bounds = self.source.rect()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.ratio = self.source.width() / screen.geometry().width()

        self.color = preferences.pen_color
        self.stroke_size = preferences.pen_size
        self.tool = preferences.default_tool or None
        self.dim_color = QColor(0, 0, 0, round(255 * preferences.dim_percent / 100))
        self.selection = None
        self.drag = None
        self.hover = None
        self.show_hint = False
        self.annotations = []
        self.current = None
        self.typing = None
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(SNAP_HOLD_MS)
        self.snap_timer.timeout.connect(self.snap_current_stroke)
        self.toolbar = Toolbar(self, self)
        self.toolbar.hide()
        self.sync_toolbar()
        self.settings_button = self.build_settings_button()

    def build_settings_button(self):
        button = QToolButton(self)
        button.setText("Settings")
        button.setIcon(glyph_icon("gear", SETTINGS_ICON_SIZE))
        button.setIconSize(QSize(SETTINGS_ICON_SIZE, SETTINGS_ICON_SIZE))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setStyleSheet(SETTINGS_BUTTON_STYLE)
        button.setFocusPolicy(Qt.NoFocus)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self.session.open_settings)
        button.adjustSize()
        return button

    def resizeEvent(self, _event):
        self.settings_button.move(
            self.width() - self.settings_button.width() - SETTINGS_BUTTON_MARGIN,
            SETTINGS_BUTTON_MARGIN,
        )

    def show_context_menu(self, global_position):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("Settings...", self.session.open_settings)
        menu.addAction("Open screenshots folder", open_save_folder)
        menu.addSeparator()
        menu.addAction("Cancel capture", self.cancel)
        menu.exec(global_position)

    def physical(self, position):
        return QPoint(
            min(max(round(position.x() * self.ratio), 0), self.bounds.width() - 1),
            min(max(round(position.y() * self.ratio), 0), self.bounds.height() - 1),
        )

    def activate(self):
        self.show_hint = preferences.show_hint
        self.refocus()

    def refocus(self):
        self.raise_()
        self.activateWindow()
        force_foreground(self)
        self.setFocus()

    def sync_toolbar(self):
        self.toolbar.sync(self.tool, self.color, self.stroke_size)

    def clear_selection(self):
        self.selection = None
        self.annotations = []
        self.current = None
        self.typing = None
        self.toolbar.hide()
        self.setCursor(Qt.CrossCursor)
        self.update()

    def select_all(self):
        self.session.claim(self)
        self.clear_selection()
        self.selection = QRect(self.bounds)
        self.place_toolbar()
        self.update()

    def toggle_tool(self, kind):
        self.commit_text()
        self.tool = None if self.tool == kind else kind
        self.sync_toolbar()

    def select_color(self, color):
        self.color = color
        preferences.pen_color = color
        self.sync_toolbar()

    def select_size(self, size):
        self.stroke_size = size
        preferences.pen_size = size
        self.sync_toolbar()

    def undo(self):
        self.commit_text()
        if self.annotations:
            self.annotations.pop()
            self.update()

    def copy(self):
        self.session.finish(self, "copy")

    def save(self):
        self.session.finish(self, "save")

    def cancel(self):
        self.session.cancel()

    def commit_text(self):
        if self.typing is None:
            return
        self.typing.is_editing = False
        if self.typing.text.strip():
            self.annotations.append(self.typing)
        self.typing = None
        self.update()

    def render_selection(self):
        self.commit_text()
        crop = self.source.copy(self.selection)
        painter = QPainter(crop)
        painter.translate(-self.selection.topLeft())
        for annotation in self.annotations:
            annotation.paint(painter)
        painter.end()
        return crop

    def new_annotation(self, point):
        width = self.stroke_size * self.ratio
        if self.tool == "text":
            width = TEXT_PIXELS[self.stroke_size] * self.ratio
        return Annotation(self.tool, self.color, width, point, self.source)

    def edges_at(self, point):
        """Edge letters under the point (e.g. "lt"), "move" inside the selection, else None."""
        rect = self.selection
        margin = HANDLE_HIT_MARGIN * self.ratio
        inside_x = rect.left() - margin <= point.x() <= rect.right() + margin
        inside_y = rect.top() - margin <= point.y() <= rect.bottom() + margin
        horizontal = ""
        if inside_y:
            horizontal = (
                "l" if abs(point.x() - rect.left()) <= margin
                else "r" if abs(point.x() - rect.right()) <= margin
                else ""
            )
        vertical = ""
        if inside_x:
            vertical = (
                "t" if abs(point.y() - rect.top()) <= margin
                else "b" if abs(point.y() - rect.bottom()) <= margin
                else ""
            )
        if horizontal or vertical:
            return horizontal + vertical
        return "move" if rect.contains(point) else None

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())
            return
        if event.button() != Qt.LeftButton:
            return
        self.show_hint = False
        point = self.physical(event.position())
        self.commit_text()
        target = self.edges_at(point) if self.selection else None
        if target == "move" and self.tool == "text":
            self.typing = self.new_annotation(point)
            self.typing.is_editing = True
        elif target == "move" and self.tool:
            self.current = self.new_annotation(point)
        elif target:
            self.drag = (target, point, QRect(self.selection))
        else:
            self.session.claim(self)
            self.clear_selection()
            self.drag = ("create", point, None)
        self.update()

    def mouseDoubleClickEvent(self, event):
        point = self.physical(event.position())
        if event.button() == Qt.LeftButton and not (self.selection and self.edges_at(point)):
            self.select_all()

    def mouseMoveEvent(self, event):
        point = self.physical(event.position())
        self.hover = point
        if self.current is not None:
            if not self.current.is_snapped:
                self.current.extend(self.clamped_to_selection(point))
                if self.current.kind in FREEHAND_TOOLS:
                    self.snap_timer.start()
        elif self.drag is not None:
            self.update_drag(point)
        elif self.selection:
            self.update_cursor(self.edges_at(point))
        self.update()

    def snap_current_stroke(self):
        if self.current is not None and self.current.snap_to_shape():
            self.update()

    def leaveEvent(self, _event):
        self.hover = None
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self.current is not None:
            self.snap_timer.stop()
            if self.current.kind in FREEHAND_TOOLS:
                self.current.finish_stroke()
            self.annotations.append(self.current)
            self.current = None
        elif self.drag is not None:
            self.drag = None
            if (
                self.selection is None
                or self.selection.width() < MIN_SELECTION_SIZE
                or self.selection.height() < MIN_SELECTION_SIZE
            ):
                self.clear_selection()
                return
            self.place_toolbar()
        self.update()

    def clamped_to_selection(self, point):
        return QPoint(
            min(max(point.x(), self.selection.left()), self.selection.right()),
            min(max(point.y(), self.selection.top()), self.selection.bottom()),
        )

    def update_drag(self, point):
        mode, start, origin = self.drag
        if mode == "create":
            rect = QRect(start, point)
        elif mode == "move":
            rect = origin.translated(point - start)
            rect.moveLeft(min(max(rect.left(), 0), self.bounds.width() - rect.width()))
            rect.moveTop(min(max(rect.top(), 0), self.bounds.height() - rect.height()))
        else:
            rect = QRect(origin)
            if "l" in mode:
                rect.setLeft(point.x())
            if "r" in mode:
                rect.setRight(point.x())
            if "t" in mode:
                rect.setTop(point.y())
            if "b" in mode:
                rect.setBottom(point.y())
        self.selection = rect.normalized().intersected(self.bounds)
        if mode != "create":
            self.place_toolbar()

    def update_cursor(self, target):
        if target == "move":
            self.setCursor(Qt.CrossCursor if self.tool else Qt.SizeAllCursor)
        elif target:
            self.setCursor(CURSOR_BY_EDGES[target])
        else:
            self.setCursor(Qt.CrossCursor)

    def place_toolbar(self):
        rect = QRectF(self.selection)
        top, bottom = rect.top() / self.ratio, rect.bottom() / self.ratio
        right = rect.right() / self.ratio
        width, height = self.toolbar.width(), self.toolbar.height()
        x = min(max(right - width, 0), self.width() - width)
        if bottom + TOOLBAR_GAP + height <= self.height():
            y = bottom + TOOLBAR_GAP
        elif top - TOOLBAR_GAP - height >= 0:
            y = top - TOOLBAR_GAP - height
        else:
            y = bottom - height - TOOLBAR_GAP
        self.toolbar.move(int(x), int(y))
        self.toolbar.show()
        self.toolbar.raise_()

    def is_picking(self):
        return self.hover is not None and (self.drag is not None or not self.selection)

    def is_ctrl_down(self):
        return bool(user32.GetAsyncKeyState(VK_CONTROL) & KEY_DOWN_MASK)

    def keyReleaseEvent(self, _event):
        self.update()

    def keyPressEvent(self, event):
        self.update()
        if self.typing is not None:
            self.type_text(event)
            return
        key = event.key()
        ctrl = event.modifiers() & Qt.ControlModifier
        if key == Qt.Key_Escape:
            self.cancel()
        elif ctrl and key == Qt.Key_C and self.is_picking():
            self.session.pick_color(QColor(self.source.pixel(self.hover.x(), self.hover.y())))
        elif ctrl and key == Qt.Key_A:
            self.select_all()
        elif not self.selection:
            return
        elif key in (Qt.Key_Return, Qt.Key_Enter) or (ctrl and key == Qt.Key_C):
            self.copy()
        elif ctrl and key == Qt.Key_S:
            self.save()
        elif ctrl and key == Qt.Key_Z:
            self.undo()
        elif key in ARROW_KEY_DIRECTIONS:
            self.nudge(ARROW_KEY_DIRECTIONS[key], event.modifiers() & Qt.ShiftModifier)
        elif not ctrl:
            self.select_tool_for_key(key)

    def select_tool_for_key(self, key):
        for kind, _label, tool_key in TOOLS:
            if key == tool_key:
                self.toggle_tool(kind)

    def nudge(self, direction, is_fast):
        step = NUDGE_PIXELS_FAST if is_fast else NUDGE_PIXELS
        moved = self.selection.translated(direction * step)
        moved.moveLeft(min(max(moved.left(), 0), self.bounds.width() - moved.width()))
        moved.moveTop(min(max(moved.top(), 0), self.bounds.height() - moved.height()))
        self.selection = moved
        self.place_toolbar()
        self.update()

    def type_text(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.typing = None
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self.commit_text()
        elif key == Qt.Key_Backspace:
            self.typing.text = self.typing.text[:-1]
        elif event.text().isprintable():
            self.typing.text += event.text()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.scale(1 / self.ratio, 1 / self.ratio)
        painter.drawPixmap(0, 0, self.pixmap)
        if self.selection:
            self.paint_selection(painter)
        else:
            painter.fillRect(self.bounds, self.dim_color)
            self.paint_crosshair(painter)
            self.paint_hint(painter)
        if self.is_picking() and self.is_ctrl_down():
            self.paint_loupe(painter)

    def paint_selection(self, painter):
        rect, bounds = self.selection, self.bounds
        for region in [
            QRect(0, 0, bounds.width(), rect.top()),
            QRect(0, rect.bottom() + 1, bounds.width(), bounds.height() - rect.bottom() - 1),
            QRect(0, rect.top(), rect.left(), rect.height()),
            QRect(rect.right() + 1, rect.top(), bounds.width() - rect.right() - 1, rect.height()),
        ]:
            painter.fillRect(region, self.dim_color)

        painter.save()
        painter.setClipRect(rect)
        for annotation in self.annotations + [a for a in (self.current, self.typing) if a]:
            annotation.paint(painter)
        painter.restore()

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ACCENT, max(1.0, self.ratio)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        self.paint_handles(painter, rect)
        self.paint_pill(painter, f"{rect.width()} x {rect.height()}", rect.left(), rect.top(), above=True)

    def paint_crosshair(self, painter):
        if not self.hover:
            return
        painter.setPen(QPen(CROSSHAIR_COLOR, max(1.0, self.ratio)))
        painter.drawLine(0, self.hover.y(), self.bounds.width(), self.hover.y())
        painter.drawLine(self.hover.x(), 0, self.hover.x(), self.bounds.height())

    def paint_hint(self, painter):
        if self.show_hint and not self.drag:
            self.paint_pill(painter, HINT_TEXT, None, HINT_TOP * self.ratio, above=False)

    def paint_handles(self, painter, rect):
        size = HANDLE_SIZE * self.ratio
        painter.setBrush(QColor("white"))
        painter.setPen(QPen(ACCENT, max(1.0, self.ratio)))
        xs = [rect.left(), rect.center().x(), rect.right()]
        ys = [rect.top(), rect.center().y(), rect.bottom()]
        for x in xs:
            for y in ys:
                if (x, y) != (xs[1], ys[1]):
                    painter.drawRect(QRectF(x - size / 2, y - size / 2, size, size))

    def paint_pill(self, painter, text, x, y, above):
        """A dark rounded label; x=None centers it horizontally, above=True sits over y."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont()
        font.setPixelSize(round(LABEL_FONT_PIXELS * self.ratio))
        painter.setFont(font)
        padding = LABEL_PADDING * self.ratio
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text) + padding * 3
        height = metrics.height() + padding
        left = (self.bounds.width() - width) / 2 if x is None else x
        top = y - height - padding if above else y
        if top < 0:
            top = y + padding
        box = QRectF(left, top, width, height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 28, 30, 235))
        painter.drawRoundedRect(box, 6 * self.ratio, 6 * self.ratio)
        painter.setPen(QColor("white"))
        painter.drawText(box, Qt.AlignCenter, text)
        painter.restore()

    def paint_loupe(self, painter):
        cell = LOUPE_CELL * self.ratio
        size = cell * LOUPE_PIXELS
        offset = LOUPE_OFFSET * self.ratio
        info_height = 30 * self.ratio
        point = self.hover
        x = point.x() + offset
        if x + size > self.bounds.width():
            x = point.x() - offset - size
        y = point.y() + offset
        if y + size + info_height > self.bounds.height():
            y = point.y() - offset - size - info_height
        target = QRectF(x, y, size, size)
        half = LOUPE_PIXELS // 2
        source = QRectF(point.x() - half, point.y() - half, LOUPE_PIXELS, LOUPE_PIXELS)

        painter.save()
        painter.fillRect(target, QColor("black"))
        painter.drawImage(target, self.source, source)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ACCENT, 2 * self.ratio))
        painter.drawRect(target)
        center = QRectF(x + half * cell, y + half * cell, cell, cell)
        painter.setPen(QPen(QColor("white"), max(1.0, self.ratio)))
        painter.drawRect(center)
        painter.setPen(QPen(QColor("black"), max(1.0, self.ratio)))
        painter.drawRect(center.adjusted(-self.ratio, -self.ratio, self.ratio, self.ratio))
        painter.restore()

        pixel = QColor(self.source.pixel(point.x(), point.y()))
        label = f"{point.x()}, {point.y()}   {pixel.name().upper()}   Ctrl+C: copy"
        self.paint_pill(painter, label, x, y + size + 4 * self.ratio, above=False)


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
            overlay.close()
            overlay.deleteLater()
