from PySide6.QtCore import (
    Qt,
)

PALETTE = ["#ff3b30", "#ffcc00", "#34c759", "#0a84ff", "#ffffff", "#1c1c1e"]
STROKE_SIZES = [3, 6, 10]
TEXT_PIXELS = {3: 18, 6: 28, 10: 44}
TOOLS = [
    ("pen", "Pen", Qt.Key_P),
    ("arrow", "Arrow", Qt.Key_A),
    ("marker", "Marker", Qt.Key_M),
    ("box", "Box", Qt.Key_B),
    ("ellipse", "Ellipse", Qt.Key_O),
    ("text", "Text", Qt.Key_T),
    ("redact", "Redact", Qt.Key_R),
]
TOOL_HINTS = {
    "pen": "hold still at the end of a stroke to snap it to a line, oval or box",
    "marker": "hold still at the end of a stroke to straighten it",
}
FREEHAND_TOOLS = ("pen", "marker")
