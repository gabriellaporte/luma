from PySide6.QtCore import (
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from luma.editor.annotations import Annotation
from luma.editor.toolbar import Toolbar
from luma.editor.tools import FREEHAND_TOOLS, TEXT_PIXELS, TOOLS
from luma.preferences import preferences
from luma.saving import open_save_folder
from luma.system.keyboard import force_foreground, is_ctrl_down
from luma.ui.icons import glyph_icon
from luma.ui.theme import MENU_STYLE

LOUPE_PIXELS = 15
LOUPE_CELL = 9
LOUPE_OFFSET = 26
CROSSHAIR_COLOR = QColor(255, 255, 255, 90)
HINT_TEXT = (
    "Drag to select   |   Double-click: whole screen   |   "
    "Hold Ctrl: magnifier, Ctrl+C: copy color   |   Right-click: menu   |   Esc: cancel"
)
SNAP_HOLD_MS = 450
HINT_TOP = 56
NUDGE_PIXELS = 1
NUDGE_PIXELS_FAST = 10
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
SETTINGS_ICON_SIZE = 18
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
                "l"
                if abs(point.x() - rect.left()) <= margin
                else "r"
                if abs(point.x() - rect.right()) <= margin
                else ""
            )
        vertical = ""
        if inside_x:
            vertical = (
                "t"
                if abs(point.y() - rect.top()) <= margin
                else "b"
                if abs(point.y() - rect.bottom()) <= margin
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
        if self.is_picking() and is_ctrl_down():
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
