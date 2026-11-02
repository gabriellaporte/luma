from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luma import APP_NAME, __version__
from luma.editor.tools import PALETTE, STROKE_SIZES, TOOLS
from luma.preferences import preferences
from luma.saving import IMAGE_FORMATS, LOSSY_FORMATS, file_stem, open_save_folder
from luma.system import autostart
from luma.system.hotkeys import to_windows_hotkey
from luma.ui.icons import swatch_icon
from luma.ui.theme import dialog_style

MIN_QUALITY = 10
MAX_DIM_PERCENT = 90
SIZE_LABELS = {3: "Thin", 6: "Medium", 10: "Thick"}
FILE_NAME_HELP = "Date and time codes: %Y year, %m month, %d day, %H hour, %M minute, %S second."


def hint(text):
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def checkbox(text, value, on_toggle):
    box = QCheckBox(text)
    box.setChecked(value)
    box.toggled.connect(on_toggle)
    return box


class SettingsDialog(QDialog):
    """Every option applies as soon as it changes; there is nothing to confirm."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} settings")
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setStyleSheet(dialog_style())
        self.setMinimumWidth(560)

        self.tabs = QTabWidget()
        restore = QPushButton("Restore defaults")
        restore.clicked.connect(self.restore_defaults)
        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addWidget(QLabel(f"{APP_NAME} {__version__}"))
        footer.addStretch()
        footer.addWidget(restore)
        footer.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addLayout(footer)
        self.build_tabs()

    def build_tabs(self):
        self.tabs.clear()
        self.tabs.addTab(self.general_tab(), "General")
        self.tabs.addTab(self.saving_tab(), "Saving")
        self.tabs.addTab(self.editor_tab(), "Editor")

    def restore_defaults(self):
        preferences.reset()
        self.build_tabs()

    def page(self):
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignLeft)
        return widget, form

    def general_tab(self):
        widget, form = self.page()
        self.shortcut_error = QLabel()
        self.shortcut_error.setObjectName("error")

        self.primary_edit = self.shortcut_edit(
            preferences.capture_shortcut, "capture_shortcut", required=True
        )
        self.secondary_edit = self.shortcut_edit(
            preferences.secondary_shortcut, "secondary_shortcut", required=False
        )
        clear = QPushButton("Clear")
        clear.clicked.connect(self.secondary_edit.clear)
        secondary_row = QHBoxLayout()
        secondary_row.addWidget(self.secondary_edit)
        secondary_row.addWidget(clear)

        form.addRow("Capture shortcut", self.primary_edit)
        form.addRow("Second shortcut", secondary_row)
        form.addRow(self.shortcut_error)
        form.addRow(
            hint(
                "Click a box and press the keys you want. Print Screen, letters, digits and F-keys, "
                "with Ctrl, Alt, Shift or Win, all work."
            )
        )
        form.addRow(checkbox("Start with Windows", autostart.is_enabled(APP_NAME), self.set_autostart))
        form.addRow(
            checkbox(
                "Show a confirmation after copying or saving",
                preferences.show_confirmation,
                lambda value: setattr(preferences, "show_confirmation", value),
            )
        )
        form.addRow(
            checkbox(
                "Show the help hint when a capture starts",
                preferences.show_hint,
                lambda value: setattr(preferences, "show_hint", value),
            )
        )
        return widget

    def shortcut_edit(self, value, setting, required):
        edit = QKeySequenceEdit(QKeySequence(value))
        edit.setMaximumSequenceLength(1)
        edit.editingFinished.connect(lambda: self.store_shortcut(edit, setting, required))
        return edit

    def store_shortcut(self, edit, setting, required):
        text = edit.keySequence().toString()
        other = (
            preferences.secondary_shortcut if setting == "capture_shortcut" else preferences.capture_shortcut
        )
        try:
            if text:
                to_windows_hotkey(text)
            if not text and required:
                raise ValueError("The capture shortcut cannot be empty.")
            if text and text == other:
                raise ValueError("Both shortcuts are the same.")
        except ValueError as error:
            self.shortcut_error.setText(str(error))
            edit.setKeySequence(QKeySequence(getattr(preferences, setting)))
            return
        self.shortcut_error.setText("")
        setattr(preferences, setting, text)

    def set_autostart(self, enabled):
        if enabled:
            autostart.enable(APP_NAME)
        else:
            autostart.disable(APP_NAME)

    def saving_tab(self):
        widget, form = self.page()

        self.folder_edit = QLineEdit(preferences.save_folder)
        self.folder_edit.editingFinished.connect(
            lambda: setattr(preferences, "save_folder", self.folder_edit.text())
        )
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_folder)
        open_folder = QPushButton("Open")
        open_folder.clicked.connect(open_save_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(browse)
        folder_row.addWidget(open_folder)

        self.name_edit = QLineEdit(preferences.file_name_template)
        self.name_edit.textChanged.connect(self.set_file_name_template)
        self.name_preview = hint("")

        self.format_box = QComboBox()
        self.format_box.addItems(IMAGE_FORMATS)
        self.format_box.setCurrentText(preferences.image_format)
        self.format_box.currentTextChanged.connect(self.set_image_format)
        self.quality_box = QSpinBox()
        self.quality_box.setRange(MIN_QUALITY, 100)
        self.quality_box.setSuffix(" / 100")
        self.quality_box.setValue(preferences.image_quality)
        self.quality_box.valueChanged.connect(lambda value: setattr(preferences, "image_quality", value))

        form.addRow("Save folder", folder_row)
        form.addRow("File name", self.name_edit)
        form.addRow(self.name_preview)
        form.addRow(hint(FILE_NAME_HELP))
        form.addRow("Format", self.format_box)
        form.addRow("Quality (JPEG and WebP)", self.quality_box)
        form.addRow(
            checkbox(
                "Ask where to save every time",
                preferences.ask_where_to_save,
                lambda value: setattr(preferences, "ask_where_to_save", value),
            )
        )
        form.addRow(
            checkbox(
                "Also save a file whenever I copy to the clipboard",
                preferences.save_on_copy,
                lambda value: setattr(preferences, "save_on_copy", value),
            )
        )
        self.refresh_saving_labels()
        return widget

    def browse_folder(self):
        chosen = QFileDialog.getExistingDirectory(self, "Choose the save folder", preferences.save_folder)
        if chosen:
            preferences.save_folder = str(Path(chosen))
            self.folder_edit.setText(preferences.save_folder)

    def set_file_name_template(self, text):
        preferences.file_name_template = text
        self.refresh_saving_labels()

    def set_image_format(self, name):
        preferences.image_format = name
        self.refresh_saving_labels()

    def refresh_saving_labels(self):
        example = file_stem(preferences.file_name_template, datetime.now())
        self.name_preview.setText(f"Example: {example}.{IMAGE_FORMATS[preferences.image_format]}")
        self.quality_box.setEnabled(preferences.image_format in LOSSY_FORMATS)

    def editor_tab(self):
        widget, form = self.page()

        tool_box = QComboBox()
        tool_box.addItem("None (move the selection)", "")
        for kind, label, _key in TOOLS:
            tool_box.addItem(label, kind)
        tool_box.setCurrentIndex(max(0, tool_box.findData(preferences.default_tool)))
        tool_box.currentIndexChanged.connect(
            lambda: setattr(preferences, "default_tool", tool_box.currentData())
        )

        swatches = QHBoxLayout()
        group = QButtonGroup(widget)
        for color in PALETTE:
            button = QToolButton()
            button.setCheckable(True)
            button.setChecked(color == preferences.pen_color)
            button.setIcon(swatch_icon(color, 22))
            button.setIconSize(QSize(22, 22))
            button.clicked.connect(lambda _checked, color=color: setattr(preferences, "pen_color", color))
            group.addButton(button)
            swatches.addWidget(button)
        swatches.addStretch()

        size_box = QComboBox()
        for size in STROKE_SIZES:
            size_box.addItem(SIZE_LABELS[size], size)
        size_box.setCurrentIndex(max(0, size_box.findData(preferences.pen_size)))
        size_box.currentIndexChanged.connect(lambda: setattr(preferences, "pen_size", size_box.currentData()))

        dim_box = QSpinBox()
        dim_box.setRange(0, MAX_DIM_PERCENT)
        dim_box.setSuffix(" %")
        dim_box.setValue(preferences.dim_percent)
        dim_box.valueChanged.connect(lambda value: setattr(preferences, "dim_percent", value))

        form.addRow("Starting tool", tool_box)
        form.addRow("Annotation color", swatches)
        form.addRow("Annotation size", size_box)
        form.addRow("Background dimming", dim_box)
        form.addRow(
            hint(
                "Changes apply from the next capture. The color and size also follow "
                "what you pick in the toolbar."
            )
        )
        return widget
