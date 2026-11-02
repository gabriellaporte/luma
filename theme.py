import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

MENU_STYLE = """
QMenu { background: #1c1c1e; color: white; border: 1px solid #3a3a3c; border-radius: 8px;
        padding: 4px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: #0a84ff; }
QMenu::item:disabled { color: #8e8e93; }
QMenu::separator { height: 1px; background: #3a3a3c; margin: 4px 8px; }
"""

_DIALOG_STYLE_TEMPLATE = """
QDialog { background: #1c1c1e; }
QLabel { color: #f2f2f7; font-size: 13px; }
QLabel#hint { color: #8e8e93; font-size: 12px; }
QLabel#error { color: #ff6b61; font-size: 12px; }
QTabWidget::pane { border: 1px solid #3a3a3c; border-radius: 8px; top: -1px; }
QTabBar::tab { color: #aeaeb2; padding: 8px 18px; border: none; font-size: 13px; }
QTabBar::tab:selected { color: white; border-bottom: 2px solid #0a84ff; }
QCheckBox { color: #f2f2f7; font-size: 13px; spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #636366;
                       background: #2c2c2e; }
QCheckBox::indicator:checked { background: #0a84ff; border-color: #0a84ff; }
QLineEdit, QComboBox, QKeySequenceEdit, QSpinBox { background: #2c2c2e; color: white; padding: 6px 8px;
        border: 1px solid #3a3a3c; border-radius: 6px; font-size: 13px; }
QLineEdit:focus, QComboBox:focus, QKeySequenceEdit:focus, QSpinBox:focus { border-color: #0a84ff; }
QComboBox::drop-down { border: none; width: 26px; background: transparent; }
QComboBox::down-arrow { image: url({chevron}); width: 12px; height: 8px; }
QComboBox QAbstractItemView { background: #2c2c2e; color: white; selection-background-color: #0a84ff; }
QPushButton { background: #2c2c2e; color: white; padding: 7px 16px; border: 1px solid #3a3a3c;
              border-radius: 6px; font-size: 13px; }
QPushButton:hover { background: #3a3a3c; }
QPushButton#primary { background: #0a84ff; border-color: #0a84ff; font-weight: 600; }
QToolButton { background: #2c2c2e; border: 2px solid transparent; border-radius: 8px; padding: 4px; }
QToolButton:checked { border-color: #0a84ff; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QSpinBox:disabled { color: #636366; }
"""


def dialog_style():
    return _DIALOG_STYLE_TEMPLATE.replace("{chevron}", chevron_path())


def chevron_path():
    """Qt style sheets only take arrows from files, so draw one once into the temp folder."""
    path = Path(tempfile.gettempdir()) / "luma-chevron.png"
    pixmap = QPixmap(12, 8)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#aeaeb2"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPolyline([QPointF(1.5, 1.5), QPointF(6, 6), QPointF(10.5, 1.5)])
    painter.end()
    pixmap.save(str(path))
    return path.as_posix()
