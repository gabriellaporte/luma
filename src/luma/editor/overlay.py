import time

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
    QFontMetrics,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from luma.editor.annotations import Annotation
from luma.editor.crosshair import CrosshairLines
from luma.editor.diagnostics import InteractionStats
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
LOUPE_LABEL_WIDTH = 360
SELECTION_BAND = 14
IMMEDIATE_REPAINT_INTERVAL = 0.005
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
        self.pixmap.setDevicePixelRatio(self.ratio)
        self.dimmed = self.build_dimmed_pixmap()
        self.selection = None
        self.drag = None
        self.hover = None
        self.show_hint = False
        self.annotations = []
        self.current = None
        self.typing = None
        self.stats = InteractionStats()
        self.lines = CrosshairLines(shot.monitor.rect, self.ratio)
        self.last_paint = 0.0
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

    def build_dimmed_pixmap(self):
        """The darkened screen is built once, so painting never has to alpha-blend the full frame."""
        dimmed = QPixmap(self.pixmap)
        painter = QPainter(dimmed)
        painter.fillRect(dimmed.rect(), self.dim_color)
        painter.end()
        return dimmed

    def widget_rect(self, rect):
        """A physical-pixel rectangle as the aligned widget rectangle that covers it."""
        scaled = QRectF(
            rect.x() / self.ratio,
            rect.y() / self.ratio,
            rect.width() / self.ratio,
            rect.height() / self.ratio,
        )
        return scaled.toAlignedRect().adjusted(-1, -1, 1, 1)

    def invalidate(self, *rects):
        """Repaint these physical-pixel rectangles now, or on the next loop if one just happened.

        Painting right inside the mouse handler skips the event queue, which keeps the drawing as
        close as possible to the cursor; the interval stops a fast mouse from painting every event.
        """
        region = QRegion()
        for rect in rects:
            region = region.united(self.widget_rect(rect))
        if region.isEmpty():
            return
        if time.perf_counter() - self.last_paint >= IMMEDIATE_REPAINT_INTERVAL:
            self.repaint(region)
        else:
            self.update(region)

    def loupe_geometry(self, point):
        cell = LOUPE_CELL * self.ratio
        size = cell * LOUPE_PIXELS
        offset = LOUPE_OFFSET * self.ratio
        info_height = 30 * self.ratio
        x = point.x() + offset
        if x + size > self.bounds.width():
            x = point.x() - offset - size
        y = point.y() + offset
        if y + size + info_height > self.bounds.height():
            y = point.y() - offset - size - info_height
        return QRectF(x, y, size, size), info_height

    def loupe_rect(self, point):
        target, info_height = self.loupe_geometry(point)
        margin = 6 * self.ratio
        return QRectF(
            target.x() - margin,
            target.y() - margin,
            max(target.width(), LOUPE_LABEL_WIDTH * self.ratio) + 2 * margin,
            target.height() + info_height + 4 * margin,
        ).toAlignedRect()

    def hover_dirty_rects(self, point):
        if point is None:
            return []
        rects = []
        if is_ctrl_down():
            rects.append(self.loupe_rect(point))
        return rects

    def selection_dirty_rects(self, old, new):
        """What a selection change touches: both outlines with their labels, and the area that flipped."""
        rects = []
        for rect in (old, new):
            if rect:
                rects += self.outline_bands(rect)
        if old and new:
            rects += list(QRegion(old).xored(QRegion(new)))
        elif old or new:
            rects.append(old or new)
        return rects

    def outline_bands(self, rect):
        """The frame, handles and size label of a selection: everything outside its own pixels."""
        side = round(SELECTION_BAND * self.ratio)
        label = self.size_label_box(rect).toAlignedRect().adjusted(-2, -2, 2, 2)
        return [
            QRect(rect.left() - side, rect.top() - side, rect.width() + 2 * side, 2 * side),
            QRect(rect.left() - side, rect.bottom() - side, rect.width() + 2 * side, 2 * side),
            QRect(rect.left() - side, rect.top() - side, 2 * side, rect.height() + 2 * side),
            QRect(rect.right() - side, rect.top() - side, 2 * side, rect.height() + 2 * side),
            label,
        ]

    def size_label_box(self, rect):
        return self.pill_box(f"{rect.width()} x {rect.height()}", rect.left(), rect.top(), above=True)

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
        self.lines.raise_to_top()
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
            self.toolbar.hide()
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
        started = self.stats.mouse_moved()
        point = self.physical(event.position())
        dirty = self.hover_dirty_rects(self.hover)
        self.hover = point
        if self.current is not None:
            if not self.current.is_snapped:
                dirty.append(self.current.bounds())
                self.current.extend(self.clamped_to_selection(point))
                dirty.append(self.current.bounds())
                if self.current.kind in FREEHAND_TOOLS:
                    self.snap_timer.start()
        elif self.drag is not None:
            previous = self.selection
            self.update_drag(point)
            dirty += self.selection_dirty_rects(previous, self.selection)
        elif self.selection:
            self.update_cursor(self.edges_at(point))
        self.invalidate(*dirty, *self.hover_dirty_rects(point))
        self.move_crosshair(point)
        self.stats.handler_done(started)

    def move_crosshair(self, point):
        if self.isVisible() and self.selection is None and self.drag is None:
            self.lines.follow(point)
        else:
            self.lines.hide()

    def closeEvent(self, event):
        self.lines.close()
        super().closeEvent(event)

    def snap_current_stroke(self):
        if self.current is not None and self.current.snap_to_shape():
            self.update()

    def leaveEvent(self, _event):
        self.hover = None
        self.lines.hide()
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

    def update_cursor(self, target):
        if target == "move":
            shape = Qt.CrossCursor if self.tool else Qt.SizeAllCursor
        elif target:
            shape = CURSOR_BY_EDGES[target]
        else:
            shape = Qt.CrossCursor
        if shape != self.cursor().shape():
            self.setCursor(shape)

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
        started = self.stats.paint_started()
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.dimmed)
        if self.selection:
            self.paint_bright_selection(painter)
        painter.scale(1 / self.ratio, 1 / self.ratio)
        if self.selection:
            self.paint_selection(painter)
        else:
            self.paint_hint(painter)
        if self.is_picking() and is_ctrl_down():
            self.paint_loupe(painter)
        painter.end()
        self.stats.painted(started)
        self.last_paint = time.perf_counter()

    def paint_bright_selection(self, painter):
        """Show the undimmed screen inside the selection, with a native 1:1 pixel copy."""
        painter.save()
        painter.scale(1 / self.ratio, 1 / self.ratio)
        painter.setClipRect(self.selection, Qt.IntersectClip)
        painter.resetTransform()
        painter.drawPixmap(0, 0, self.pixmap)
        painter.restore()

    def paint_selection(self, painter):
        rect = self.selection
        painter.save()
        painter.setClipRect(rect, Qt.IntersectClip)
        for annotation in self.annotations + [a for a in (self.current, self.typing) if a]:
            annotation.paint(painter)
        painter.restore()

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ACCENT, max(1.0, self.ratio)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        self.paint_handles(painter, rect)
        self.paint_pill(painter, f"{rect.width()} x {rect.height()}", rect.left(), rect.top(), above=True)

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

    def pill_font(self):
        font = QFont()
        font.setPixelSize(round(LABEL_FONT_PIXELS * self.ratio))
        return font

    def pill_box(self, text, x, y, above):
        """Where a label sits: x=None centers it horizontally, above=True puts it over y."""
        padding = LABEL_PADDING * self.ratio
        metrics = QFontMetrics(self.pill_font())
        width = metrics.horizontalAdvance(text) + padding * 3
        height = metrics.height() + padding
        left = (self.bounds.width() - width) / 2 if x is None else x
        top = y - height - padding if above else y
        if top < 0:
            top = y + padding
        return QRectF(left, top, width, height)

    def paint_pill(self, painter, text, x, y, above):
        """A dark rounded label."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.pill_font())
        box = self.pill_box(text, x, y, above)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 28, 30, 235))
        painter.drawRoundedRect(box, 6 * self.ratio, 6 * self.ratio)
        painter.setPen(QColor("white"))
        painter.drawText(box, Qt.AlignCenter, text)
        painter.restore()

    def paint_loupe(self, painter):
        point = self.hover
        target, _info_height = self.loupe_geometry(point)
        cell = target.width() / LOUPE_PIXELS
        half = LOUPE_PIXELS // 2
        source = QRectF(point.x() - half, point.y() - half, LOUPE_PIXELS, LOUPE_PIXELS)

        painter.save()
        painter.fillRect(target, QColor("black"))
        painter.drawImage(target, self.source, source)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ACCENT, 2 * self.ratio))
        painter.drawRect(target)
        center = QRectF(target.x() + half * cell, target.y() + half * cell, cell, cell)
        painter.setPen(QPen(QColor("white"), max(1.0, self.ratio)))
        painter.drawRect(center)
        painter.setPen(QPen(QColor("black"), max(1.0, self.ratio)))
        painter.drawRect(center.adjusted(-self.ratio, -self.ratio, self.ratio, self.ratio))
        painter.restore()

        pixel = QColor(self.source.pixel(point.x(), point.y()))
        label = f"{point.x()}, {point.y()}   {pixel.name().upper()}   Ctrl+C: copy"
        self.paint_pill(painter, label, target.x(), target.bottom() + 4 * self.ratio, above=False)
