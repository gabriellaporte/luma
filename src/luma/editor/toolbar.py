from PySide6.QtCore import (
    QSize,
    Qt,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QToolButton

from luma.editor.tools import PALETTE, STROKE_SIZES, TOOL_HINTS, TOOLS
from luma.ui.icons import glyph_icon, swatch_icon, thickness_icon

ICON_SIZE = 22
SWATCH_ICON_SIZE = 24
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
        self.add_button(layout, glyph_icon("save", ICON_SIZE), "Save to a file (Ctrl+S)").clicked.connect(
            overlay.save
        )
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
